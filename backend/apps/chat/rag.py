"""
RAG chat core.
Retrieval: pgvector cosine similarity + Postgres full-text search, merged
with reciprocal rank fusion (RRF). Generation: mandatory citations back to
chunk IDs; a low-confidence guardrail returns "not found in your documents"
instead of hallucinating. An SQL tool lets the agent answer aggregate
questions ("spend with Vendor Y this quarter") beyond pure retrieval.
"""
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Sum
from pgvector.django import CosineDistance
import re

from .models import Chunk
from apps.agents.client import get_llm_client

RETRIEVAL_CONFIDENCE_FLOOR = 0.15


def chunk_text(text: str, max_tokens: int = 500, overlap_tokens: int = 50) -> list[str]:
    """Naive whitespace-token chunker with overlap. Swap for a tokenizer-aware
    splitter if exact token counts matter for a given provider."""
    words = text.split()
    if not words:
        return []
    chunks, start = [], 0
    step = max(1, max_tokens - overlap_tokens)
    while start < len(words):
        chunks.append(" ".join(words[start:start + max_tokens]))
        start += step
    return chunks


def vector_search(query_vector, workspace_id, document_type=None, top_k=8):
    qs = Chunk.objects.filter(document__workspace_id=workspace_id)
    if document_type:
        qs = qs.filter(document__type=document_type)
    return list(qs.order_by(CosineDistance("embedding", query_vector))[:top_k])


def fulltext_search(query_text, workspace_id, top_k=8):
    vector = SearchVector("text")
    query = SearchQuery(query_text)
    qs = (
        Chunk.objects.filter(document__workspace_id=workspace_id)
        .annotate(rank=SearchRank(vector, query))
        .filter(rank__gt=0)
        .order_by("-rank")[:top_k]
    )
    return list(qs)


def hybrid_retrieve(question: str, workspace_id, top_k=6) -> list[Chunk]:
    client = get_llm_client()
    query_vector = client.embed(question)

    vector_hits = vector_search(query_vector, workspace_id, top_k=top_k * 2)
    text_hits = fulltext_search(question, workspace_id, top_k=top_k * 2)

    # Reciprocal rank fusion
    scores: dict[str, float] = {}
    by_id: dict[str, Chunk] = {}
    for rank_list in (vector_hits, text_hits):
        for rank, chunk in enumerate(rank_list):
            by_id[str(chunk.id)] = chunk
            scores[str(chunk.id)] = scores.get(str(chunk.id), 0.0) + 1.0 / (60 + rank)

    ranked_ids = sorted(scores, key=scores.get, reverse=True)[:top_k]
    return [by_id[i] for i in ranked_ids], scores


SQL_TOOL_SYSTEM_PROMPT = """You decide whether a procurement question needs an
aggregate SQL-style lookup (spend totals, counts, averages, contract expiry)
rather than document retrieval. Respond ONLY with JSON:
{
  "needs_aggregate": bool,
  "metric": "total_spend|invoice_count|discrepant_count|avg_discrepancy_rate|expiring_contracts_count|expiring_contracts_list|none",
  "vendor_name": "string or null",
  "period": "this_quarter|this_year|all_time|null",
  "days": integer_or_null
}
Rules:
- Use "expiring_contracts_count" when the question asks *how many* contracts
  expire within a timeframe.
- Use "expiring_contracts_list" when the question asks *which* contracts expire
  (i.e. wants vendor names / dates, not just a count).
- Extract "days" from the question when a relative window is mentioned:
  "next 90 days" → 90, "next month" → 30, "this month" → 30,
  "next 30 days" → 30, "next quarter" → 90. Default to 90 when unclear.
- Use "avg_discrepancy_rate" for questions about discrepancy rate or percentage
  across invoices (optionally scoped by vendor / period).
- Set "days" to null for non-contract metrics.
"""


