"""Seed a deterministic 30-document matching corpus for agent evaluation."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from datetime import date, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.core.models import Contract, Vendor, Workspace
from apps.documents.models import DeliveryReceipt, Document, Invoice, LineItem, PurchaseOrder


CASES = [
    ("quantity", {"quantity": Decimal("90"), "delivered": Decimal("90")}),
    ("rate", {"unit_price": Decimal("1.25")}),
    ("currency", {"currency": "EUR", "receipt": False}),
    ("missing_delivery", {"receipt": False}),
    ("contract_rate", {"unit_price": Decimal("0.55"), "po_unit_price": Decimal("0.55"), "contract": True}),
    ("quantity_rate_currency", {"quantity": Decimal("90"), "unit_price": Decimal("1.25"), "currency": "EUR"}),
    ("expired_contract", {"contract": True, "expired": True}),
    ("rounding_false_positive", {"unit_price": Decimal("1.204")}),
    ("unit_conversion_false_positive", {"po_description": "5 boxes of 12 pieces", "invoice_description": "60 pieces", "po_quantity": Decimal("5"), "quantity": Decimal("60")}),
    ("partial_delivery", {"receipt": True, "partial": True, "delivered": Decimal("90")}),
]


class Command(BaseCommand):
    help = "Create 30 deterministic procurement documents for matching evaluation."

    def add_arguments(self, parser):
        parser.add_argument("--workspace", default="agent-eval")

    def handle(self, *args, **options):
        workspace, _ = Workspace.objects.get_or_create(
            slug=options.get("workspace", "agent-eval"), defaults={"name": "Agent Evaluation"}
        )
        Document.objects.filter(content_hash__startswith="agent-eval-").delete()
        workspace.vendors.filter(name__startswith="Eval Vendor ").delete()

        vendors = []
        for index in range(10):
            vendor, _ = Vendor.objects.get_or_create(
                workspace=workspace, name=f"Eval Vendor {index + 1}"
            )
            vendors.append(vendor)

        for index in range(10):
            case_name, overrides = CASES[index]
            vendor = vendors[index]
            po_number = f"EVAL-PO-{index + 1:02d}"
            po_doc = Document.objects.create(
                workspace=workspace, type="po", source="upload",
                file=ContentFile(b"evaluation purchase order", name=f"{po_number}.txt"),
                content_hash=f"agent-eval-po-{index:02d}".ljust(64, "0"),
                vendor=vendor, extraction_status="done",
            )
            PurchaseOrder.objects.create(
                document=po_doc, workspace=workspace, vendor=vendor,
                po_number=po_number, order_date=date(2026, 9, 1),
                currency="USD", total_amount=Decimal("100.00"),
            )
            LineItem.objects.create(
                document=po_doc, sku="EVAL-ITEM", description=overrides.get("po_description", "Evaluation item"),
                quantity=overrides.get("po_quantity", Decimal("100")), unit_price=overrides.get("po_unit_price", Decimal("1.20")), currency="USD", position=0,
            )

            invoice_doc = Document.objects.create(
                workspace=workspace, type="invoice", source="upload",
                file=ContentFile(b"evaluation invoice", name=f"EVAL-INV-{index + 1:02d}.txt"),
                content_hash=f"agent-eval-inv-{index:02d}".ljust(64, "0"),
                vendor=vendor, extraction_status="done",
            )
            invoice = Invoice.objects.create(
                document=invoice_doc, workspace=workspace, vendor=vendor,
                invoice_number=f"EVAL-INV-{index + 1:02d}", referenced_po_number=po_number,
                invoice_date=date(2026, 9, 5), due_date=date(2026, 10, 5),
                currency=overrides.get("currency", "USD"), total_amount=Decimal("100.00"),
            )
            LineItem.objects.create(
                document=invoice_doc, sku="EVAL-ITEM",
                description=overrides.get("invoice_description", "Evaluation item"),
                quantity=overrides.get("quantity", overrides.get("po_quantity", Decimal("100"))),
                unit_price=overrides.get("unit_price", Decimal("1.20")),
                currency=overrides.get("currency", "USD"), position=0,
            )

            if overrides.get("contract"):
                Contract.objects.create(
                    workspace=workspace, vendor=vendor, status="expired" if overrides.get("expired") else "active",
                    valid_from=date(2026, 1, 1), valid_until=date(2026, 8, 31) if overrides.get("expired") else date(2027, 12, 31),
                    terms={"rate_cards": [{"sku": "EVAL-ITEM", "unit_price": 0.40}], "payment_days": 30},
                )

            if overrides.get("receipt", True):
                receipt_doc = Document.objects.create(
                    workspace=workspace, type="delivery_receipt", source="upload",
                    file=ContentFile(b"evaluation delivery receipt", name=f"EVAL-REC-{index + 1:02d}.txt"),
                    content_hash=f"agent-eval-rec-{index:02d}".ljust(64, "0"),
                    vendor=vendor, extraction_status="done",
                )
                receipt = DeliveryReceipt.objects.create(
                    document=receipt_doc, workspace=workspace, vendor=vendor,
                    referenced_po_number=po_number, delivery_date=date(2026, 9, 4),
                    is_partial=overrides.get("partial", False),
                )
                LineItem.objects.create(
                    document=receipt_doc, sku="EVAL-ITEM", description=overrides.get("po_description", "Evaluation item"),
                    quantity=overrides.get("delivered", overrides.get("po_quantity", Decimal("100"))), unit_price=Decimal("1.20"), currency="USD", position=0,
                )

        contract_doc = Document.objects.create(
            workspace=workspace, type="contract", source="upload",
            file=ContentFile(b"evaluation contract", name="EVAL-CONTRACT.txt"),
            content_hash="agent-eval-contract".ljust(64, "0"), vendor=vendors[4], extraction_status="done",
        )
        Contract.objects.filter(vendor=vendors[4]).update(source_document_id=contract_doc.id)

        self.stdout.write(self.style.SUCCESS("seeded 30 documents across 10 vendors"))
        self.stdout.write("Cases: " + ", ".join(case[0] for case in CASES))


if __name__ == "__main__":
    Command().handle()
