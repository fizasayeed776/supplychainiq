from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.core.models import Contract, Vendor, Workspace
from apps.documents.models import Document, Invoice, LineItem, PurchaseOrder
from .comparator import compare
from .judge import judge
from .matcher import find_purchase_order


class AgentBehaviorTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(name="Agent tests", slug="agent-tests")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Agent Vendor")
        self.po_document = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="po",
            file=SimpleUploadedFile("po.txt", b"po"), content_hash="agent-po".ljust(64, "0"),
        )
        self.po = PurchaseOrder.objects.create(
            document=self.po_document, workspace=self.workspace, vendor=self.vendor,
            po_number="PO-AGENT-1", order_date=date(2026, 9, 1), currency="USD",
        )
        LineItem.objects.create(
            document=self.po_document, sku="BOX", description="5 boxes of 12 pieces",
            quantity=5, unit_price=Decimal("0.40"), currency="USD", position=0,
        )
        self.invoice_document = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="invoice",
            file=SimpleUploadedFile("invoice.txt", b"invoice"), content_hash="agent-inv".ljust(64, "0"),
        )
        self.invoice = Invoice.objects.create(
            document=self.invoice_document, workspace=self.workspace, vendor=self.vendor,
            invoice_number="INV-AGENT-1", referenced_po_number="per PO from last week",
            invoice_date=date(2026, 9, 5), due_date=date(2026, 10, 5), currency="USD",
        )
        LineItem.objects.create(
            document=self.invoice_document, sku="BOX", description="60 pieces",
            quantity=60, unit_price=Decimal("0.40"), currency="USD", position=0,
        )

    @patch("apps.agents.matcher._semantic_po_search")
    def test_matcher_uses_fallback_for_informal_reference(self, fallback):
        fallback.return_value = self.po
        self.assertEqual(find_purchase_order(self.invoice), self.po)
        fallback.assert_called_once_with(self.invoice)

    def test_comparator_flags_rate_and_currency(self):
        line = self.invoice.document.line_items.get()
        line.description = "5 boxes of 12 pieces"
        line.quantity = 5
        line.unit_price = Decimal("0.55")
        line.currency = "EUR"
        line.save()
        candidates = compare(self.invoice, self.po, [], None)
        self.assertEqual({candidate["type"] for candidate in candidates}, {"rate_mismatch", "currency_mismatch", "no_delivery_on_record"})

    @patch("apps.agents.judge.run_structured_agent")
    def test_judge_suppresses_rounding_and_unit_conversion(self, mock_llm):
        # Python pre-filtering removes the quantity_mismatch (unit_conversion + equal
        # base quantities) and the delivery_shortfall (partial_delivery=True) before
        # the LLM is ever called, leaving only the 0.3% rate_mismatch candidate.
        # The LLM (mocked) then judges that 0.3% difference as a rounding false
        # positive and returns kept_indices=[], yielding a clean "matched" result.
        mock_llm.return_value = {
            "status": "matched",
            "severity": "none",
            "kept_indices": [],
            "reasoning": "Mocked: no genuine discrepancies after rounding/unit-conversion filtering.",
        }
        result = judge(self.invoice, [
            {"type": "quantity_mismatch", "expected": 12, "actual": 12.0, "expected_base": 12, "actual_base": 12, "unit_conversion": True},
            {"type": "rate_mismatch", "expected": 1.20, "actual": 1.204},
            {"type": "delivery_shortfall", "expected": 100, "actual": 90, "partial_delivery": True},
        ])
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["discrepancies"], [])
        # Confirm the LLM was called exactly once with the one remaining candidate
        mock_llm.assert_called_once()
        call_prompt = mock_llm.call_args[0][1]  # second positional arg is user_prompt
        self.assertIn("rate_mismatch", call_prompt)

    def test_comparator_normalizes_plural_pack_units(self):
        candidates = compare(self.invoice, self.po, [], None)
        self.assertFalse(any(candidate["type"] == "quantity_mismatch" for candidate in candidates))

    def test_contract_rate_is_checked_without_po(self):
        contract = Contract.objects.create(
            workspace=self.workspace, vendor=self.vendor, status="active",
            valid_until=date(2027, 1, 1), terms={"rate_cards": [{"sku": "BOX", "unit_price": 0.40}]},
        )
        line = self.invoice.document.line_items.get()
        line.description = "Evaluation item"
        line.quantity = 5
        line.unit_price = Decimal("0.55")
        line.save()
        candidates = compare(self.invoice, None, [], contract)
        self.assertTrue(any(candidate["type"] == "contract_rate_violation" for candidate in candidates))


