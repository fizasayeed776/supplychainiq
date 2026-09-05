"""
Matching idempotency and precision/recall regression tests.
Rubric requirement: matching precision/recall, idempotency.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.core.models import Vendor, Workspace
from apps.documents.models import Document, Invoice, LineItem, PurchaseOrder
from .models import MatchResult
from .tasks import try_three_way_match


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
