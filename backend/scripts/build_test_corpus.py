"""Seed a deterministic evaluation corpus for agent matching tests.

Document inventory (one vendor per case, 15 cases):
  - 15 POs           (one per vendor)
  - 15 Invoices      (one per vendor)
  - 12 Delivery receipts (cases where a receipt is expected)
  - 2  Contracts     (cases that test contract compliance)
  = ~44 documents total

Discrepancy taxonomy:
  Cases 01-12 are DISCREPANT (planted_discrepancy=True).
  Cases 13-15 are CLEAN      (planted_discrepancy=False).

Case details
============
01 quantity_mismatch          invoice qty 90, PO qty 100
02 rate_mismatch              invoice price 1.25, PO price 1.20
03 currency_mismatch          invoice in EUR, PO in USD, no delivery receipt
04 missing_delivery           no delivery receipt at all
05 contract_rate_violation    rate 0.55 against contract rate 0.40
06 multi_field                qty 90 + rate 1.25 + currency EUR
07 expired_contract           contract valid_until 2026-08-31 (before invoice date)
08 unit_mismatch_boxes_pieces PO: 5 boxes of 12 pieces; invoice: 55 pieces (mismatch)
09 partial_delivery_shortfall receipt is partial AND delivered qty < invoiced qty
10 partial_delivery_multi     two receipts totalling 90 of 100 invoiced
11 zero_quantity_line         invoice has a line with qty=0 (invalid)
12 multi_currency_total       USD + EUR lines mixed (total currency ambiguous)
13 rounding_false_positive    rate 1.204 vs 1.20 — judge should suppress
14 unit_conversion_clean      PO: 5 boxes of 12 = 60 pieces; invoice: 60 pieces
15 full_match_clean           everything matches exactly
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from datetime import date, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile

from apps.core.models import Contract, Vendor, Workspace
from apps.documents.models import DeliveryReceipt, Document, Invoice, LineItem, PurchaseOrder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc(workspace, vendor, doc_type, index, suffix):
    hash_key = f"agent-eval-{suffix}-{index:02d}".ljust(64, "0")
    return Document.objects.create(
        workspace=workspace,
        type=doc_type,
        source="upload",
        vendor=vendor,
        file=ContentFile(b"evaluation doc", name=f"EVAL-{suffix.upper()}-{index+1:02d}.txt"),
        content_hash=hash_key,
        extraction_status="done",
    )


def _po(workspace, vendor, index, po_number, description, quantity, unit_price, currency="USD"):
    doc = _doc(workspace, vendor, "po", index, "po")
    PurchaseOrder.objects.create(
        document=doc, workspace=workspace, vendor=vendor,
        po_number=po_number, order_date=date(2026, 9, 1),
        currency=currency, total_amount=(quantity * unit_price).quantize(Decimal("0.01")),
    )
    LineItem.objects.create(
        document=doc, sku="EVAL-ITEM", description=description,
        quantity=quantity, unit_price=unit_price, currency=currency, position=0,
    )
    return doc


def _invoice(workspace, vendor, index, po_number, description, quantity, unit_price, currency="USD",
             extra_line=None):
    doc = _doc(workspace, vendor, "invoice", index, "inv")
    invoice = Invoice.objects.create(
        document=doc, workspace=workspace, vendor=vendor,
        invoice_number=f"EVAL-INV-{index+1:02d}",
        referenced_po_number=po_number,
        invoice_date=date(2026, 9, 5), due_date=date(2026, 10, 5),
        currency=currency,
        total_amount=(quantity * unit_price).quantize(Decimal("0.01")),
    )
    LineItem.objects.create(
        document=doc, sku="EVAL-ITEM", description=description,
        quantity=quantity, unit_price=unit_price, currency=currency, position=0,
    )
    if extra_line:
        LineItem.objects.create(document=doc, **extra_line)
    return doc, invoice


def _receipt(workspace, vendor, index, po_number, quantity, is_partial=False, suffix="rec"):
    doc = _doc(workspace, vendor, "delivery_receipt", index, suffix)
    receipt = DeliveryReceipt.objects.create(
        document=doc, workspace=workspace, vendor=vendor,
        referenced_po_number=po_number,
        delivery_date=date(2026, 9, 4),
        is_partial=is_partial,
    )
    LineItem.objects.create(
        document=doc, sku="EVAL-ITEM", description="Evaluation item",
        quantity=quantity, unit_price=Decimal("1.20"), currency="USD", position=0,
    )
    return doc, receipt


def _contract(workspace, vendor, unit_price, expired=False):
    valid_until = date(2026, 8, 31) if expired else date(2027, 12, 31)
    return Contract.objects.create(
        workspace=workspace, vendor=vendor,
        status="expired" if expired else "active",
        valid_from=date(2026, 1, 1),
        valid_until=valid_until,
        terms={
            "rate_cards": [{"sku": "EVAL-ITEM", "unit_price": float(unit_price)}],
            "payment_days": 30,
        },
    )


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class Command:
    def handle(self, workspace_slug="agent-eval"):
        workspace, _ = Workspace.objects.get_or_create(
            slug=workspace_slug, defaults={"name": "Agent Evaluation"}
        )
        # Clear previous eval data.
        Document.objects.filter(content_hash__startswith="agent-eval-").delete()
        workspace.vendors.filter(name__startswith="Eval Vendor ").delete()

        vendors = [
            Vendor.objects.create(workspace=workspace, name=f"Eval Vendor {i + 1}")
            for i in range(15)
        ]

        # ── Case 01: quantity mismatch ─────────────────────────────────────
        i, v = 0, vendors[0]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("90"), Decimal("1.20"))
        _receipt(workspace, v, i, pn, Decimal("90"))

        # ── Case 02: rate mismatch ─────────────────────────────────────────
        i, v = 1, vendors[1]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.25"))
        _receipt(workspace, v, i, pn, Decimal("100"))

        # ── Case 03: currency mismatch (no receipt) ────────────────────────
        i, v = 2, vendors[2]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"), "USD")
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"), "EUR")
        # No delivery receipt for this case.

        # ── Case 04: missing delivery (no receipt) ─────────────────────────
        i, v = 3, vendors[3]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        # Intentionally no receipt.

        # ── Case 05: contract rate violation ──────────────────────────────
        i, v = 4, vendors[4]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("0.55"))
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("0.55"))
        _receipt(workspace, v, i, pn, Decimal("100"))
        _contract(workspace, v, unit_price=Decimal("0.40"), expired=False)

        # ── Case 06: multi-field (qty + rate + currency) ───────────────────
        i, v = 5, vendors[5]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"), "USD")
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("90"), Decimal("1.25"), "EUR")
        _receipt(workspace, v, i, pn, Decimal("90"))

        # ── Case 07: expired contract ──────────────────────────────────────
        i, v = 6, vendors[6]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _receipt(workspace, v, i, pn, Decimal("100"))
        _contract(workspace, v, unit_price=Decimal("1.20"), expired=True)

        # ── Case 08: unit mismatch — boxes vs pieces ───────────────────────
        # PO: 5 boxes of 12 pieces (=60 pieces). Invoice: 55 pieces — mismatch.
        i, v = 7, vendors[7]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "5 boxes of 12 pieces", Decimal("5"), Decimal("0.40"))
        _, inv = _invoice(workspace, v, i, pn, "55 pieces", Decimal("55"), Decimal("0.40"))
        _receipt(workspace, v, i, pn, Decimal("55"))

        # ── Case 09: partial delivery shortfall ────────────────────────────
        # Receipt is partial AND delivered qty (70) < invoiced qty (100).
        i, v = 8, vendors[8]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _receipt(workspace, v, i, pn, Decimal("70"), is_partial=True)

        # ── Case 10: partial delivery across two receipts ──────────────────
        # Two receipts (50 + 40 = 90) against an invoice for 100 — shortfall.
        i, v = 9, vendors[9]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _receipt(workspace, v, i, pn, Decimal("50"), is_partial=True, suffix="rec-a")
        _receipt(workspace, v, i, pn, Decimal("40"), is_partial=True, suffix="rec-b")

        # ── Case 11: zero quantity line (invalid invoice) ──────────────────
        i, v = 10, vendors[10]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("0"), Decimal("1.20"))
        _receipt(workspace, v, i, pn, Decimal("100"))

        # ── Case 12: multi-currency lines (USD + EUR on same invoice) ──────
        i, v = 11, vendors[11]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"), "USD")
        extra = dict(
            sku="EVAL-ITEM-EUR", description="Euro component",
            quantity=Decimal("10"), unit_price=Decimal("2.00"), currency="EUR", position=1,
        )
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"),
                          "USD", extra_line=extra)
        _receipt(workspace, v, i, pn, Decimal("100"))

        # ── Case 13: rounding false positive (CLEAN) ──────────────────────
        # Rate 1.204 vs 1.20 — difference is < 0.5%, judge should suppress.
        i, v = 12, vendors[12]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.204"))
        _receipt(workspace, v, i, pn, Decimal("100"))

        # ── Case 14: unit conversion clean (CLEAN) ────────────────────────
        # PO: 5 boxes of 12 pieces = 60 pieces; invoice: 60 pieces — match.
        i, v = 13, vendors[13]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "5 boxes of 12 pieces", Decimal("5"), Decimal("0.40"))
        _, inv = _invoice(workspace, v, i, pn, "60 pieces", Decimal("60"), Decimal("0.40"))
        _receipt(workspace, v, i, pn, Decimal("60"))

        # ── Case 15: full match clean (CLEAN) ─────────────────────────────
        i, v = 14, vendors[14]
        pn = f"EVAL-PO-{i+1:02d}"
        _po(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _, inv = _invoice(workspace, v, i, pn, "Evaluation item", Decimal("100"), Decimal("1.20"))
        _receipt(workspace, v, i, pn, Decimal("100"))

        # Link the contract-case PO documents to their contracts via source_document_id
        for contract_vendor_idx in (4, 6):
            contract_doc = _doc(workspace, vendors[contract_vendor_idx],
                                "contract", contract_vendor_idx, "contract")
            Contract.objects.filter(vendor=vendors[contract_vendor_idx]).update(
                source_document_id=contract_doc.id
            )

        doc_count = Document.objects.filter(content_hash__startswith="agent-eval-").count()
        print(f"Seeded {doc_count} documents across 15 vendors/cases")
        print("Discrepant cases (01-12):", ", ".join(f"EVAL-INV-{i:02d}" for i in range(1, 13)))
        print("Clean cases    (13-15):", ", ".join(f"EVAL-INV-{i:02d}" for i in range(13, 16)))


if __name__ == "__main__":
    Command().handle()
