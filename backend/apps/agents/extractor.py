"""
Extractor agent. Wrapped so it can be swapped for a real Strands Agents SDK
`Agent` with the `chunk_retriever` tool without changing callers — the
Celery task only calls `run_extractor(document)`.
"""
from .client import get_llm_client

EXTRACTION_SCHEMA = {
    "document_type": "po | invoice | delivery_receipt | contract | other",
    "confidence": "float 0-1, overall extraction confidence",
    "fields": {
        "po_number": "string, if applicable",
        "invoice_number": "string, if applicable",
        "referenced_po_number": "string, as written on the doc — may be loose/informal",
        "order_date": "YYYY-MM-DD or null",
        "invoice_date": "YYYY-MM-DD or null",
        "due_date": "YYYY-MM-DD or null",
        "delivery_date": "YYYY-MM-DD or null",
        "is_partial": "bool, delivery receipts only",
        "vendor_name": "string, especially for contracts when no vendor is selected",
        "rate_cards": "list of contracted rates, quantities, currencies, or pricing tiers",
        "payment_days": "integer number of payment days",
        "valid_from": "YYYY-MM-DD or null, contracts only",
        "valid_until": "YYYY-MM-DD or null, contracts only",
        "sla": "object containing service-level commitments, penalties, and response targets",
        "currency": "ISO 4217 code",
        "total_amount": "number or null",
        "line_items": [
            {"sku": "string", "description": "string", "quantity": "number",
             "unit_price": "number", "currency": "string"}
        ],
    },
}

SYSTEM_PROMPT = """You are the Extractor agent in a procurement-document pipeline.
Convert raw OCR/text into strict structured JSON per the given schema.
Rules:
- Never invent line items or numbers that are not present in the text.
- If a field is missing or illegible, use null rather than guessing.
- referenced_po_number should capture even loose references
  (e.g. "as per your order last week") verbatim, for downstream fuzzy matching.
- quantity/unit_price must be numeric, stripped of currency symbols and thousands separators.
"""


def run_extractor(document) -> dict:
    client = get_llm_client()
    user_prompt = (
        f"Document raw text:\n---\n{document.raw_text[:12000]}\n---\n"
        f"Extract fields using this schema: {EXTRACTION_SCHEMA}"
    )
    response = client.complete(SYSTEM_PROMPT, user_prompt, model=client.fast_model,
                                json_schema=EXTRACTION_SCHEMA)
    data = response["json"] or {"document_type": document.type, "confidence": 0.0, "fields": {}}
    return {
        "document_type": data.get("document_type", document.type),
        "confidence": data.get("confidence", 0.5),
        "fields": data.get("fields", {}),
    }