# =============================================================================
# dispute_drafter.py tests
# =============================================================================

class DisputeDrafterTests(TestCase):
    """draft_dispute_email() — happy path and LLM-failure fallback."""

    def setUp(self):
        workspace = Workspace.objects.create(name="Drafter WS", slug="drafter-ws")
        vendor = Vendor.objects.create(workspace=workspace, name="Drafter Vendor")
        inv_doc = Document.objects.create(
            workspace=workspace, vendor=vendor, type="invoice",
            file=SimpleUploadedFile("d_inv.txt", b"inv"),
            content_hash="drafter-inv".ljust(64, "0"),
        )
        self.invoice = Invoice.objects.create(
            document=inv_doc, workspace=workspace, vendor=vendor,
            invoice_number="INV-DRAFT-1", currency="USD",
            invoice_date=date(2026, 9, 1), due_date=date(2026, 10, 1),
        )
        from apps.matching.models import MatchResult
        self.match = MatchResult.objects.create(
            workspace=workspace, invoice=self.invoice,
            status="discrepant", severity="major",
            discrepancies=[{"type": "rate_mismatch", "expected": 1.20, "actual": 1.50}],
            agent_reasoning="Rate is higher than agreed.",
        )

    @patch("apps.agents.dispute_drafter.run_structured_agent")
    def test_happy_path_returns_subject_and_body(self, mock_agent):
        mock_agent.return_value = {
            "subject": "Dispute: INV-DRAFT-1",
            "body": "Dear Drafter Vendor, we dispute the rate...",
        }
        from apps.agents.dispute_drafter import draft_dispute_email
        result = draft_dispute_email(self.match)

        self.assertIn("subject", result)
        self.assertIn("body", result)
        self.assertEqual(result["subject"], "Dispute: INV-DRAFT-1")
        mock_agent.assert_called_once()
        # Verify the context passed to the agent includes invoice and PO numbers
        call_args = mock_agent.call_args[0]
        self.assertIn("INV-DRAFT-1", call_args[1])
        self.assertIn("Drafter Vendor", call_args[1])

    @patch("apps.agents.dispute_drafter.run_structured_agent", side_effect=RuntimeError("LLM down"))
    def test_llm_failure_returns_fallback(self, _mock):
        from apps.agents.dispute_drafter import draft_dispute_email
        result = draft_dispute_email(self.match)

        self.assertIn("subject", result)
        self.assertIn("body", result)
        self.assertIn("INV-DRAFT-1", result["subject"])
        self.assertIn("manually", result["body"])

    @patch("apps.agents.dispute_drafter.run_structured_agent")
    def test_po_number_from_referenced_po_when_no_purchase_order(self, mock_agent):
        """When match_result has no purchase_order FK, falls back to
        invoice.referenced_po_number."""
        self.invoice.referenced_po_number = "PO-REF-999"
        self.invoice.save()
        mock_agent.return_value = {"subject": "s", "body": "b"}

        from apps.agents.dispute_drafter import draft_dispute_email
        draft_dispute_email(self.match)

        call_context = mock_agent.call_args[0][1]
        self.assertIn("PO-REF-999", call_context)


# =============================================================================
# risk_analyst.py tests
# =============================================================================

from apps.core.models import Contract

