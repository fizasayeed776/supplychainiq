"""
Comparator agent. Aligns line items across invoice / PO / delivery receipts
and checks contract terms; emits discrepancy *candidates* (the Judge
downstream decides severity and filters false positives like rounding).
"""
from decimal import Decimal
import re


def _sum_quantities(receipts, sku):
    total = Decimal("0")
    for r in receipts:
        for li in r.document.line_items.filter(sku=sku):
            total += li.quantity
    return total


def _quantity_in_base_units(line_item):
    """Return quantity and a recognized pack conversion from line text."""
    text = f"{line_item.description or ''} {line_item.sku or ''}".lower()
    pack_match = re.search(r"(?:box(?:es)?|case(?:s)?|carton(?:s)?)\s+of\s+(\d+)", text)
    unit = "piece" if re.search(r"\b(?:piece|pieces|pc|pcs|unit|units)\b", text) else "pack"
    multiplier = Decimal(pack_match.group(1)) if pack_match else Decimal("1")
    return line_item.quantity * multiplier, unit, multiplier


def compare(invoice, purchase_order, delivery_receipts, contract=None) -> list[dict]:
    candidates = []
    invoice_items = {li.sku or li.description: li for li in invoice.document.line_items.all()}
    po_items = {li.sku or li.description: li for li in purchase_order.document.line_items.all()} if purchase_order else {}

    for key, inv_li in invoice_items.items():
        po_li = po_items.get(key)
        if po_li is None:
            if purchase_order:
                candidates.append({
                    "field": "line_item", "sku": key, "type": "unmatched_line_item",
                    "expected": None, "actual": {"quantity": float(inv_li.quantity), "unit_price": float(inv_li.unit_price)},
                    "reasoning": "Invoice line item has no matching PO line item.",
                })
            continue

        if delivery_receipts:
            delivered_qty = _sum_quantities(delivery_receipts, inv_li.sku)
        else:
            delivered_qty = None

        invoice_base, invoice_unit, invoice_multiplier = _quantity_in_base_units(inv_li)
        po_base, po_unit, po_multiplier = _quantity_in_base_units(po_li)
        if invoice_base != po_base:
            candidates.append({
                "field": "quantity", "sku": key, "type": "quantity_mismatch",
                "expected": float(po_li.quantity), "actual": float(inv_li.quantity),
                "expected_base": float(po_base), "actual_base": float(invoice_base),
                "unit_conversion": invoice_multiplier != po_multiplier,
                "delivered": float(delivered_qty) if delivered_qty is not None else None,
                "reasoning": f"PO ordered {po_li.quantity}, invoice bills {inv_li.quantity}.",
            })

        if abs(inv_li.unit_price - po_li.unit_price) >= Decimal("0.01"):
            candidates.append({
                "field": "unit_price", "sku": key, "type": "rate_mismatch",
                "expected": float(po_li.unit_price), "actual": float(inv_li.unit_price),
                "reasoning": f"Contracted/PO rate {po_li.unit_price} vs invoiced rate {inv_li.unit_price}.",
            })

        if (inv_li.currency or "").upper() != (po_li.currency or "").upper():
            candidates.append({
                "field": "currency", "sku": key, "type": "currency_mismatch",
                "expected": po_li.currency, "actual": inv_li.currency,
                "reasoning": "Invoice currency differs from PO currency — verify FX conversion.",
            })

    if purchase_order and delivery_receipts == [] and invoice_items:
        candidates.append({
            "field": "delivery", "type": "no_delivery_on_record",
            "expected": "delivery receipt", "actual": None,
            "reasoning": "Invoice was billed but no delivery receipt exists for this PO.",
        })
    elif delivery_receipts and purchase_order:
        partial = any(receipt.is_partial for receipt in delivery_receipts)
        for key, po_li in po_items.items():
            delivered_qty = _sum_quantities(delivery_receipts, po_li.sku)
            if delivered_qty < po_li.quantity:
                candidates.append({
                    "field": "delivery", "sku": key, "type": "delivery_shortfall",
                    "expected": float(po_li.quantity), "actual": float(delivered_qty),
                    "partial_delivery": partial,
                    "reasoning": (
                        f"Delivered {delivered_qty} of {po_li.quantity} ordered."
                        + (" Receipt is marked partial and may still be in transit." if partial else "")
                    ),
                })

    if contract:
        terms = contract.terms or {}
        for rate_card in terms.get("rate_cards", []):
            sku = rate_card.get("sku")
            inv_li = invoice_items.get(sku)
            if inv_li is not None:
                contract_rate = Decimal(str(rate_card.get("unit_price", 0)))
                if abs(inv_li.unit_price - contract_rate) >= Decimal("0.01"):
                    candidates.append({
                        "field": "unit_price", "sku": sku, "type": "contract_rate_violation",
                        "expected": float(contract_rate), "actual": float(inv_li.unit_price),
                        "reasoning": f"Contract rate is {contract_rate}; invoice rate is {inv_li.unit_price}.",
                    })
        if terms.get("payment_days") and invoice.due_date and invoice.invoice_date:
            actual_days = (invoice.due_date - invoice.invoice_date).days
            if actual_days != terms["payment_days"]:
                candidates.append({
                    "field": "payment_days", "type": "contract_term_violation",
                    "expected": terms["payment_days"], "actual": actual_days,
                    "reasoning": "Invoice payment terms do not match the contracted payment days.",
                })
        if contract.valid_until and invoice.invoice_date and invoice.invoice_date > contract.valid_until:
            candidates.append({
                "field": "contract_validity", "type": "expired_contract",
                "expected": f"contract valid until {contract.valid_until}",
                "actual": f"invoice dated {invoice.invoice_date}",
                "reasoning": "Purchasing continued after contract expiry.",
            })

    return candidates
