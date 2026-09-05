"""
Dispute Drafter agent. Drafts a professional dispute email citing the
exact documents and figures involved. Output always goes to human review
before sending (never auto-sent).
"""
from .client import get_llm_client

SYSTEM_PROMPT = """You are the Dispute Drafter agent for a procurement team.
Write a concise, professional dispute email to a vendor, citing the specific
invoice number, PO number, and the exact figures in question. Be factual and
non-accusatory; propose next steps (credit note, corrected invoice, or a call).
Respond ONLY with JSON: {"subject": "...", "body": "..."}
"""


def draft_dispute_email(match_result) -> dict:
    invoice = match_result.invoice
    client = get_llm_client()
    context = (
        f"Invoice {invoice.invoice_number} from vendor {invoice.vendor.name}.\n"
        f"Discrepancies: {match_result.discrepancies}\n"
        f"Severity: {match_result.severity}\n"
        f"Agent reasoning: {match_result.agent_reasoning}"
    )
    response = client.complete(
        SYSTEM_PROMPT, context, model=client.fast_model,
        json_schema={"subject": "string", "body": "string"},
    )
    return response["json"] or {
        "subject": f"Discrepancy on Invoice {invoice.invoice_number}",
        "body": "Draft unavailable — please write manually. See discrepancy details in the app.",
    }
