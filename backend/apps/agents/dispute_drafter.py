"""
Dispute Drafter agent. Drafts a professional dispute email citing the
exact documents and figures involved. Output always goes to human review
before sending (never auto-sent).
"""
import logging

from pydantic import BaseModel

from .client import run_structured_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Dispute Drafter agent for a procurement team.
Write a concise, professional dispute email to a vendor, citing the specific
invoice number, PO number, and the exact figures in question. Be factual and
non-accusatory; propose next steps (credit note, corrected invoice, or a call).
Respond ONLY with JSON: {"subject": "...", "body": "..."}
"""


class DisputeEmail(BaseModel):
    subject: str
    body: str


def draft_dispute_email(match_result) -> dict:
    invoice = match_result.invoice
    context = (
        f"Invoice {invoice.invoice_number} from vendor {invoice.vendor.name}.\n"
        f"Discrepancies: {match_result.discrepancies}\n"
        f"Severity: {match_result.severity}\n"
        f"Agent reasoning: {match_result.agent_reasoning}"
    )
    try:
        result = run_structured_agent(SYSTEM_PROMPT, context, DisputeEmail)
    except Exception:
        logger.exception(
            "draft_dispute_email failed for invoice %s", invoice.invoice_number
        )
        return {
            "subject": f"Discrepancy on Invoice {invoice.invoice_number}",
            "body": "Draft unavailable — please write manually. See discrepancy details in the app.",
        }
    return result
