"""
Judge agent. Quality lives here: reviews Comparator candidates, filters
false positives (rounding, unit conversions e.g. boxes vs pieces, partial
deliveries), and assigns severity. Prompt iteration against the seeded
test corpus (precision/recall) is expected to happen mainly on this prompt.

Design note: the LLM returns only kept_indices (0-based positions into the
candidates list) rather than re-emitting the full discrepancy objects.  This
sidesteps OpenAI's strict JSON schema requirement (discrepancy objects have
heterogeneous shapes that can't be described with a fixed schema) and prevents
the LLM from accidentally reformatting or corrupting the original data.
Python maps the indices back to the untouched candidate dicts.
"""
import logging
from decimal import Decimal
from typing import List, Literal

from django.conf import settings
from pydantic import BaseModel

from .client import run_structured_agent

logger = logging.getLogger(__name__)

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
"severity": "none|minor|major|critical",
"kept_indices": [list of integer positions, 0-indexed, of the candidates
from the input list that represent genuine discrepancies], "reasoning": "..."}
Do not re-describe or restate the candidates — only reference them by index.
Indices of candidates you consider false positives must be excluded from kept_indices.
"""


class JudgeDecision(BaseModel):
    status: Literal["matched", "discrepant", "unmatched"]
    severity: Literal["none", "minor", "major", "critical"]
    kept_indices: List[int]
    reasoning: str


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

    candidates_display = "\n".join(f"[{i}] {c}" for i, c in enumerate(candidates))
    user_prompt = (
        f"Invoice {invoice.invoice_number} for vendor {invoice.vendor.name}.\n"
        f"Candidate discrepancies (reference by index in your response):\n{candidates_display}"
    )

    try:
        decision = run_structured_agent(SYSTEM_PROMPT, user_prompt, JudgeDecision,
                                        model_id=settings.LLM_MODEL_JUDGE)
        kept = [candidates[i] for i in decision["kept_indices"] if 0 <= i < len(candidates)]
        result = {
            "status": decision["status"],
            "severity": decision["severity"],
            "discrepancies": kept,
            "reasoning": decision["reasoning"],
        }
    except Exception:
        logger.exception("judge failed for invoice %s", invoice.invoice_number)
        result = {
            "status": "discrepant", "severity": "minor",
            "discrepancies": candidates,
            "reasoning": "Judge response unavailable; defaulting to raw candidates.",
        }
    return result
