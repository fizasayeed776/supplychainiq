"""
Tests for apps/agents/usage.py — LLM usage tracking.

Spec requirement: "Add a test asserting the cache-hit counter increments
correctly on repeated identical prompts."

These tests use Django's LocMemCache (the default test cache backend) so
they run without Redis.  The _increment helper falls back to get/set when
cache.incr raises an exception, which LocMemCache does — that path is also
exercised here.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "usage-test",
    }
}


@override_settings(CACHES=LOCMEM_CACHE, LLM_MONTHLY_USAGE_CAP_USD=50.0)
class UsageCounterTest(TestCase):
    """Counter increment and cache-hit tracking."""

    def setUp(self):
        # Clear the LocMemCache between tests.
        from django.core.cache import cache
        cache.clear()

    # ------------------------------------------------------------------
    # record_complete
    # ------------------------------------------------------------------

    def test_complete_miss_increments_calls(self):
        from apps.agents.usage import record_complete, get_monthly_stats

        record_complete("gpt-4o-mini", "hello world", cached=False)
        stats = get_monthly_stats()
        self.assertEqual(stats["calls_complete"], 1)
        self.assertEqual(stats["hits_complete"], 0)

    def test_complete_hit_increments_both_calls_and_hits(self):
        from apps.agents.usage import record_complete, get_monthly_stats

        record_complete("gpt-4o-mini", "same prompt", cached=False)
        record_complete("gpt-4o-mini", "same prompt", cached=True)   # second call is a cache hit

        stats = get_monthly_stats()
        self.assertEqual(stats["calls_complete"], 2)
        self.assertEqual(stats["hits_complete"], 1)

    def test_cache_hit_rate_calculation(self):
        from apps.agents.usage import record_complete, get_monthly_stats

        # 3 misses, 2 hits → 2/5 = 40 %
        for _ in range(3):
            record_complete("gpt-4o-mini", "p", cached=False)
        for _ in range(2):
            record_complete("gpt-4o-mini", "p", cached=True)

        stats = get_monthly_stats()
        self.assertEqual(stats["total_calls"], 5)
        self.assertEqual(stats["total_hits"], 2)
        self.assertAlmostEqual(stats["cache_hit_rate_pct"], 40.0, places=1)

    # ------------------------------------------------------------------
    # record_embed
    # ------------------------------------------------------------------

    def test_embed_miss_and_hit_tracked_separately(self):
        from apps.agents.usage import record_embed, get_monthly_stats

        record_embed("gemini-embedding-001", "chunk text", cached=False)
        record_embed("gemini-embedding-001", "chunk text", cached=True)

        stats = get_monthly_stats()
        self.assertEqual(stats["calls_embed"], 2)
        self.assertEqual(stats["hits_embed"], 1)

    # ------------------------------------------------------------------
    # Repeated identical prompts increment cache-hit counter (spec test)
    # ------------------------------------------------------------------

    def test_repeated_identical_prompt_cache_hit_counter(self):
        """Spec requirement: repeated identical prompts must increment the
        cache-hit counter.  Simulate LLMClient.complete() being called twice
        with the same inputs — second call returns cached=True."""
        from apps.agents.usage import record_complete, get_monthly_stats

        prompt = "What is the total spend with Vendor A this quarter?"
        model = "gpt-4o-mini"

        # First call: cache miss
        record_complete(model, prompt, cached=False)
        after_first = get_monthly_stats()
        self.assertEqual(after_first["hits_complete"], 0)

        # Second call with same prompt: cache hit
        record_complete(model, prompt, cached=True)
        after_second = get_monthly_stats()
        self.assertEqual(after_second["calls_complete"], 2)
        self.assertEqual(after_second["hits_complete"], 1)
        self.assertAlmostEqual(after_second["cache_hit_rate_pct"], 50.0, places=1)

    # ------------------------------------------------------------------
    # Monthly cap
    # ------------------------------------------------------------------

    @override_settings(CACHES=LOCMEM_CACHE, LLM_MONTHLY_USAGE_CAP_USD=0.0)
    def test_cap_exceeded_logs_warning(self):
        """When spend exceeds the cap a WARNING must be logged."""
        from apps.agents import usage as usage_module

        # Seed a non-zero cost directly.
        from django.core.cache import cache
        from apps.agents.usage import _month_prefix
        prefix = _month_prefix()
        cache.set(f"{prefix}:cost_usd_millicents", 1000, timeout=3600)  # $0.01

        with self.assertLogs("apps.agents.usage", level="WARNING") as log_ctx:
            usage_module._check_cap(prefix)

        self.assertTrue(
            any("LLM_MONTHLY_USAGE_CAP_USD exceeded" in msg for msg in log_ctx.output),
            f"Expected cap warning in logs: {log_ctx.output}",
        )

    @override_settings(CACHES=LOCMEM_CACHE, LLM_MONTHLY_USAGE_CAP_USD=0.0)
    def test_cap_alert_sent_only_once(self):
        """The Teams alert must fire at most once per month (no spam)."""
        from django.core.cache import cache
        from apps.agents.usage import _month_prefix, _check_cap

        prefix = _month_prefix()
        cache.set(f"{prefix}:cost_usd_millicents", 1000, timeout=3600)

        with patch("apps.agents.usage._send_teams_cap_alert") as mock_alert, \
             override_settings(TEAMS_WEBHOOK_URL="http://fake-webhook"):
            _check_cap(prefix)
            _check_cap(prefix)  # second call should be suppressed

        mock_alert.assert_called_once()

    # ------------------------------------------------------------------
    # get_snapshot
    # ------------------------------------------------------------------

    def test_get_snapshot_returns_all_expected_keys(self):
        from apps.agents.usage import record_complete, record_embed, get_snapshot

        record_complete("gpt-4o-mini", "hello", cached=False)
        record_embed("gemini-embedding-001", "chunk", cached=True)

        snap = get_snapshot()
        for key in ("calls_complete", "hits_complete", "calls_embed", "hits_embed", "estimated_cost_usd"):
            self.assertIn(key, snap, f"Missing key '{key}' in snapshot")

    # ------------------------------------------------------------------
    # within_cap flag
    # ------------------------------------------------------------------

    def test_within_cap_true_when_spend_below_cap(self):
        from apps.agents.usage import get_monthly_stats

        stats = get_monthly_stats()
        self.assertTrue(stats["within_cap"])

    @override_settings(CACHES=LOCMEM_CACHE, LLM_MONTHLY_USAGE_CAP_USD=0.001)
    def test_within_cap_false_when_spend_exceeds_cap(self):
        from django.core.cache import cache
        from apps.agents.usage import _month_prefix, get_monthly_stats

        prefix = _month_prefix()
        cache.set(f"{prefix}:cost_usd_millicents", 500, timeout=3600)  # $0.005 > cap $0.001

        stats = get_monthly_stats()
        self.assertFalse(stats["within_cap"])


@override_settings(CACHES=LOCMEM_CACHE)
class LLMClientUsageIntegrationTest(TestCase):
    """Verify LLMClient.complete() wires into the usage tracker correctly."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_complete_cache_hit_increments_hit_counter(self):
        """Two complete() calls with identical inputs: second should register
        a cache hit in the usage tracker."""
        from apps.agents.client import LLMClient
        from apps.agents.usage import get_monthly_stats

        client = LLMClient(
            provider="openai",
            chat_api_key="fake",
            base_url=None,
            fast_model="gpt-4o-mini",
            judge_model="gpt-4o",
            embedding_provider="gemini",
            embedding_api_key="fake",
            embedding_base_url=None,
            embedding_model="gemini-embedding-001",
            embedding_dim=3,
        )

        fake_result = {"text": "answer", "json": None}

        # Patch the provider call so no real HTTP happens.
        with patch.object(client, "_call_provider", return_value=fake_result) as mock_call, \
             patch.object(client, "_acquire_rate_limit_token"):
            client.complete("sys", "same user prompt", model="gpt-4o-mini")
            client.complete("sys", "same user prompt", model="gpt-4o-mini")

        # Provider should only have been called once (second was a cache hit).
        mock_call.assert_called_once()

        stats = get_monthly_stats()
        self.assertEqual(stats["calls_complete"], 2)
        self.assertEqual(stats["hits_complete"], 1)
        self.assertAlmostEqual(stats["cache_hit_rate_pct"], 50.0, places=1)
