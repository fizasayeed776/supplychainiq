"""
Tests for apps/chat/rag.py — aggregate tool branches.

These tests call maybe_run_aggregate_tool() directly, bypassing the LLM
decision step by patching LLMClient.complete() to return a pre-built
decision dict.  This keeps tests fast, deterministic, and free of LLM
credentials while still exercising the full DB aggregation logic.

Fixtures created per test class:
  workspace, vendor, contracts / invoices / match results as needed.
"""
import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Workspace, Vendor, WorkspaceMembership
from apps.documents.models import Document, Invoice
from apps.matching.models import MatchResult
from apps.chat.rag import maybe_run_aggregate_tool, _format_aggregate_context

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workspace(name="RAG Test WS", slug="rag-test-ws"):
    return Workspace.objects.create(name=name, slug=slug)


def _make_vendor(workspace, name="Test Vendor"):
    return Vendor.objects.create(workspace=workspace, name=name)


def _make_invoice(workspace, vendor, *, inv_num, amount="1000.00",
                  currency="USD", inv_date=None, status="matched"):
    from apps.core.models import Contract
    doc = Document.objects.create(
        workspace=workspace, vendor=vendor, type="invoice",
        file=SimpleUploadedFile(f"{inv_num}.txt", b"x"),
        content_hash=inv_num.ljust(64, "0")[:64],
    )
    inv = Invoice.objects.create(
        document=doc, workspace=workspace, vendor=vendor,
        invoice_number=inv_num,
        invoice_date=inv_date or datetime.date(2026, 1, 15),
        due_date=datetime.date(2026, 2, 15),
        currency=currency,
        total_amount=Decimal(amount),
    )
    MatchResult.objects.create(
        workspace=workspace, invoice=inv,
        status=status, severity="none" if status != "discrepant" else "minor",
        discrepancies=[],
    )
    return inv


def _make_contract(workspace, vendor, *, valid_until, status="active"):
    from apps.core.models import Contract
    return Contract.objects.create(
        workspace=workspace, vendor=vendor,
        valid_from=datetime.date(2024, 1, 1),
        valid_until=valid_until,
        status=status,
    )


def _fake_llm_decision(decision: dict):
    """Return a patch context manager that makes LLMClient.complete() return
    a specific aggregate-tool decision without any LLM call."""
    mock_resp = {"text": "", "json": decision, "cached": True}
    return patch(
        "apps.chat.rag.get_llm_client",
        return_value=MagicMock(
            fast_model="gpt-4o-mini",
            complete=MagicMock(return_value=mock_resp),
        ),
    )


# ---------------------------------------------------------------------------
# expiring_contracts_list
# ---------------------------------------------------------------------------