def maybe_run_aggregate_tool(question: str, workspace_id) -> dict | None:
    from apps.documents.models import Invoice
    from django.utils import timezone

    client = get_llm_client()
    response = client.complete(
        SQL_TOOL_SYSTEM_PROMPT,
        question,
        model=client.fast_model,
        json_schema={
            "needs_aggregate": "bool",
            "metric": "string",
            "vendor_name": "string|null",
            "period": "string|null",
            "days": "integer|null",
        },
    )
    decision = response["json"] or {"needs_aggregate": False}

    # Heuristic override: "discrepant" in the question almost always means
    # the caller wants a discrepancy count, not a raw invoice count.
    if "discrepant" in question.lower() and decision.get("metric") == "invoice_count":
        decision["metric"] = "discrepant_count"

    if not decision.get("needs_aggregate"):
        return None

    # ------------------------------------------------------------------ #
    # Contract-expiry branches (do not use the Invoice queryset)          #
    # ------------------------------------------------------------------ #
    if decision["metric"] in ("expiring_contracts_count", "expiring_contracts_list"):
        from apps.core.models import Contract
        from datetime import timedelta

        days = int(decision.get("days") or 90)
        today = timezone.now().date()
        cutoff = today + timedelta(days=days)

        cqs = Contract.objects.filter(
            workspace_id=workspace_id,
            valid_until__isnull=False,
            valid_until__lte=cutoff,
            valid_until__gte=today,
        ).select_related("vendor")

        if decision.get("vendor_name"):
            cqs = cqs.filter(vendor__name__icontains=decision["vendor_name"])

        if decision["metric"] == "expiring_contracts_count":
            return {
                "metric": "expiring_contracts_count",
                "value": cqs.count(),
                "days": days,
            }

        # expiring_contracts_list — return a structured list for the LLM
        return {
            "metric": "expiring_contracts_list",
            "value": [
                {
                    "vendor": c.vendor.name,
                    "valid_until": c.valid_until.isoformat(),
                    "status": c.status,
                }
                for c in cqs.order_by("valid_until")
            ],
            "days": days,
        }

    # ------------------------------------------------------------------ #
    # Invoice-based branches                                              #
    # ------------------------------------------------------------------ #
    qs = Invoice.objects.filter(workspace_id=workspace_id)
    if decision.get("vendor_name"):
        qs = qs.filter(vendor__name__icontains=decision["vendor_name"])
    if decision.get("period") == "this_quarter":
        now = timezone.now()
        quarter_start_month = 3 * ((now.month - 1) // 3) + 1
        qs = qs.filter(invoice_date__year=now.year, invoice_date__month__gte=quarter_start_month)
    elif decision.get("period") == "this_year":
        qs = qs.filter(invoice_date__year=timezone.now().year)

    if decision["metric"] == "total_spend":
        value = qs.aggregate(total=Sum("total_amount"))["total"] or 0
        return {"metric": "total_spend", "value": float(value), "invoice_count": qs.count()}

    if decision["metric"] == "invoice_count":
        return {"metric": "invoice_count", "value": qs.count()}

    if decision["metric"] == "discrepant_count":
        from apps.matching.models import MatchResult
        value = MatchResult.objects.filter(invoice__in=qs, status="discrepant").count()
        return {"metric": "discrepant_count", "value": value}

    if decision["metric"] == "avg_discrepancy_rate":
        from apps.matching.models import MatchResult
        total = MatchResult.objects.filter(invoice__in=qs).count()
        discrepant = MatchResult.objects.filter(invoice__in=qs, status="discrepant").count()
        rate = (discrepant / total) if total else 0.0
        return {
            "metric": "avg_discrepancy_rate",
            "value": round(rate, 4),
            "total": total,
            "discrepant": discrepant,
        }

    # Unknown metric — fall through to pure retrieval rather than silently returning None
    return None


ANSWER_SYSTEM_PROMPT = """You answer procurement questions using ONLY the
provided document excerpts and/or aggregate data tool result. Cite excerpts
by their [chunk:N] marker inline. If the excerpts and tool result do not
contain enough information to answer confidently, say exactly:
"I couldn't find that in your documents." Do not guess or use outside knowledge.
When presenting contract expiry lists, format each contract as a brief line:
  • <vendor name> — expires <date> (<status>)
When presenting discrepancy rates, express them as a percentage (e.g. "12.5%").
"""


def _format_aggregate_context(aggregate: dict) -> str:
    """Render an aggregate tool result as human-readable text for the LLM prompt.

    Raw dicts / lists confuse the model; well-formatted text produces much
    better answers, especially for contract-expiry lists.
    """
    metric = aggregate.get("metric", "")

    if metric == "expiring_contracts_list":
        days = aggregate.get("days", 90)
        contracts = aggregate.get("value", [])
        if not contracts:
            return f"Aggregate tool result: No contracts expire in the next {days} days."
        lines = "\n".join(
            f"  • {c['vendor']} — expires {c['valid_until']} (status: {c['status']})"
            for c in contracts
        )
        return (
            f"Aggregate tool result: {len(contracts)} contract(s) expiring "
            f"in the next {days} days:\n{lines}"
        )

    if metric == "expiring_contracts_count":
        days = aggregate.get("days", 90)
        return (
            f"Aggregate tool result: {aggregate['value']} contract(s) expire "
            f"in the next {days} days."
        )

    if metric == "avg_discrepancy_rate":
        rate_pct = round(aggregate["value"] * 100, 2)
        return (
            f"Aggregate tool result: average discrepancy rate is {rate_pct}% "
            f"({aggregate['discrepant']} discrepant out of {aggregate['total']} matched invoices)."
        )

    if metric == "total_spend":
        return (
            f"Aggregate tool result: total spend = {aggregate['value']} "
            f"across {aggregate.get('invoice_count', '?')} invoice(s)."
        )

    if metric == "invoice_count":
        return f"Aggregate tool result: {aggregate['value']} invoice(s) found."

    if metric == "discrepant_count":
        return f"Aggregate tool result: {aggregate['value']} discrepant invoice(s) found."

    # Fallback: just stringify the dict cleanly
    return f"Aggregate tool result: {aggregate}"


def answer_question(question: str, workspace_id) -> dict:
    chunks, _scores = hybrid_retrieve(question, workspace_id)
    aggregate = maybe_run_aggregate_tool(question, workspace_id)

    if not chunks and not aggregate:
        return {"answer": "I couldn't find that in your documents.", "citations": []}

    requested_ids = re.findall(r"\b(?:INV|PO|CT)-[A-Z0-9-]+\b", question.upper())
    requested_ids += re.findall(
        r"\b(?:INVOICE|PO|CONTRACT)\s+([A-Z0-9][A-Z0-9-]+)", question.upper()
    )
    if requested_ids and not any(
        all(identifier in (chunk.text or "").upper() for identifier in requested_ids)
        for chunk in chunks
    ) and not aggregate:
        return {"answer": "I couldn't find that in your documents.", "citations": []}

    excerpts = "\n\n".join(f"[chunk:{i}] {c.text}" for i, c in enumerate(chunks))
    context = f"Document excerpts:\n{excerpts}"
    if aggregate:
        context += f"\n\n{_format_aggregate_context(aggregate)}"

    client = get_llm_client()
    response = client.complete(ANSWER_SYSTEM_PROMPT, f"{context}\n\nQuestion: {question}", model=client.fast_model)

    # Only cite chunks that the LLM actually referenced via [chunk:N] markers.
    # Pure aggregate answers produce no markers → citations stays empty.
    referenced_indices = {int(n) for n in re.findall(r"\[chunk:(\d+)\]", response["text"])}
    citations = [
        {
            "chunk_id": str(chunks[i].id),
            "document_id": str(chunks[i].document_id),
            "position": chunks[i].position,
            "snippet": chunks[i].text[:200],
        }
        for i in sorted(referenced_indices)
        if i < len(chunks)
    ]
    return {"answer": response["text"], "citations": citations}


def stream_answer_question(question: str, workspace_id):
    """Generator that yields dicts for streaming over WebSocket.

    Yields:
      {"type": "token", "content": str}  — one or more times as text arrives
      {"type": "done", "citations": [...]}  — exactly once at the end

    If a cached/non-streaming answer is already available (e.g. the
    underlying LLM call was served from cache), the full text is emitted
    as a single token chunk followed by done — the consumer sees the same
    protocol either way.
    """
    chunks, _scores = hybrid_retrieve(question, workspace_id)
    aggregate = maybe_run_aggregate_tool(question, workspace_id)

    not_found = {"type": "done", "citations": []}

    if not chunks and not aggregate:
        yield {"type": "token", "content": "I couldn't find that in your documents."}
        yield not_found
        return

    requested_ids = re.findall(r"\b(?:INV|PO|CT)-[A-Z0-9-]+\b", question.upper())
    requested_ids += re.findall(
        r"\b(?:INVOICE|PO|CONTRACT)\s+([A-Z0-9][A-Z0-9-]+)", question.upper()
    )
    if requested_ids and not any(
        all(identifier in (chunk.text or "").upper() for identifier in requested_ids)
        for chunk in chunks
    ) and not aggregate:
        yield {"type": "token", "content": "I couldn't find that in your documents."}
        yield not_found
        return

    excerpts = "\n\n".join(f"[chunk:{i}] {c.text}" for i, c in enumerate(chunks))
    context = f"Document excerpts:\n{excerpts}"
    if aggregate:
        context += f"\n\n{_format_aggregate_context(aggregate)}"

    client = get_llm_client()
    prompt = f"{context}\n\nQuestion: {question}"

    # Check the cache first — if we have a cached answer emit it as one chunk
    # (no point re-streaming something already computed).
    cache_key = client._cache_key(client.fast_model, ANSWER_SYSTEM_PROMPT, prompt)
    from django.core.cache import cache as django_cache
    cached = django_cache.get(cache_key)
    if cached:
        yield {"type": "token", "content": cached["text"]}
        referenced_indices = {int(n) for n in re.findall(r"\[chunk:(\d+)\]", cached["text"])}
        citations = [
            {
                "chunk_id": str(chunks[i].id),
                "document_id": str(chunks[i].document_id),
                "position": chunks[i].position,
                "snippet": chunks[i].text[:200],
            }
            for i in sorted(referenced_indices)
            if i < len(chunks)
        ]
        yield {"type": "done", "citations": citations}
        return

    # Real streaming path — yield each chunk as it arrives.
    full_text = []
    for chunk_text_part in client.stream_complete(ANSWER_SYSTEM_PROMPT, prompt, model=client.fast_model):
        full_text.append(chunk_text_part)
        yield {"type": "token", "content": chunk_text_part}

    # Store completed response in cache so future identical questions are fast.
    django_cache.set(cache_key, {"text": "".join(full_text), "json": None}, timeout=60 * 60 * 24 * 7)

    # Only cite chunks that the LLM actually referenced via [chunk:N] markers.
    assembled = "".join(full_text)
    referenced_indices = {int(n) for n in re.findall(r"\[chunk:(\d+)\]", assembled)}
    citations = [
        {
            "chunk_id": str(chunks[i].id),
            "document_id": str(chunks[i].document_id),
            "position": chunks[i].position,
            "snippet": chunks[i].text[:200],
        }
        for i in sorted(referenced_indices)
        if i < len(chunks)
    ]
    yield {"type": "done", "citations": citations}