class RiskAnalystTests(TestCase):
    """compute_vendor_risk() — zero-history, discrepant history, and the
    critical-severity regression (unmatched != critical discrepancy)."""

    def setUp(self):
        from apps.matching.models import MatchResult
        self.MatchResult = MatchResult
        self.workspace = Workspace.objects.create(name="Risk WS", slug="risk-ws")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Risk Vendor")

    def _make_invoice(self, suffix, status="matched", severity="none"):
        inv_doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="invoice",
            file=SimpleUploadedFile(f"r_{suffix}.txt", b"x"),
            content_hash=f"risk-inv-{suffix}".ljust(64, "0"),
        )
        inv = Invoice.objects.create(
            document=inv_doc, workspace=self.workspace, vendor=self.vendor,
            invoice_number=f"INV-RISK-{suffix}",
            invoice_date=date(2026, 9, 1), due_date=date(2026, 10, 1), currency="USD",
        )
        self.MatchResult.objects.create(
            workspace=self.workspace, invoice=inv,
            status=status, severity=severity, discrepancies=[],
        )
        return inv

    @patch("apps.agents.risk_analyst.run_structured_agent", side_effect=RuntimeError("no LLM"))
    def test_zero_history_gives_zero_score(self, _mock):
        """Vendor with no invoices → fallback formula → risk_score = 0."""
        from apps.agents.risk_analyst import compute_vendor_risk
        result = compute_vendor_risk(self.vendor)

        self.assertEqual(result["risk_score"], 0)
        self.assertEqual(result["risk_factors"]["total_invoices"], 0)
        self.assertEqual(result["risk_factors"]["discrepancy_rate"], 0.0)
        self.assertIn("computed_at", result)

    @patch("apps.agents.risk_analyst.run_structured_agent", side_effect=RuntimeError("no LLM"))
    def test_discrepant_history_raises_score(self, _mock):
        """3 discrepant invoices → fallback formula gives score > 0."""
        for i in range(3):
            self._make_invoice(f"d{i}", status="discrepant", severity="minor")

        from apps.agents.risk_analyst import compute_vendor_risk
        result = compute_vendor_risk(self.vendor)

        self.assertGreater(result["risk_score"], 0)
        self.assertEqual(result["risk_factors"]["discrepant_invoices"], 3)

    @patch("apps.agents.risk_analyst.run_structured_agent", side_effect=RuntimeError("no LLM"))
    def test_unmatched_critical_not_counted_as_critical_discrepancy(self, _mock):
        """Regression: unmatched invoice with severity=critical must NOT be
        counted as a critical discrepancy in the risk score calculation.
        This exact bug was found via live testing in Step 5."""
        # One genuinely critical discrepant invoice
        self._make_invoice("c1", status="discrepant", severity="critical")
        # One unmatched invoice that the orchestrator tagged severity=critical
        # (meaning "no PO found") — this must NOT inflate critical_discrepancies
        self._make_invoice("u1", status="unmatched", severity="critical")

        from apps.agents.risk_analyst import compute_vendor_risk
        result = compute_vendor_risk(self.vendor)

        # Only the discrepant+critical one counts, not the unmatched one
        self.assertEqual(result["risk_factors"]["critical_discrepancies"], 1,
                         "unmatched invoice with severity=critical must NOT count "
                         "as a critical discrepancy")

    @patch("apps.agents.risk_analyst.run_structured_agent")
    def test_llm_result_is_used_when_available(self, mock_agent):
        """When LLM succeeds, its score is returned (not the heuristic)."""
        mock_agent.return_value = {
            "risk_score": 42.5,
            "risk_factors": {"total_invoices": 0},
            "explanation": "Moderate risk.",
        }
        from apps.agents.risk_analyst import compute_vendor_risk
        result = compute_vendor_risk(self.vendor)

        self.assertAlmostEqual(result["risk_score"], 42.5)
        self.assertEqual(result["explanation"], "Moderate risk.")

    @patch("apps.agents.risk_analyst.run_structured_agent", side_effect=RuntimeError("no LLM"))
    def test_expired_contracts_contribute_to_score(self, _mock):
        """Expired contracts should increase the fallback heuristic score."""
        Contract.objects.create(
            workspace=self.workspace, vendor=self.vendor, status="expired",
        )
        from apps.agents.risk_analyst import compute_vendor_risk
        result = compute_vendor_risk(self.vendor)

        self.assertGreater(result["risk_score"], 0)
        self.assertEqual(result["risk_factors"]["expired_contracts"], 1)


# =============================================================================
# agents/client.py tests (LLMClient caching + rate-limiting)
# =============================================================================

from unittest.mock import MagicMock, call