class ExpiringContractsListTests(TestCase):
    def setUp(self):
        self.ws = _make_workspace()
        self.vendor_a = _make_vendor(self.ws, "Vendor A")
        self.vendor_b = _make_vendor(self.ws, "Vendor B")

        today = timezone.now().date()
        # This contract expires in 14 days — should appear in a 90-day window
        self.near = _make_contract(
            self.ws, self.vendor_a,
            valid_until=today + datetime.timedelta(days=14),
            status="expiring",
        )
        # This contract expires in 200 days — should NOT appear in a 90-day window
        self.far = _make_contract(
            self.ws, self.vendor_b,
            valid_until=today + datetime.timedelta(days=200),
            status="active",
        )

    def test_returns_only_contracts_within_window(self):
        decision = {
            "needs_aggregate": True,
            "metric": "expiring_contracts_list",
            "vendor_name": None,
            "period": None,
            "days": 90,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool(
                "which contracts expire in the next 90 days?", str(self.ws.id)
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["metric"], "expiring_contracts_list")
        self.assertEqual(result["days"], 90)
        vendors_returned = [c["vendor"] for c in result["value"]]
        self.assertIn("Vendor A", vendors_returned)
        self.assertNotIn("Vendor B", vendors_returned)

    def test_respects_days_parameter(self):
        """A 10-day window should return nothing (near contract is 14 days out)."""
        decision = {
            "needs_aggregate": True,
            "metric": "expiring_contracts_list",
            "vendor_name": None,
            "period": None,
            "days": 10,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool(
                "any contracts expiring in the next 10 days?", str(self.ws.id)
            )

        self.assertEqual(result["value"], [])

    def test_vendor_filter_applies(self):
        """When vendor_name is set only that vendor's contracts appear."""
        today = timezone.now().date()
        # Create a second near-expiry contract for vendor_b
        _make_contract(
            self.ws, self.vendor_b,
            valid_until=today + datetime.timedelta(days=20),
            status="expiring",
        )
        decision = {
            "needs_aggregate": True,
            "metric": "expiring_contracts_list",
            "vendor_name": "Vendor A",
            "period": None,
            "days": 90,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool(
                "which Vendor A contracts expire soon?", str(self.ws.id)
            )

        vendors_returned = [c["vendor"] for c in result["value"]]
        self.assertIn("Vendor A", vendors_returned)
        self.assertNotIn("Vendor B", vendors_returned)

    def test_result_ordered_by_valid_until_ascending(self):
        """Earliest-expiring contracts should come first."""
        today = timezone.now().date()
        vendor_c = _make_vendor(self.ws, "Vendor C")
        _make_contract(self.ws, vendor_c,
                       valid_until=today + datetime.timedelta(days=7))
        decision = {
            "needs_aggregate": True,
            "metric": "expiring_contracts_list",
            "vendor_name": None,
            "period": None,
            "days": 90,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool("list expiring contracts", str(self.ws.id))

        dates = [c["valid_until"] for c in result["value"]]
        self.assertEqual(dates, sorted(dates))

    def test_result_includes_status_field(self):
        decision = {
            "needs_aggregate": True,
            "metric": "expiring_contracts_list",
            "vendor_name": None,
            "period": None,
            "days": 90,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool("expiring contracts", str(self.ws.id))

        self.assertTrue(all("status" in c for c in result["value"]))


# ---------------------------------------------------------------------------
# expiring_contracts_count
# ---------------------------------------------------------------------------

class ExpiringContractsCountTests(TestCase):
    def setUp(self):
        self.ws = _make_workspace(slug="rag-count-ws")
        self.vendor = _make_vendor(self.ws, "Count Vendor")
        today = timezone.now().date()
        _make_contract(self.ws, self.vendor,
                       valid_until=today + datetime.timedelta(days=20))
        _make_contract(self.ws, self.vendor,
                       valid_until=today + datetime.timedelta(days=45))
        # Outside 30-day window but inside 90-day window
        _make_contract(self.ws, self.vendor,
                       valid_until=today + datetime.timedelta(days=60))

    def test_count_within_30_days_correct(self):
        """Only the contract expiring in 20 days falls within a 30-day window."""
        decision = {
            "needs_aggregate": True,
            "metric": "expiring_contracts_count",
            "vendor_name": None,
            "period": None,
            "days": 30,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool(
                "how many contracts expire in the next 30 days?", str(self.ws.id)
            )
        self.assertEqual(result["value"], 1)

    def test_count_within_90_days(self):
        """All three contracts fall within a 90-day window."""
        decision = {
            "needs_aggregate": True,
            "metric": "expiring_contracts_count",
            "vendor_name": None,
            "period": None,
            "days": 90,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool(
                "how many contracts expire in the next 90 days?", str(self.ws.id)
            )
        self.assertEqual(result["value"], 3)

    def test_days_defaults_to_90_when_null(self):
        """days=None in the decision should default to 90."""
        decision = {
            "needs_aggregate": True,
            "metric": "expiring_contracts_count",
            "vendor_name": None,
            "period": None,
            "days": None,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool("how many contracts are expiring?", str(self.ws.id))
        self.assertEqual(result["days"], 90)
        self.assertEqual(result["value"], 3)


# ---------------------------------------------------------------------------
# avg_discrepancy_rate
# ---------------------------------------------------------------------------

class AvgDiscrepancyRateTests(TestCase):
    def setUp(self):
        self.ws = _make_workspace(slug="rag-rate-ws")
        self.vendor = _make_vendor(self.ws, "Rate Vendor")

    def test_rate_zero_when_no_invoices(self):
        decision = {
            "needs_aggregate": True,
            "metric": "avg_discrepancy_rate",
            "vendor_name": None,
            "period": None,
            "days": None,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool(
                "what is our average discrepancy rate?", str(self.ws.id)
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["metric"], "avg_discrepancy_rate")
        self.assertEqual(result["value"], 0.0)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["discrepant"], 0)

    def test_rate_between_zero_and_one(self):
        """3 matched + 1 discrepant → rate = 0.25."""
        _make_invoice(self.ws, self.vendor, inv_num="R-001", status="matched")
        _make_invoice(self.ws, self.vendor, inv_num="R-002", status="matched")
        _make_invoice(self.ws, self.vendor, inv_num="R-003", status="matched")
        _make_invoice(self.ws, self.vendor, inv_num="R-004", status="discrepant")

        decision = {
            "needs_aggregate": True,
            "metric": "avg_discrepancy_rate",
            "vendor_name": None,
            "period": None,
            "days": None,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool(
                "what is our average discrepancy rate?", str(self.ws.id)
            )

        self.assertGreaterEqual(result["value"], 0.0)
        self.assertLessEqual(result["value"], 1.0)
        self.assertAlmostEqual(result["value"], 0.25, places=2)
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["discrepant"], 1)

    def test_rate_100_percent_when_all_discrepant(self):
        _make_invoice(self.ws, self.vendor, inv_num="ALL-001", status="discrepant")
        _make_invoice(self.ws, self.vendor, inv_num="ALL-002", status="discrepant")

        decision = {
            "needs_aggregate": True,
            "metric": "avg_discrepancy_rate",
            "vendor_name": None,
            "period": None,
            "days": None,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool("rate?", str(self.ws.id))

        self.assertAlmostEqual(result["value"], 1.0, places=4)

    def test_vendor_filter_scopes_rate(self):
        """Rate for vendor A must not be polluted by vendor B's invoices.
        Vendor names are chosen so that vendor_a's name is NOT a substring
        of vendor_b's name — icontains must scope to exactly one vendor."""
        # Use names that don't share a common substring
        vendor_a = _make_vendor(self.ws, "Acme Supplies")
        vendor_b = _make_vendor(self.ws, "Zenith Corp")
        _make_invoice(self.ws, vendor_a, inv_num="VS-A-001", status="matched")
        # vendor_b has 2 discrepant invoices — must not affect vendor_a rate
        _make_invoice(self.ws, vendor_b, inv_num="VS-B-001", status="discrepant")
        _make_invoice(self.ws, vendor_b, inv_num="VS-B-002", status="discrepant")

        decision = {
            "needs_aggregate": True,
            "metric": "avg_discrepancy_rate",
            "vendor_name": "Acme Supplies",
            "period": None,
            "days": None,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool(
                "what is Acme Supplies's discrepancy rate?", str(self.ws.id)
            )

        # Only vendor_a's 1 matched invoice in scope → rate = 0.0
        self.assertEqual(result["value"], 0.0)
        self.assertEqual(result["total"], 1)


# ---------------------------------------------------------------------------
# needs_aggregate=False → returns None (no regression)
# ---------------------------------------------------------------------------

class AggregateToolFallThroughTests(TestCase):
    def setUp(self):
        self.ws = _make_workspace(slug="rag-fallthrough-ws")

    def test_returns_none_when_needs_aggregate_false(self):
        """A decision with needs_aggregate=False must return None so the
        caller falls through to document retrieval."""
        decision = {
            "needs_aggregate": False,
            "metric": "none",
            "vendor_name": None,
            "period": None,
            "days": None,
        }
        with _fake_llm_decision(decision):
            result = maybe_run_aggregate_tool(
                "what does the NDA say about confidentiality?", str(self.ws.id)
            )

        self.assertIsNone(result)

    def test_returns_none_when_json_is_empty(self):
        """If the LLM returns no JSON at all, default to needs_aggregate=False."""
        mock_resp = {"text": "", "json": None, "cached": False}
        with patch(
            "apps.chat.rag.get_llm_client",
            return_value=MagicMock(
                fast_model="gpt-4o-mini",
                complete=MagicMock(return_value=mock_resp),
            ),
        ):
            result = maybe_run_aggregate_tool("tell me about the supplier terms", str(self.ws.id))

        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _format_aggregate_context — rendering helper unit tests
# ---------------------------------------------------------------------------

class FormatAggregateContextTests(TestCase):
    def test_expiring_contracts_list_renders_bullets(self):
        agg = {
            "metric": "expiring_contracts_list",
            "days": 90,
            "value": [
                {"vendor": "Acme Ltd", "valid_until": "2026-10-01", "status": "expiring"},
                {"vendor": "Beta Corp", "valid_until": "2026-11-15", "status": "active"},
            ],
        }
        text = _format_aggregate_context(agg)
        self.assertIn("Acme Ltd", text)
        self.assertIn("2026-10-01", text)
        self.assertIn("90", text)
        # Should be human-readable bullets, not raw dict repr
        self.assertNotIn("{'vendor'", text)

    def test_expiring_contracts_list_empty(self):
        agg = {"metric": "expiring_contracts_list", "days": 30, "value": []}
        text = _format_aggregate_context(agg)
        self.assertIn("No contracts", text)
        self.assertIn("30", text)

    def test_expiring_contracts_count_renders_plainly(self):
        agg = {"metric": "expiring_contracts_count", "value": 5, "days": 90}
        text = _format_aggregate_context(agg)
        self.assertIn("5", text)
        self.assertIn("90", text)

    def test_avg_discrepancy_rate_shows_percentage(self):
        agg = {
            "metric": "avg_discrepancy_rate",
            "value": 0.125,
            "total": 8,
            "discrepant": 1,
        }
        text = _format_aggregate_context(agg)
        self.assertIn("12.5%", text)
        self.assertIn("8", text)
        self.assertIn("1", text)

    def test_total_spend_renders(self):
        agg = {"metric": "total_spend", "value": 45000.0, "invoice_count": 12}
        text = _format_aggregate_context(agg)
        self.assertIn("45000", text)
        self.assertIn("12", text)


# ---------------------------------------------------------------------------
# answer_question() citation filtering — the four required scenarios
# ---------------------------------------------------------------------------

def _make_chunk(workspace, vendor, *, position, text):
    """Create a real Chunk row (with a zero-vector embedding) for use in
    citation-filtering tests.  pgvector accepts a list of floats, so we
    supply a 1536-dim zero vector to satisfy the NOT NULL constraint without
    needing a real embedding call."""
    from apps.chat.models import Chunk
    doc = Document.objects.create(
        workspace=workspace, vendor=vendor, type="invoice",
        file=SimpleUploadedFile(f"chunk-doc-{position}.txt", b"x"),
        content_hash=f"chunk{position}".ljust(64, "0")[:64],
    )
    return Chunk.objects.create(
        document=doc,
        text=text,
        embedding=[0.0] * 1536,
        position=position,
    )


def _fake_answer_llm(answer_text: str):
    """Return a patch target that makes *both* LLM calls (aggregate decision
    + answer generation) return deterministic, non-LLM responses:
      - The aggregate-tool call gets needs_aggregate=False so retrieval is used.
      - The answer call returns answer_text.
    Both calls go through the same mock client; we distinguish them by
    checking the system prompt argument."""
    def _complete(system_prompt, user_prompt, model=None, json_schema=None):
        if json_schema is not None:
            # This is the aggregate-tool decision call
            return {"text": "", "json": {"needs_aggregate": False}, "cached": True}
        # This is the answer-generation call
        return {"text": answer_text, "json": None, "cached": True}

    mock_client = MagicMock()
    mock_client.fast_model = "gpt-4o-mini"
    mock_client.complete.side_effect = _complete
    return patch("apps.chat.rag.get_llm_client", return_value=mock_client)


def _fake_hybrid_retrieve(chunks):
    """Patch hybrid_retrieve to return (chunks, {}) without touching pgvector."""
    scores = {str(c.id): 1.0 for c in chunks}
    return patch("apps.chat.rag.hybrid_retrieve", return_value=(chunks, scores))


class CitationFilteringNoMarkersTest(TestCase):
    """When the LLM answer contains no [chunk:N] markers, citations must be []
    even if hybrid_retrieve returned non-empty chunks."""

    def setUp(self):
        self.ws = _make_workspace(slug="cit-no-markers-ws")
        self.vendor = _make_vendor(self.ws, "Filter Vendor A")
        self.chunks = [
            _make_chunk(self.ws, self.vendor, position=0, text="Chunk zero text."),
            _make_chunk(self.ws, self.vendor, position=1, text="Chunk one text."),
            _make_chunk(self.ws, self.vendor, position=2, text="Chunk two text."),
        ]

    def test_no_markers_yields_empty_citations(self):
        from apps.chat.rag import answer_question

        answer_text = "There are 3 contracts expiring in the next 90 days."  # no [chunk:N]

        with _fake_hybrid_retrieve(self.chunks), _fake_answer_llm(answer_text):
            result = answer_question("which contracts expire soon?", str(self.ws.id))

        self.assertEqual(result["citations"], [])
        self.assertEqual(result["answer"], answer_text)


class CitationFilteringPartialMarkersTest(TestCase):
    """When the LLM answer references only [chunk:0] and [chunk:2] out of 4
    retrieved chunks, only those two should appear in citations, in index order."""

    def setUp(self):
        self.ws = _make_workspace(slug="cit-partial-ws")
        self.vendor = _make_vendor(self.ws, "Filter Vendor B")
        self.chunks = [
            _make_chunk(self.ws, self.vendor, position=0, text="Alpha clause text."),
            _make_chunk(self.ws, self.vendor, position=1, text="Beta clause text."),
            _make_chunk(self.ws, self.vendor, position=2, text="Gamma clause text."),
            _make_chunk(self.ws, self.vendor, position=3, text="Delta clause text."),
        ]

    def test_only_referenced_chunks_are_cited(self):
        from apps.chat.rag import answer_question

        answer_text = (
            "Per [chunk:0] the payment terms are net-30. "
            "Additionally, [chunk:2] specifies a 5% late fee."
        )

        with _fake_hybrid_retrieve(self.chunks), _fake_answer_llm(answer_text):
            result = answer_question("what are the payment terms?", str(self.ws.id))

        cited_ids = [c["chunk_id"] for c in result["citations"]]
        self.assertEqual(len(cited_ids), 2)
        self.assertEqual(cited_ids[0], str(self.chunks[0].id))
        self.assertEqual(cited_ids[1], str(self.chunks[2].id))
        # chunks 1 and 3 must not appear
        self.assertNotIn(str(self.chunks[1].id), cited_ids)
        self.assertNotIn(str(self.chunks[3].id), cited_ids)


class CitationFilteringAggregateEndToEndTest(TestCase):
    """A contract-expiry aggregate question answered purely from the tool result
    must return citations: [] end-to-end, even though hybrid_retrieve returns
    non-empty chunks.  Re-uses the ExpiringContractsListTests fixture pattern."""

    def setUp(self):
        self.ws = _make_workspace(slug="cit-agg-e2e-ws")
        self.vendor = _make_vendor(self.ws, "Expiry Vendor")

        today = timezone.now().date()
        import datetime as _dt
        from apps.core.models import Contract
        Contract.objects.create(
            workspace=self.ws, vendor=self.vendor,
            valid_from=_dt.date(2024, 1, 1),
            valid_until=today + _dt.timedelta(days=14),
            status="expiring",
        )
        # A chunk that could be spuriously cited
        self.spurious_chunk = _make_chunk(
            self.ws, self.vendor, position=0, text="Some contract boilerplate."
        )

    def test_aggregate_answer_has_no_citations(self):
        from apps.chat.rag import answer_question

        aggregate_decision = {
            "needs_aggregate": True,
            "metric": "expiring_contracts_list",
            "vendor_name": None,
            "period": None,
            "days": 90,
        }
        # LLM answer references no chunks — it was answered from the tool result
        answer_text = "• Expiry Vendor — expires in 14 days (expiring)"

        def _complete(system_prompt, user_prompt, model=None, json_schema=None):
            if json_schema is not None:
                return {"text": "", "json": aggregate_decision, "cached": True}
            return {"text": answer_text, "json": None, "cached": True}

        mock_client = MagicMock()
        mock_client.fast_model = "gpt-4o-mini"
        mock_client.complete.side_effect = _complete

        with (
            _fake_hybrid_retrieve([self.spurious_chunk]),
            patch("apps.chat.rag.get_llm_client", return_value=mock_client),
        ):
            result = answer_question(
                "which contracts expire in the next 90 days?", str(self.ws.id)
            )

        self.assertEqual(result["citations"], [],
                         "Aggregate-only answer must produce no citation chips")


class CitationFilteringDocRetrievalRegressionTest(TestCase):
    """Document-retrieval-only path: when the LLM references chunks normally,
    citations must still be non-empty (no regression from the fix)."""

    def setUp(self):
        self.ws = _make_workspace(slug="cit-regression-ws")
        self.vendor = _make_vendor(self.ws, "Regression Vendor")
        self.chunks = [
            _make_chunk(self.ws, self.vendor, position=0, text="Net-30 payment terms apply."),
            _make_chunk(self.ws, self.vendor, position=1, text="Liability is capped at $10k."),
        ]

    def test_normal_retrieval_answer_returns_citations(self):
        from apps.chat.rag import answer_question

        # LLM references both chunks
        answer_text = (
            "The payment terms are net-30 [chunk:0]. "
            "Liability is capped at $10,000 [chunk:1]."
        )

        with _fake_hybrid_retrieve(self.chunks), _fake_answer_llm(answer_text):
            result = answer_question("what are the payment terms?", str(self.ws.id))

        self.assertEqual(len(result["citations"]), 2)
        cited_ids = {c["chunk_id"] for c in result["citations"]}
        self.assertIn(str(self.chunks[0].id), cited_ids)
        self.assertIn(str(self.chunks[1].id), cited_ids)
        # Snippets should be non-empty
        for citation in result["citations"]:
            self.assertTrue(citation["snippet"])
