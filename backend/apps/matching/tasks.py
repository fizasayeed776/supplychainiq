import logging

from celery import shared_task, group, chord
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
    Safe to re-run: it fully recomputes and overwrites the MatchResult.

    Returns a chord-compatible dict so finalize_nightly_rematch can aggregate
    results across the whole nightly batch without an extra DB query.
    """
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

        # Return a small summary dict — consumed by finalize_nightly_rematch
        # when this task is part of a chord.  Must be JSON-serializable.
        return {
            "invoice_id": str(invoice.id),
            "status": result["status"],
            "severity": result["severity"],
        }

    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def finalize_nightly_rematch(results, workspace_id):
    """Chord callback: runs once after all try_three_way_match tasks for a
    single workspace finish.

    ``results`` is a list of the dicts returned by try_three_way_match — one
    entry per invoice that was re-matched.  Tasks that raised (and exhausted
    retries) will appear as None in the list; we skip those gracefully.

    Actions:
    1. Aggregate matched vs discrepant counts.
    2. Publish a single summary event to the workspace's dashboard group.
    3. If any new discrepancies were found, post a Teams/generic webhook
       summary via the existing post_signed_webhook helper.
    """
    from apps.core.models import Workspace
    from apps.workflow.outbound import post_signed_webhook

    total = len(results)
    discrepant = sum(1 for r in results if r and r.get("status") == "discrepant")
    matched = sum(1 for r in results if r and r.get("status") == "matched")
    critical = sum(1 for r in results if r and r.get("severity") == "critical")
    failed = sum(1 for r in results if r is None)

    summary = {
        "event": "nightly_rematch_complete",
        "workspace_id": str(workspace_id),
        "total": total,
        "matched": matched,
        "discrepant": discrepant,
        "critical": critical,
        "failed": failed,
    }

    logger.info("finalize_nightly_rematch workspace=%s %s", workspace_id, summary)

    # Push summary to the live dashboard.
    _publish(workspace_id, {**summary, "stage": "nightly_rematch_complete"})

    # Stamp the most-recent ScanRun for this workspace with an LLM usage snapshot
    # so per-run cost/cache data is visible in the API alongside match counts.
    try:
        from apps.documents.models import ScanRun
        from apps.agents.usage import get_snapshot
        from django.utils import timezone

        scan_run = (
            ScanRun.objects
            .filter(workspace_id=workspace_id)
            .order_by("-started_at")
            .first()
        )
        if scan_run is not None:
            existing = scan_run.statistics or {}
            existing.update({
                **summary,
                "llm_usage": get_snapshot(),
                "finished_at": timezone.now().isoformat(),
            })
            scan_run.statistics = existing
            scan_run.finished_at = timezone.now()
            scan_run.save(update_fields=["statistics", "finished_at"])
    except Exception:
        logger.exception("finalize_nightly_rematch: failed to stamp ScanRun statistics")

    # Outbound Teams/generic webhook — only when new discrepancies were found.
    if discrepant > 0:
        try:
            workspace = Workspace.objects.get(id=workspace_id)
            urls = (workspace.settings_json or {}).get("outbound_webhook_urls", [])
            for url in urls:
                post_signed_webhook(workspace, url, summary)
        except Workspace.DoesNotExist:
            logger.warning("finalize_nightly_rematch: workspace %s not found", workspace_id)

    return summary


@shared_task
def rematch_all_open_invoices():
    """Beat schedule: nightly full re-match, e.g. after contract terms change.

    Uses one celery.chord per workspace so that:
    - All invoices in a workspace are matched in parallel (group fan-out).
    - A single finalize_nightly_rematch callback fires per workspace once all
      its invoices are done, aggregating counts and publishing one summary
      event rather than N individual events.
    """
    from collections import defaultdict

    open_invoices = (
        Invoice.objects
        .exclude(match_result__status="matched")
        .values("id", "workspace_id")
    )

    # Bucket invoice IDs by workspace so each workspace gets its own chord.
    by_workspace = defaultdict(list)
    for row in open_invoices:
        by_workspace[str(row["workspace_id"])].append(str(row["id"]))

    chords_queued = 0
    total_invoices = 0

    for workspace_id, invoice_ids in by_workspace.items():
        match_group = group(
            try_three_way_match.s(invoice_id) for invoice_id in invoice_ids
        )
        callback = finalize_nightly_rematch.s(workspace_id)
        chord(match_group)(callback)
        chords_queued += 1
        total_invoices += len(invoice_ids)

    return {"chords_queued": chords_queued, "total_invoices": total_invoices}
