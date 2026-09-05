"""
Orchestrator. Implements the "agents-as-tools" pattern: it doesn't reason
itself, it delegates to Matcher -> Comparator -> Judge in sequence,
aggregates their output, and publishes step-by-step progress events
(e.g. "Comparator: invoice 42, line 3/7") to the workspace dashboard group.
"""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from . import matcher, comparator, judge as judge_module


def _publish(workspace_id, message):
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(
        f"dashboard_{workspace_id}", {"type": "pipeline.progress", "payload": {"agent_step": message}}
    )


def run_three_way_match(invoice) -> dict:
    ws = invoice.workspace_id

    _publish(ws, f"Matcher: locating PO for invoice {invoice.invoice_number}")
    purchase_order = matcher.find_purchase_order(invoice)
    delivery_receipts = matcher.find_delivery_receipts(invoice, purchase_order)

    contract = invoice.vendor.contracts.order_by("-created_at").first()
    if purchase_order is None and contract is None:
        return {
            "status": "unmatched", "severity": "critical", "discrepancies": [],
            "reasoning": "No matching purchase order could be found for this invoice.",
            "purchase_order": None, "delivery_receipt": None,
        }

    _publish(ws, f"Comparator: comparing invoice {invoice.invoice_number} line items")
    candidates = comparator.compare(invoice, purchase_order, delivery_receipts, contract)

    _publish(ws, f"Judge: reviewing {len(candidates)} candidate discrepancies")
    verdict = judge_module.judge(invoice, candidates)

    return {
        **verdict,
        "purchase_order": purchase_order,
        "delivery_receipt": delivery_receipts[0] if delivery_receipts else None,
    }