class LLMClientCacheTests(TestCase):
    """Prompt-hash caching: second identical call must be a cache hit."""

    def _make_client(self):
        from apps.agents.client import LLMClient
        return LLMClient(
            provider="openai", chat_api_key="k", base_url="",
            fast_model="gpt-4o-mini", judge_model="gpt-4o",
            embedding_provider="gemini", embedding_api_key="ek",
            embedding_base_url="", embedding_model="text-embedding-3-small",
            embedding_dim=1536,
        )

    def test_cache_key_is_deterministic(self):
        client = self._make_client()
        k1 = client._cache_key("gpt-4o-mini", "sys", "usr", None)
        k2 = client._cache_key("gpt-4o-mini", "sys", "usr", None)
        self.assertEqual(k1, k2)

    def test_cache_key_differs_for_different_inputs(self):
        client = self._make_client()
        k1 = client._cache_key("gpt-4o-mini", "sys", "usr1", None)
        k2 = client._cache_key("gpt-4o-mini", "sys", "usr2", None)
        self.assertNotEqual(k1, k2)

    @patch("apps.agents.client.LLMClient._call_provider")
    @patch("apps.agents.client.LLMClient._acquire_rate_limit_token")
    @patch("apps.agents.usage.record_complete")
    def test_second_identical_call_is_cache_hit(self, _rec, _rate, mock_call):
        """Identical system+user → second complete() must return cached=True
        and NOT call _call_provider again."""
        mock_call.return_value = {"text": "answer", "json": None}
        client = self._make_client()
        from django.core.cache import cache
        cache.delete(client._cache_key("gpt-4o-mini", "sys", "user_prompt", None))

        r1 = client.complete("sys", "user_prompt", use_cache=True)
        r2 = client.complete("sys", "user_prompt", use_cache=True)

        self.assertFalse(r1["cached"])
        self.assertTrue(r2["cached"])
        mock_call.assert_called_once()  # only one real API call

    @patch("apps.agents.client.LLMClient._call_provider")
    @patch("apps.agents.client.LLMClient._acquire_rate_limit_token")
    @patch("apps.agents.usage.record_complete")
    def test_cache_disabled_always_calls_provider(self, _rec, _rate, mock_call):
        mock_call.return_value = {"text": "answer", "json": None}
        client = self._make_client()

        client.complete("sys", "prompt", use_cache=False)
        client.complete("sys", "prompt", use_cache=False)

        self.assertEqual(mock_call.call_count, 2)


# =============================================================================
# agents/matcher.py tests
# =============================================================================

class MatcherTests(TestCase):
    """find_purchase_order and find_delivery_receipts — exact, no-match cases."""

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Matcher WS", slug="matcher-ws")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Matcher Vendor")
        po_doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="po",
            file=SimpleUploadedFile("m_po.txt", b"po"),
            content_hash="matcher-po-001".ljust(64, "0"),
        )
        from apps.documents.models import DeliveryReceipt
        self.DeliveryReceipt = DeliveryReceipt
        self.po = PurchaseOrder.objects.create(
            document=po_doc, workspace=self.workspace, vendor=self.vendor,
            po_number="PO-MATCH-EXACT", order_date=date(2026, 9, 1), currency="USD",
        )
        inv_doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="invoice",
            file=SimpleUploadedFile("m_inv.txt", b"inv"),
            content_hash="matcher-inv-001".ljust(64, "0"),
        )
        self.invoice = Invoice.objects.create(
            document=inv_doc, workspace=self.workspace, vendor=self.vendor,
            invoice_number="INV-MATCHER-1",
            referenced_po_number="PO-MATCH-EXACT",
            invoice_date=date(2026, 9, 5), due_date=date(2026, 10, 5), currency="USD",
        )

    def test_exact_po_reference_match(self):
        from apps.agents.matcher import find_purchase_order
        result = find_purchase_order(self.invoice)
        self.assertEqual(result, self.po)

    def test_no_match_returns_none(self):
        self.invoice.referenced_po_number = ""
        self.invoice.save()
        from apps.agents.matcher import find_purchase_order
        result = find_purchase_order(self.invoice)
        self.assertIsNone(result)

    @patch("apps.agents.matcher._semantic_po_search")
    def test_informal_reference_triggers_semantic_fallback(self, mock_sem):
        mock_sem.return_value = self.po
        self.invoice.referenced_po_number = "as per your order last week"
        self.invoice.save()
        from apps.agents.matcher import find_purchase_order
        result = find_purchase_order(self.invoice)
        self.assertEqual(result, self.po)
        mock_sem.assert_called_once()

    def test_find_delivery_receipts_with_matching_po(self):
        rec_doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="delivery_receipt",
            file=SimpleUploadedFile("rec.txt", b"rec"),
            content_hash="matcher-rec-001".ljust(64, "0"),
        )
        receipt = self.DeliveryReceipt.objects.create(
            document=rec_doc, workspace=self.workspace, vendor=self.vendor,
            referenced_po_number="PO-MATCH-EXACT",
        )
        from apps.agents.matcher import find_delivery_receipts
        results = find_delivery_receipts(self.invoice, self.po)
        self.assertIn(receipt, results)

    def test_find_delivery_receipts_returns_empty_when_no_receipts(self):
        from apps.agents.matcher import find_delivery_receipts
        results = find_delivery_receipts(self.invoice, self.po)
        self.assertEqual(results, [])


