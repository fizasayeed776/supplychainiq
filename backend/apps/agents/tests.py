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
