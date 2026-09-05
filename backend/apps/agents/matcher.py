"""
Matcher agent. Tries exact/loose reference-number matching first (cheap,
deterministic); falls back to semantic/vector search over chunk embeddings
when the invoice references its PO informally ("as per your order last week").
"""
import re

from apps.documents.models import PurchaseOrder, DeliveryReceipt


def _normalize(ref: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", (ref or "")).upper()


def find_purchase_order(invoice) -> PurchaseOrder | None:
    ref = _normalize(invoice.referenced_po_number)
    if ref:
        candidates = PurchaseOrder.objects.filter(workspace=invoice.workspace, vendor=invoice.vendor)
        for po in candidates:
            if _normalize(po.po_number) == ref or _normalize(po.po_number) in ref:
                return po

    # Fallback: semantic search over PO document chunks for a loose reference
    if invoice.referenced_po_number:
        return _semantic_po_search(invoice)
    return None


def _semantic_po_search(invoice) -> PurchaseOrder | None:
    from apps.chat.rag import vector_search
    from apps.agents.client import get_llm_client

    client = get_llm_client()
    query_vector = client.embed(invoice.referenced_po_number)
    hits = vector_search(
        query_vector, workspace_id=invoice.workspace_id, document_type="po", top_k=3,
    )
    for chunk in hits:
        po = getattr(chunk.document, "purchase_order", None)
        if po and po.vendor_id == invoice.vendor_id:
            return po
    return None


def find_delivery_receipts(invoice, purchase_order: PurchaseOrder | None) -> list[DeliveryReceipt]:
    """Partial deliveries can span multiple receipts against one PO."""
    qs = DeliveryReceipt.objects.filter(workspace=invoice.workspace, vendor=invoice.vendor)
    if purchase_order:
        norm_po = _normalize(purchase_order.po_number)
        qs = [r for r in qs if _normalize(r.referenced_po_number) == norm_po
              or norm_po in _normalize(r.referenced_po_number)]
    else:
        qs = list(qs)
    return qs
