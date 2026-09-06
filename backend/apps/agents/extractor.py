"""
Extractor agent — migrated to the Strands Agents SDK.

Callers (Celery tasks) only call `run_extractor(document)` and rely on the
return shape::

    {"document_type": str, "confidence": float, "fields": dict}

Nothing downstream changes — `_materialize_structured_record` in
apps/documents/tasks.py reads the same keys it always has.
"""
import logging
from typing import List, Optional

from pydantic import BaseModel

from .client import run_structured_agent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic response schema
#
# Every field must have an explicit type with declared properties so that
# OpenAI's strict JSON schema mode (used by agent.structured_output()) can
# build a valid schema.  Loose `Any` or bare `dict` types produce a
# schema-less object which OpenAI rejects with:
#   "properties must be present"
# ---------------------------------------------------------------------------

class LineItemExtraction(BaseModel):
    sku: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    currency: Optional[str] = None


class SlaTerms(BaseModel):
    """Service-level agreement commitments extracted from contracts."""
    response_time_hours: Optional[float] = None
    penalty_clause: Optional[str] = None
    uptime_target: Optional[str] = None
    notes: Optional[str] = None


class RateCardEntry(BaseModel):
    """A single contracted rate / pricing tier from a contract or PO."""
    description: Optional[str] = None
    unit_price: Optional[float] = None
    currency: Optional[str] = None
    quantity_tier: Optional[str] = None


class ExtractionFields(BaseModel):
    po_number: Optional[str] = None
    invoice_number: Optional[str] = None
    referenced_po_number: Optional[str] = None
    order_date: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    delivery_date: Optional[str] = None
    is_partial: Optional[bool] = None
    vendor_name: Optional[str] = None
    rate_cards: Optional[List[RateCardEntry]] = None
    payment_days: Optional[int] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    sla: Optional[SlaTerms] = None
    currency: Optional[str] = None
    total_amount: Optional[float] = None
    line_items: Optional[List[LineItemExtraction]] = None


class ExtractionResult(BaseModel):
    document_type: str
    confidence: float
    fields: ExtractionFields


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Extractor agent in a procurement-document pipeline.
Convert raw OCR/text into strict structured JSON per the given schema.
Rules:
- Never invent line items or numbers that are not present in the text.
- If a field is missing or illegible, use null rather than guessing.
- referenced_po_number should capture even loose references
  (e.g. "as per your order last week") verbatim, for downstream fuzzy matching.
- quantity/unit_price must be numeric, stripped of currency symbols and thousands separators.
- rate_cards: extract as a list of objects, each with description, unit_price (numeric),
  currency (ISO 4217), and quantity_tier (e.g. "1-100 units"). Use null for any sub-field
  not present.
- sla: extract into response_time_hours (numeric hours), penalty_clause (verbatim text),
  uptime_target (e.g. "99.9%"), and notes (any other SLA commitments). Use null for any
  sub-field not present.
"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_extractor(document) -> dict:
    """Extract structured fields from *document* using the Strands Agent SDK.

    Returns:
        ``{"document_type": str, "confidence": float, "fields": dict}``

    On any Strands/LLM failure the exception is logged and a safe fallback
    dict is returned so the Celery task can decide whether to retry.
    """
    user_prompt = (
        f"Document raw text:\n---\n{document.raw_text[:12000]}\n---\n"
        "Extract all available fields. Return null for anything missing or illegible."
    )

    try:
        result_dict = run_structured_agent(SYSTEM_PROMPT, user_prompt, ExtractionResult)
    except Exception:
        logger.exception("run_extractor failed for document %s", document.id)
        return {"document_type": document.type, "confidence": 0.0, "fields": {}}

    # result_dict mirrors ExtractionResult.model_dump():
    # {"document_type": ..., "confidence": ..., "fields": {"po_number": ..., ...}}
    raw_fields = result_dict.get("fields") or {}
    return {
        "document_type": result_dict.get("document_type", document.type),
        "confidence": result_dict.get("confidence", 0.5),
        "fields": raw_fields,
    }
