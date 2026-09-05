"""
Judge agent. Quality lives here: reviews Comparator candidates, filters
false positives (rounding, unit conversions e.g. boxes vs pieces, partial
deliveries), and assigns severity. Prompt iteration against the seeded
test corpus (precision/recall) is expected to happen mainly on this prompt.
"""
from decimal import Decimal

from .client import get_llm_client

SYSTEM_PROMPT = """You are the Judge agent for procurement three-way matching.
You receive candidate discrepancies from a Comparator and must:
1. Discard false positives: rounding differences under 1%, unit-of-measure
   conversions (e.g. "10 boxes" vs "120 pieces" at 12/box), and quantity
   differences fully explained by a *partial* delivery still in progress.
2. Assign severity to genuine discrepancies: "minor" (small dollar impact,
   likely a data-entry slip), "major" (meaningful rate/quantity mismatch),
   "critical" (expired contract, no delivery on record, large $ exposure).
3. Write concise plain-language reasoning a procurement officer can act on.

Respond ONLY with JSON: {"status": "matched|discrepant|unmatched",
"severity": "none|minor|major|critical", "discrepancies": [...], "reasoning": "..."}
Keep discrepancies discarded as false positives OUT of the returned list.
"""


def judge(invoice, candidates: list[dict]) -> dict:
    filtered = []
    for candidate in candidates:
        if candidate.get("type") == "delivery_shortfall" and candidate.get("partial_delivery"):
            continue
        if candidate.get("type") == "quantity_mismatch":
            expected = Decimal(str(candidate.get("expected_base", candidate.get("expected", 0))))
            actual = Decimal(str(candidate.get("actual_base", candidate.get("actual", 0))))
            if expected and abs(expected - actual) / expected < Decimal("0.01"):
                continue
            if candidate.get("unit_conversion") and expected == actual:
                continue
        filtered.append(candidate)
    candidates = filtered
    if not candidates:
        return {"status": "matched", "severity": "none", "discrepancies": [], "reasoning": "No discrepancies found."}

    client = get_llm_client()
    user_prompt = (
        f"Invoice {invoice.invoice_number} for vendor {invoice.vendor.name}.\n"
        f"Candidate discrepancies:\n{candidates}"
    )
    response = client.complete(
        SYSTEM_PROMPT, user_prompt, model=client.judge_model,
        json_schema={"status": "str", "severity": "str", "discrepancies": "list", "reasoning": "str"},
    )
    result = response["json"] or {
        "status": "discrepant", "severity": "minor",
        "discrepancies": candidates, "reasoning": "Judge response unavailable; defaulting to raw candidates.",
    }
    return result
