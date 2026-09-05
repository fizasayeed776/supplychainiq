import logging

from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from apps.documents.models import Invoice
from .models import MatchResult

logger = logging.getLogger(__name__)


def _publish(workspace_id, payload):
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(f"dashboard_{workspace_id}", {"type": "pipeline.progress", "payload": payload})


@shared_task(bind=True, max_retries=3, retry_backoff=True, acks_late=True)
def try_three_way_match(self, invoice_id):
    """Runs the Matcher -> Comparator -> Judge agent chain for one invoice.
    Safe to re-run: it fully recomputes and overwrites the MatchResult."""
    from apps.agents.orchestrator import run_three_way_match

    invoice = Invoice.objects.select_related("vendor", "workspace").get(id=invoice_id)
    _publish(invoice.workspace_id, {"invoice": str(invoice.id), "stage": "matching_started"})

    try:
        result = run_three_way_match(invoice)
        MatchResult.objects.update_or_create(
            invoice=invoice,
            defaults={
                "workspace": invoice.workspace,
                "purchase_order": result.get("purchase_order"),
                "delivery_receipt": result.get("delivery_receipt"),
                "status": result["status"],
                "discrepancies": result["discrepancies"],
                "severity": result["severity"],
                "agent_reasoning": result["reasoning"],
            },
        )
        from apps.agents.tasks import recompute_vendor_risk
        recompute_vendor_risk.delay(str(invoice.vendor_id))
        _publish(invoice.workspace_id, {
            "invoice": str(invoice.id), "stage": "matching_done",
            "status": result["status"], "severity": result["severity"],
        })

        if result["status"] == "discrepant" and result["severity"] in ("major", "critical"):
            from apps.workflow.tasks import notify_critical_discrepancy
            notify_critical_discrepancy.delay(str(invoice.id))
        if result["status"] == "discrepant":
            from apps.workflow.tasks import draft_dispute_email
            draft_dispute_email.delay(str(invoice.match_result.id))

        from apps.workflow.tasks import advance_approval_flow
        advance_approval_flow.delay(str(invoice.id))

    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def rematch_all_open_invoices():
    """Beat schedule: nightly full re-match, e.g. after contract terms change."""
    ids = list(
        Invoice.objects.exclude(match_result__status="matched").values_list("id", flat=True)
    )
    for invoice_id in ids:
        try_three_way_match.delay(str(invoice_id))
    return {"queued": len(ids)}
