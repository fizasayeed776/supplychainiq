"""
Risk Analyst agent. Recomputes a vendor's risk score from discrepancy
history, contract status, and delivery punctuality, and explains it in
plain language for the Vendors page.
"""
import logging
from typing import Optional

from django.utils import timezone
from pydantic import BaseModel

from .client import run_structured_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Risk Analyst agent for procurement vendor management.
Given a vendor's discrepancy history, contract status, and delivery record,
compute a risk_score from 0 (very low risk) to 100 (very high risk) and
explain the score in 2-3 plain-language sentences a procurement manager
would understand, referencing the concrete evidence.
Respond ONLY with JSON: {"risk_score": number, "risk_factors": {...}, "explanation": "..."}
"""


class RiskFactors(BaseModel):
    total_invoices: Optional[int] = None
    discrepant_invoices: Optional[int] = None
    critical_discrepancies: Optional[int] = None
    expired_contracts: Optional[int] = None
    discrepancy_rate: Optional[float] = None


class RiskAssessment(BaseModel):
    risk_score: float
    risk_factors: RiskFactors
    explanation: str


def compute_vendor_risk(vendor) -> dict:
    match_results = vendor.invoices.select_related("match_result").all()
    total = match_results.count()
    discrepant = sum(1 for i in match_results if getattr(i, "match_result", None)
                     and i.match_result.status == "discrepant")
    # Only count critical severity on *discrepant* results. An "unmatched" result
    # is assigned severity="critical" by the orchestrator to signal "no PO found" —
    # that is a matching gap, not a discrepancy, and must not inflate the risk score.
    critical = sum(1 for i in match_results if getattr(i, "match_result", None)
                   and i.match_result.status == "discrepant"
                   and i.match_result.severity == "critical")
    expired_contracts = vendor.contracts.filter(status="expired").count()

    evidence = {
        "total_invoices": total,
        "discrepant_invoices": discrepant,
        "critical_discrepancies": critical,
        "expired_contracts": expired_contracts,
        "discrepancy_rate": round(discrepant / total, 3) if total else 0.0,
    }

    try:
        result = run_structured_agent(
            SYSTEM_PROMPT,
            f"Vendor: {vendor.name}\nEvidence: {evidence}",
            RiskAssessment,
            use_cache=False,  # risk changes as new invoices land; don't serve stale scores
        )
    except Exception:
        logger.exception("compute_vendor_risk failed for vendor %s", vendor.name)
        result = {
            "risk_score": min(100, discrepant * 10 + critical * 20 + expired_contracts * 15),
            "risk_factors": evidence,
            "explanation": "Heuristic fallback score (LLM unavailable).",
        }

    result["computed_at"] = timezone.now().isoformat()
    return result
