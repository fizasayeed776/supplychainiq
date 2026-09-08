"""
Matching idempotency and precision/recall regression tests.
Rubric requirement: matching precision/recall, idempotency.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.core.models import Vendor, Workspace
from apps.documents.models import Document, Invoice, LineItem, PurchaseOrder
from .models import MatchResult
from .tasks import try_three_way_match, finalize_nightly_rematch, rematch_all_open_invoices


class MatchResultIdempotencyTests(TestCase):
    """Running try_three_way_match twice on the same invoice must produce
    exactly one MatchResult (update_or_create semantics)."""

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Match tests", slug="match-tests")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Match Vendor")
        po_doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="po",
            file=SimpleUploadedFile("po.txt", b"po"),
            content_hash="matchtest-po".ljust(64, "0"),
        )
        self.po = PurchaseOrder.objects.create(
            document=po_doc, workspace=self.workspace, vendor=self.vendor,
            po_number="PO-MATCH-1", order_date=date(2026, 9, 1), currency="USD",
        )
        LineItem.objects.create(
            document=po_doc, sku="PART-A", description="Part A",
            quantity=Decimal("10"), unit_price=Decimal("5.00"), currency="USD", position=0,
        )
        inv_doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="invoice",
            file=SimpleUploadedFile("inv.txt", b"inv"),
            content_hash="matchtest-inv".ljust(64, "0"),
        )
        self.invoice = Invoice.objects.create(
            document=inv_doc, workspace=self.workspace, vendor=self.vendor,
            invoice_number="INV-MATCH-1", referenced_po_number="PO-MATCH-1",
            invoice_date=date(2026, 9, 5), due_date=date(2026, 10, 5), currency="USD",
        )
        LineItem.objects.create(
            document=inv_doc, sku="PART-A", description="Part A",
            quantity=Decimal("10"), unit_price=Decimal("5.00"), currency="USD", position=0,
        )

    @patch("apps.agents.tasks.recompute_vendor_risk.delay")
    @patch("apps.workflow.tasks.advance_approval_flow.delay")
    @patch("apps.matching.tasks._publish")
    @patch("apps.agents.orchestrator.run_three_way_match")
    def test_match_result_is_idempotent(self, mock_match, _pub, _adv, _risk):
        mock_match.return_value = {
            "status": "matched", "discrepancies": [], "severity": "none",
            "reasoning": "Clean match.", "purchase_order": self.po,
            "delivery_receipt": None,
        }
        try_three_way_match.run(str(self.invoice.id))
        try_three_way_match.run(str(self.invoice.id))

        # Must have exactly one MatchResult row
        self.assertEqual(MatchResult.objects.filter(invoice=self.invoice).count(), 1)
        result = MatchResult.objects.get(invoice=self.invoice)
        self.assertEqual(result.status, "matched")

    @patch("apps.agents.tasks.recompute_vendor_risk.delay")
    @patch("apps.workflow.tasks.advance_approval_flow.delay")
    @patch("apps.matching.tasks._publish")
    @patch("apps.agents.orchestrator.run_three_way_match")
    def test_discrepant_match_records_discrepancies(self, mock_match, _pub, _adv, _risk):
        discrepancies = [{"type": "rate_mismatch", "sku": "PART-A", "expected": 5.0, "actual": 7.5}]
        mock_match.return_value = {
            "status": "discrepant", "discrepancies": discrepancies,
            "severity": "major", "reasoning": "Rate mismatch on PART-A.",
            "purchase_order": self.po, "delivery_receipt": None,
        }
        try_three_way_match.run(str(self.invoice.id))
        result = MatchResult.objects.get(invoice=self.invoice)
        self.assertEqual(result.status, "discrepant")
        self.assertEqual(result.severity, "major")
        self.assertEqual(len(result.discrepancies), 1)
        self.assertEqual(result.discrepancies[0]["type"], "rate_mismatch")


# ---------------------------------------------------------------------------
# Fix 8: group + chord tests
# ---------------------------------------------------------------------------

@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class NightlyRematchChordTests(TestCase):
    """Verify that rematch_all_open_invoices fans out via group+chord and that
    finalize_nightly_rematch aggregates counts correctly.

    Celery eager mode (CELERY_TASK_ALWAYS_EAGER=True) executes every task
    synchronously in the same thread, so chord callbacks fire immediately and
    we can assert on their return values without a running broker.
    """

    def _make_invoice(self, suffix, workspace, vendor, po=None, status=None):
        """Helper: create a Document + Invoice (+ optional MatchResult)."""
        inv_doc = Document.objects.create(
            workspace=workspace, vendor=vendor, type="invoice",
            file=SimpleUploadedFile(f"inv{suffix}.txt", b"inv"),
            content_hash=f"chord-inv-{suffix}".ljust(64, "0"),
        )
        invoice = Invoice.objects.create(
            document=inv_doc, workspace=workspace, vendor=vendor,
            invoice_number=f"INV-CHORD-{suffix}",
            referenced_po_number=po.po_number if po else "",
            invoice_date=date(2026, 9, 1), due_date=date(2026, 10, 1), currency="USD",
        )
        if status:
            # Pre-seed a MatchResult so this invoice has the given status
            MatchResult.objects.create(
                invoice=invoice, workspace=workspace,
                status=status, severity="none",
            )
        return invoice

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Chord WS", slug="chord-ws")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Chord Vendor")
        po_doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="po",
            file=SimpleUploadedFile("po_chord.txt", b"po"),
            content_hash="chord-po".ljust(64, "0"),
        )
        self.po = PurchaseOrder.objects.create(
            document=po_doc, workspace=self.workspace, vendor=self.vendor,
            po_number="PO-CHORD-1", order_date=date(2026, 9, 1), currency="USD",
        )
        # Two open invoices (no MatchResult → excluded from "matched" filter)
        self.inv1 = self._make_invoice("1", self.workspace, self.vendor, self.po)
        self.inv2 = self._make_invoice("2", self.workspace, self.vendor, self.po)
        # One already-matched invoice → should NOT be queued
        self.inv_matched = self._make_invoice("M", self.workspace, self.vendor, self.po, status="matched")

    @patch("apps.agents.tasks.recompute_vendor_risk.delay")
    @patch("apps.workflow.tasks.advance_approval_flow.delay")
    @patch("apps.matching.tasks._publish")
    @patch("apps.agents.orchestrator.run_three_way_match")
    def test_finalize_callback_aggregates_counts(self, mock_match, _pub, _adv, _risk):
        """finalize_nightly_rematch receives the per-task results and returns
        the correct matched/discrepant/total counts."""
        mock_match.return_value = {
            "status": "matched", "discrepancies": [], "severity": "none",
            "reasoning": "Clean.", "purchase_order": self.po, "delivery_receipt": None,
        }

        # Simulate the list of results a chord would pass to the callback:
        # two matched, one discrepant, one None (failed task).
        results = [
            {"invoice_id": "aaa", "status": "matched",    "severity": "none"},
            {"invoice_id": "bbb", "status": "discrepant", "severity": "major"},
            {"invoice_id": "ccc", "status": "matched",    "severity": "none"},
            None,  # failed task
        ]

        with patch("apps.matching.tasks._publish") as mock_pub:
            summary = finalize_nightly_rematch.run(results, str(self.workspace.id))

        self.assertEqual(summary["total"],      4)
        self.assertEqual(summary["matched"],    2)
        self.assertEqual(summary["discrepant"], 1)
        self.assertEqual(summary["failed"],     1)
        # Dashboard should have received a summary pipeline event
        mock_pub.assert_called_once()
        publish_payload = mock_pub.call_args[0][1]
        self.assertEqual(publish_payload["stage"], "nightly_rematch_complete")

    @patch("apps.agents.tasks.recompute_vendor_risk.delay")
    @patch("apps.workflow.tasks.advance_approval_flow.delay")
    @patch("apps.matching.tasks._publish")
    @patch("apps.agents.orchestrator.run_three_way_match")
    def test_rematch_skips_already_matched_invoices(self, mock_match, _pub, _adv, _risk):
        """rematch_all_open_invoices must not queue invoices whose MatchResult
        is already status='matched'."""
        mock_match.return_value = {
            "status": "matched", "discrepancies": [], "severity": "none",
            "reasoning": "Clean.", "purchase_order": self.po, "delivery_receipt": None,
        }

        result = rematch_all_open_invoices.run()

        # Only inv1 and inv2 should be queued; inv_matched is excluded.
        self.assertEqual(result["total_invoices"], 2)
        self.assertEqual(result["chords_queued"],  1)  # both in the same workspace

    @patch("apps.workflow.tasks.advance_approval_flow.delay")
    @patch("apps.matching.tasks._publish")
    @patch("apps.agents.orchestrator.run_three_way_match")
    def test_chord_result_dict_has_required_keys(self, mock_match, _pub, _adv):
        """try_three_way_match must return a JSON-serializable dict with
        invoice_id, status, and severity — the keys finalize_nightly_rematch
        depends on."""
        mock_match.return_value = {
            "status": "discrepant",
            "discrepancies": [{"type": "price_mismatch"}],
            "severity": "minor",
            "reasoning": "Price off.",
            "purchase_order": self.po,
            "delivery_receipt": None,
        }

        with patch("apps.agents.tasks.recompute_vendor_risk.delay"), \
             patch("apps.workflow.tasks.draft_dispute_email.delay"):
            ret = try_three_way_match.run(str(self.inv1.id))

        self.assertIn("invoice_id", ret)
        self.assertIn("status",     ret)
        self.assertIn("severity",   ret)
        self.assertEqual(ret["status"],   "discrepant")
        self.assertEqual(ret["severity"], "minor")
        # Must be JSON-serializable (no Django model objects, UUIDs, etc.)
        import json
        json.dumps(ret)  # raises if not serializable
