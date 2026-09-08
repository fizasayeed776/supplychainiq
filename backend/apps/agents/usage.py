"""
LLM usage tracking: Redis-backed counters for total calls, cache hits, and
estimated cost.  All counters are scoped to the current calendar month so
the monthly cap (LLM_MONTHLY_USAGE_CAP_USD) can be enforced/reported.

Counter keys (all live in Django's default cache / Redis DB 1):
  llmusage:<YYYY-MM>:calls_complete    — total LLMClient.complete() calls
  llmusage:<YYYY-MM>:hits_complete     — cache hits on complete()
  llmusage:<YYYY-MM>:calls_embed       — total embed() calls
  llmusage:<YYYY-MM>:hits_embed        — cache hits on embed()
  llmusage:<YYYY-MM>:tokens_approx     — approximate token sum (whitespace split)
  llmusage:<YYYY-MM>:cost_usd_millicents — estimated cost × 100 000 (int to avoid float drift)

Using integer millicents (1/100 000 of a dollar) keeps all increments as
atomic integer adds, which Redis handles safely without compare-and-swap.
"""
import logging
from datetime import datetime

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-model cost table (USD per 1 000 tokens, input+output blended estimate).
# Override in settings as LLM_COST_PER_1K_TOKENS = {"model-name": 0.002, ...}
# ---------------------------------------------------------------------------
_DEFAULT_COST_TABLE: dict[str, float] = {
    # OpenAI
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.00015,
    "gpt-4-turbo": 0.01,
    "gpt-3.5-turbo": 0.0005,
    # Gemini
    "gemini-1.5-pro": 0.00125,
    "gemini-1.5-flash": 0.000075,
    "gemini-embedding-001": 0.000025,
    # Groq (free tier, nominal cost for cap tracking)
    "llama-3.1-8b-instant": 0.00005,
    "llama-3.3-70b-versatile": 0.00059,
}

# Cache TTL: keep counters for 35 days so month-boundary reporting still works.
_COUNTER_TTL = 60 * 60 * 24 * 35


def _month_prefix() -> str:
    return f"llmusage:{datetime.utcnow().strftime('%Y-%m')}"


def _cost_per_1k(model: str) -> float:
    table: dict[str, float] = getattr(settings, "LLM_COST_PER_1K_TOKENS", _DEFAULT_COST_TABLE)
    # Exact match first, then prefix match (e.g. "gpt-4o-mini-2024-07-18" → "gpt-4o-mini")
    if model in table:
        return table[model]
    for prefix, cost in table.items():
        if model.startswith(prefix):
            return cost
    return 0.001  # conservative fallback


def _approx_tokens(text: str) -> int:
    """Whitespace-split word count — good-enough approximation when a real
    tokenizer isn't available; errs on the side of slight over-counting."""
    return len(text.split()) if text else 0


def _increment(key: str, amount: int = 1) -> None:
    """Atomic integer increment via Redis INCR (exposed through Django cache
    ``incr``; falls back to get/set for non-Redis backends in tests)."""
    try:
        cache.incr(key, amount)
    except ValueError:
        # Key doesn't exist yet — set it, then it will be incrementable.
        cache.set(key, amount, timeout=_COUNTER_TTL)
    except Exception:
        # Non-Redis backend (e.g. LocMemCache in tests) may not support incr.
        current = cache.get(key, 0)
        cache.set(key, current + amount, timeout=_COUNTER_TTL)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_complete(model: str, prompt_text: str, cached: bool) -> None:
    """Call after every LLMClient.complete() invocation."""
    prefix = _month_prefix()
    _increment(f"{prefix}:calls_complete")
    if cached:
        _increment(f"{prefix}:hits_complete")
    tokens = _approx_tokens(prompt_text)
    _increment(f"{prefix}:tokens_approx", tokens)
    cost_millicents = int(_cost_per_1k(model) * tokens / 1000 * 100_000)
    if cost_millicents > 0:
        _increment(f"{prefix}:cost_usd_millicents", cost_millicents)
    _check_cap(prefix)


def record_embed(model: str, text: str, cached: bool) -> None:
    """Call after every LLMClient.embed() invocation."""
    prefix = _month_prefix()
    _increment(f"{prefix}:calls_embed")
    if cached:
        _increment(f"{prefix}:hits_embed")
    tokens = _approx_tokens(text)
    _increment(f"{prefix}:tokens_approx", tokens)
    cost_millicents = int(_cost_per_1k(model) * tokens / 1000 * 100_000)
    if cost_millicents > 0:
        _increment(f"{prefix}:cost_usd_millicents", cost_millicents)
    _check_cap(prefix)


