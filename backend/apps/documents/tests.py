from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Vendor, Workspace, WorkspaceMembership, Contract
from .models import DeliveryReceipt, Document, Invoice, LineItem, PurchaseOrder
from .tasks import _materialize_structured_record, extract_document


class DocumentIngestionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="audit-user", password="pass")
        self.workspace = Workspace.objects.create(name="Audit workspace", slug="audit-workspace")
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.user, role="owner")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Acme Supplies")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("apps.documents.tasks.embed_chunks.delay")
    @patch("apps.agents.extractor.run_extractor")
    def test_contract_extraction_materializes_terms_and_dates(self, run_extractor, _embed):
        document = Document.objects.create(
            workspace=self.workspace,
            vendor=self.vendor,
            type="contract",
            file=SimpleUploadedFile("contract.txt", b"Acme contract"),
            content_hash="a" * 64,
            raw_text="Acme contract",
        )
        run_extractor.return_value = {
            "document_type": "contract",
            "confidence": 0.96,
            "fields": {
                "vendor_name": "Acme Supplies",
                "rate_cards": [{"sku": "WIDGET-1", "unit_price": 2.5}],
                "payment_days": 45,
                "valid_from": "2026-01-01",
                "valid_until": "2027-12-31",
                "sla": {"response_hours": 24},
            },
        }

        extract_document.run(str(document.id))

        contract = Contract.objects.get(source_document_id=document.id)
        self.assertEqual(contract.terms["payment_days"], 45)
        self.assertEqual(contract.terms["rate_cards"][0]["sku"], "WIDGET-1")
        self.assertEqual(contract.terms["sla"]["response_hours"], 24)
        self.assertEqual(str(contract.valid_until), "2027-12-31")

    @patch("apps.documents.views.ingest_document.delay")
    def test_duplicate_upload_is_rejected_before_second_document(self, _ingest):
        payload = {
            "workspace": str(self.workspace.id),
            "type": "contract",
            "vendor": str(self.vendor.id),
        }
        first = self.client.post(
            "/api/documents/documents/",
            {**payload, "file": SimpleUploadedFile("contract.txt", b"same bytes")},
            format="multipart",
        )
        second = self.client.post(
            "/api/documents/documents/",
            {**payload, "file": SimpleUploadedFile("contract-copy.txt", b"same bytes")},
            format="multipart",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Document.objects.filter(workspace=self.workspace).count(), 1)

    def test_structured_materialization_is_idempotent(self):
        document = Document.objects.create(
            workspace=self.workspace,
            type="invoice",
            file=SimpleUploadedFile("invoice.txt", b"invoice"),
            content_hash="b" * 64,
            extraction={
                "vendor_name": "Summit Packaging Solutions",
                "invoice_number": "INV-1",
                "line_items": [{"sku": "WIDGET-1", "quantity": 2, "unit_price": 5}],
            },
        )

        _materialize_structured_record(document)
        _materialize_structured_record(document)

        self.assertEqual(Invoice.objects.filter(document=document).count(), 1)
        self.assertEqual(LineItem.objects.filter(document=document).count(), 1)
        self.assertEqual(document.vendor.name, "Summit Packaging Solutions")
        self.assertEqual(document.invoice.vendor.name, "Summit Packaging Solutions")

    def test_materialization_creates_all_vendor_backed_record_types(self):
        records = [
            ("po", {"po_number": "PO-1"}, PurchaseOrder, "po_number"),
            ("invoice", {"invoice_number": "INV-1"}, Invoice, "invoice_number"),
            (
                "delivery_receipt",
                {"referenced_po_number": "PO-1"},
                DeliveryReceipt,
                "referenced_po_number",
            ),
        ]

        for index, (document_type, fields, model, number_field) in enumerate(records):
            document = Document.objects.create(
                workspace=self.workspace,
                type=document_type,
                file=SimpleUploadedFile(f"{document_type}.txt", b"document"),
                content_hash=f"{index + 10:064x}",
                extraction={"vendor_name": "Acme Supplies", **fields},
            )
            _materialize_structured_record(document)

            self.assertTrue(
                model.objects.filter(document=document, **{number_field: fields[number_field]}).exists()
            )

    def test_required_vendor_missing_marks_materialization_as_invalid(self):
        document = Document.objects.create(
            workspace=self.workspace,
            type="invoice",
            file=SimpleUploadedFile("invoice-missing-vendor.txt", b"invoice"),
            content_hash="c" * 64,
            extraction={"invoice_number": "INV-MISSING"},
        )

        with self.assertLogs("apps.documents.tasks", level="WARNING") as logs:
            _materialize_structured_record(document)

        log_output = "\n".join(logs.output)
        self.assertIn(str(document.id), log_output)
        self.assertIn("type=invoice", log_output)
        self.assertFalse(Invoice.objects.filter(document=document).exists())

    def test_extraction_correction_patches_field_via_api(self):
        """Human-in-the-loop: user can correct a low-confidence extracted field."""
        document = Document.objects.create(
            workspace=self.workspace,
            vendor=self.vendor,
            type="invoice",
            file=SimpleUploadedFile("invoice-correction.txt", b"invoice"),
            content_hash="d" * 64,
            extraction={"invoice_number": "INV-WRONG", "vendor_name": "Acme Supplies"},
        )
        response = self.client.patch(
            f"/api/documents/documents/{document.id}/correct-extraction/",
            {"corrections": {"invoice_number": "INV-CORRECT"}},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        document.refresh_from_db()
        self.assertEqual(document.extraction["invoice_number"], "INV-CORRECT")
        # Other fields must be preserved
        self.assertEqual(document.extraction["vendor_name"], "Acme Supplies")


# ══════════════════════════════════════════════════════════════════════════════
# OCR vision-fallback gate tests
# ══════════════════════════════════════════════════════════════════════════════

class OCRVisionFallbackGateTests(TestCase):
    """Verify that vision_fallback_ocr (GPT vision) is only called when
    Tesseract's confidence is BELOW the configured threshold, never when
    confidence is high.  The gate lives in apps/documents/tasks.ocr_document.
    """

    def setUp(self):
        workspace = Workspace.objects.create(name="OCR Gate WS", slug="ocr-gate-ws")
        vendor = Vendor.objects.create(workspace=workspace, name="OCR Vendor")
        self.doc = Document.objects.create(
            workspace=workspace,
            vendor=vendor,
            type="invoice",
            source="upload",
            file=SimpleUploadedFile("scan.pdf", b"%PDF-fake"),
            content_hash="ocr-gate-test".ljust(64, "0"),
        )

    @patch("apps.documents.ocr.vision_fallback_ocr")
    @patch("apps.documents.ocr.ocr_pdf")
    def test_vision_fallback_skipped_when_confidence_is_high(self, mock_ocr_pdf, mock_vision):
        """When Tesseract returns confidence >= threshold, vision_fallback_ocr
        must NOT be called at all."""
        # Confidence 0.95 is well above the 0.65 default threshold.
        mock_ocr_pdf.return_value = {"text": "Invoice text", "confidence": 0.95}

        from apps.documents.tasks import ocr_document
        # apply() runs the task synchronously in-process with a fake request
        # context so self.request.retries is available (bind=True task).
        ocr_document.apply(args=[self.doc.id])

        mock_ocr_pdf.assert_called_once()
        mock_vision.assert_not_called()

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.ocr_status, "done")
        self.assertEqual(self.doc.raw_text, "Invoice text")

    @patch("apps.documents.ocr.vision_fallback_ocr")
    @patch("apps.documents.ocr.ocr_pdf")
    def test_vision_fallback_called_when_confidence_is_low(self, mock_ocr_pdf, mock_vision):
        """When Tesseract returns confidence < threshold, vision_fallback_ocr
        IS called and its result is used."""
        mock_ocr_pdf.return_value = {"text": "garbled text", "confidence": 0.30}
        mock_vision.return_value = {"text": "Clean vision text", "confidence": 0.98}

        from apps.documents.tasks import ocr_document
        ocr_document.apply(args=[self.doc.id])

        mock_ocr_pdf.assert_called_once()
        mock_vision.assert_called_once()

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.ocr_status, "low_confidence")
        self.assertEqual(self.doc.raw_text, "Clean vision text")