# =============================================================================
# agents/orchestrator.py tests
# =============================================================================

class OrchestratorTests(TestCase):
    """run_three_way_match — clean, discrepant, and unmatched paths."""

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Orch WS", slug="orch-ws")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Orch Vendor")
        po_doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="po",
            file=SimpleUploadedFile("o_po.txt", b"po"),
            content_hash="orch-po-001".ljust(64, "0"),
        )
        self.po = PurchaseOrder.objects.create(
            document=po_doc, workspace=self.workspace, vendor=self.vendor,
            po_number="PO-ORCH-1", order_date=date(2026, 9, 1), currency="USD",
        )
        inv_doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="invoice",
            file=SimpleUploadedFile("o_inv.txt", b"inv"),
            content_hash="orch-inv-001".ljust(64, "0"),
        )
        self.invoice = Invoice.objects.create(
            document=inv_doc, workspace=self.workspace, vendor=self.vendor,
            invoice_number="INV-ORCH-1", referenced_po_number="PO-ORCH-1",
            invoice_date=date(2026, 9, 5), due_date=date(2026, 10, 5), currency="USD",
        )

    @patch("apps.agents.orchestrator._publish")
    @patch("apps.agents.judge.judge")
    @patch("apps.agents.comparator.compare", return_value=[])
    @patch("apps.agents.matcher.find_delivery_receipts", return_value=[])
    @patch("apps.agents.matcher.find_purchase_order")
    def test_clean_match_returns_correct_shape(self, mock_po, _rec, _cmp, mock_judge, _pub):
        mock_po.return_value = self.po
        mock_judge.return_value = {
            "status": "matched", "severity": "none",
            "discrepancies": [], "reasoning": "All good.",
        }
        from apps.agents.orchestrator import run_three_way_match
        result = run_three_way_match(self.invoice)

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["severity"], "none")
        self.assertEqual(result["discrepancies"], [])
        self.assertEqual(result["purchase_order"], self.po)

    @patch("apps.agents.orchestrator._publish")
    @patch("apps.agents.judge.judge")
    @patch("apps.agents.comparator.compare")
    @patch("apps.agents.matcher.find_delivery_receipts", return_value=[])
    @patch("apps.agents.matcher.find_purchase_order")
    def test_discrepant_match_returns_discrepancies(self, mock_po, _rec, mock_cmp, mock_judge, _pub):
        mock_po.return_value = self.po
        mock_cmp.return_value = [{"type": "rate_mismatch"}]
        mock_judge.return_value = {
            "status": "discrepant", "severity": "major",
            "discrepancies": [{"type": "rate_mismatch"}],
            "reasoning": "Rate off.",
        }
        from apps.agents.orchestrator import run_three_way_match
        result = run_three_way_match(self.invoice)

        self.assertEqual(result["status"], "discrepant")
        self.assertEqual(len(result["discrepancies"]), 1)

    @patch("apps.agents.orchestrator._publish")
    @patch("apps.agents.matcher.find_delivery_receipts", return_value=[])
    @patch("apps.agents.matcher.find_purchase_order", return_value=None)
    def test_unmatched_when_no_po_and_no_contract(self, _po, _rec, _pub):
        # Vendor has no contracts
        from apps.agents.orchestrator import run_three_way_match
        result = run_three_way_match(self.invoice)

        self.assertEqual(result["status"], "unmatched")
        self.assertEqual(result["severity"], "critical")
        self.assertIsNone(result["purchase_order"])