def get_monthly_stats(month: str | None = None) -> dict:
    """Return a dict of aggregated counters for the given month (YYYY-MM).
    Defaults to the current month."""
    prefix = f"llmusage:{month}" if month else _month_prefix()
    calls_complete = cache.get(f"{prefix}:calls_complete", 0)
    hits_complete = cache.get(f"{prefix}:hits_complete", 0)
    calls_embed = cache.get(f"{prefix}:calls_embed", 0)
    hits_embed = cache.get(f"{prefix}:hits_embed", 0)
    tokens = cache.get(f"{prefix}:tokens_approx", 0)
    cost_millicents = cache.get(f"{prefix}:cost_usd_millicents", 0)
    cost_usd = cost_millicents / 100_000

    total_calls = calls_complete + calls_embed
    total_hits = hits_complete + hits_embed
    hit_rate_pct = round(total_hits / total_calls * 100, 1) if total_calls else 0.0
    cap = getattr(settings, "LLM_MONTHLY_USAGE_CAP_USD", 20.0)

    return {
        "month": (month or _month_prefix().split(":")[1]),
        "calls_complete": calls_complete,
        "hits_complete": hits_complete,
        "calls_embed": calls_embed,
        "hits_embed": hits_embed,
        "total_calls": total_calls,
        "total_hits": total_hits,
        "cache_hit_rate_pct": hit_rate_pct,
        "tokens_approx": tokens,
        "estimated_cost_usd": round(cost_usd, 4),
        "monthly_cap_usd": cap,
        "within_cap": cost_usd <= cap,
    }


def get_snapshot() -> dict:
    """Lightweight snapshot suitable for embedding in ScanRun.statistics.
    Returns only the fields relevant to a single run's contribution; callers
    should record before/after and store the delta if they want per-run cost."""
    prefix = _month_prefix()
    return {
        "calls_complete": cache.get(f"{prefix}:calls_complete", 0),
        "hits_complete": cache.get(f"{prefix}:hits_complete", 0),
        "calls_embed": cache.get(f"{prefix}:calls_embed", 0),
        "hits_embed": cache.get(f"{prefix}:hits_embed", 0),
        "estimated_cost_usd": round(cache.get(f"{prefix}:cost_usd_millicents", 0) / 100_000, 4),
    }


# ---------------------------------------------------------------------------
# Internal cap guard
# ---------------------------------------------------------------------------

# Track whether we've already fired a Teams alert this month to avoid spam.
_CAP_ALERT_KEY = "llmusage:cap_alert_fired:{month}"


def _check_cap(prefix: str) -> None:
    """Log a warning (and optionally send a Teams alert) when the monthly
    estimated spend crosses LLM_MONTHLY_USAGE_CAP_USD.  Does NOT block
    requests — a hard block would break demos; the spec asks for visibility."""
    cap = getattr(settings, "LLM_MONTHLY_USAGE_CAP_USD", 20.0)
    cost_millicents = cache.get(f"{prefix}:cost_usd_millicents", 0)
    cost_usd = cost_millicents / 100_000
    if cost_usd <= cap:
        return

    month = prefix.split(":")[1]
    alert_key = _CAP_ALERT_KEY.format(month=month)
    if cache.get(alert_key):
        # Already alerted this month — don't spam.
        return

    logger.warning(
        "LLM_MONTHLY_USAGE_CAP_USD exceeded: estimated spend $%.4f > cap $%.2f",
        cost_usd,
        cap,
    )
    # Fire once and suppress for the rest of the month.
    cache.set(alert_key, True, timeout=_COUNTER_TTL)

    # Optional Teams alert via the global webhook URL.
    teams_url = getattr(settings, "TEAMS_WEBHOOK_URL", "")
    if teams_url:
        try:
            _send_teams_cap_alert(cost_usd, cap, month, teams_url)
        except Exception:
            logger.exception("Failed to send Teams LLM cap alert")


def _send_teams_cap_alert(cost_usd: float, cap: float, month: str, url: str) -> None:
    import requests
    from apps.notifications.teams import build_teams_card

    card = build_teams_card(
        title="⚠️ LLM Monthly Budget Cap Exceeded",
        text=(
            f"SupplyChainIQ estimated LLM spend for **{month}** has exceeded "
            f"the configured cap of **${cap:.2f}**."
        ),
        facts={
            "Estimated spend": f"${cost_usd:.4f}",
            "Monthly cap": f"${cap:.2f}",
            "Month": month,
        },
    )
    response = requests.post(url, json=card, timeout=10)
    if response.status_code >= 300:
        logger.warning("Teams cap alert returned HTTP %s", response.status_code)
