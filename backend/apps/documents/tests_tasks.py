"""
Additional document task tests — idempotency guard and _materialize paths
not covered in tests.py.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.core.models import Vendor, Workspace
from apps.documents.models import Document, Invoice, PurchaseOrder, DeliveryReceipt
from apps.documents.tasks import _materialize_structured_record


class IngestDocumentIdempotencyTests(TestCase):
    """Duplicate content_hash for the same workspace must be a no-op."""

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Ingest WS", slug="ingest-ws")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Ingest Vendor")

    @patch("apps.documents.tasks._publish_progress")
    def test_duplicate_hash_skips_pipeline(self, mock_pub):
        """When a second document with the same content_hash is ingested,
        it must be skipped (ocr_status=not_needed) and NOT dispatch a pipeline.
        Regression test for the idempotency guard added in Step 2."""
        # First document — the original
        doc1 = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="invoice",
            file=SimpleUploadedFile("orig.txt", b"original"),
            content_hash="idem" * 16,
        )
        with patch("apps.documents.tasks.chain") as mock_chain, \
             patch("apps.documents.tasks.Document.objects.filter") as mock_filter:
            mock_filter.return_value.exclude.return_value.exists.return_value = True
            from apps.documents.tasks import ingest_document
            ingest_document.run(str(doc1.id))

        doc1.refresh_from_db()
        self.assertEqual(doc1.ocr_status, "not_needed")
        mock_chain.assert_not_called()
        mock_pub.assert_called_once()
        pub_payload = mock_pub.call_args[0][1]
        self.assertEqual(pub_payload["stage"], "duplicate_skipped")


class MaterializeStructuredRecordTests(TestCase):
    """_materialize_structured_record — all four document types + missing-vendor path."""

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Mat WS", slug="mat-ws")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Mat Vendor")

    def _make_doc(self, doc_type, extraction, hash_suffix, vendor=None):
        doc = Document.objects.create(
            workspace=self.workspace, vendor=vendor, type=doc_type,
            file=SimpleUploadedFile(f"{hash_suffix}.txt", b"x"),
            content_hash=f"mat-{hash_suffix}".ljust(64, "0"),
            extraction=extraction,
        )
        return doc

    @patch("apps.matching.tasks.try_three_way_match.delay")
    def test_po_document_creates_purchase_order(self, _delay):
        doc = self._make_doc("po", {
            "vendor_name": "Mat Vendor",
            "po_number": "PO-MAT-1",
            "currency": "USD",
            "line_items": [],
        }, "po1", vendor=self.vendor)
        _materialize_structured_record(doc)
        self.assertTrue(PurchaseOrder.objects.filter(document=doc, po_number="PO-MAT-1").exists())

    @patch("apps.matching.tasks.try_three_way_match.delay")
    def test_invoice_document_creates_invoice(self, _delay):
        doc = self._make_doc("invoice", {
            "vendor_name": "Mat Vendor",
            "invoice_number": "INV-MAT-1",
            "currency": "USD",
            "line_items": [],
        }, "inv1", vendor=self.vendor)
        _materialize_structured_record(doc)
        self.assertTrue(Invoice.objects.filter(document=doc, invoice_number="INV-MAT-1").exists())

    @patch("apps.matching.tasks.try_three_way_match.delay")
    def test_delivery_receipt_document_creates_receipt(self, _delay):
        doc = self._make_doc("delivery_receipt", {
            "vendor_name": "Mat Vendor",
            "referenced_po_number": "PO-MAT-1",
            "line_items": [],
        }, "dr1", vendor=self.vendor)
        _materialize_structured_record(doc)
        self.assertTrue(DeliveryReceipt.objects.filter(document=doc).exists())

    @patch("apps.matching.tasks.try_three_way_match.delay")
    def test_vendor_resolved_from_extraction_when_doc_vendor_is_none(self, _delay):
        """When doc.vendor is null but extraction has vendor_name, the vendor
        must be resolved via get_or_create and attached to the document."""
        doc = self._make_doc("invoice", {
            "vendor_name": "Brand New Vendor",
            "invoice_number": "INV-NEW-1",
            "line_items": [],
        }, "new1", vendor=None)
        _materialize_structured_record(doc)
        doc.refresh_from_db()
        self.assertIsNotNone(doc.vendor)
        self.assertEqual(doc.vendor.name, "Brand New Vendor")

    def test_missing_vendor_logs_warning_and_does_not_raise(self):
        """When doc.vendor is null AND extraction has no vendor_name, the
        function must log a WARNING and return without saving — not raise.
        Regression test for the original bug in Step 2."""
        doc = self._make_doc("invoice", {
            "invoice_number": "INV-NOVENDOR",
            "line_items": [],
        }, "novendor", vendor=None)

        with self.assertLogs("apps.documents.tasks", level="WARNING") as logs:
            _materialize_structured_record(doc)

        self.assertFalse(Invoice.objects.filter(document=doc).exists())
        combined = "\n".join(logs.output)
        self.assertIn("vendor could not be resolved", combined)

    @patch("apps.matching.tasks.try_three_way_match.delay")
    def test_materialize_is_idempotent(self, _delay):
        """Calling twice on the same document must not create duplicate rows."""
        doc = self._make_doc("invoice", {
            "vendor_name": "Mat Vendor",
            "invoice_number": "INV-IDEM-1",
            "line_items": [],
        }, "idem1", vendor=self.vendor)
        _materialize_structured_record(doc)
        _materialize_structured_record(doc)
        self.assertEqual(Invoice.objects.filter(document=doc).count(), 1)
