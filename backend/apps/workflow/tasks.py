import logging
from datetime import timedelta

import requests
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.utils import timezone

from apps.documents.models import Invoice
from apps.matching.models import MatchResult
from apps.core.models import Workspace, Contract
from .models import ApprovalFlow, ApprovalStep, Dispute, TriageRule, WebhookDelivery

logger = logging.getLogger(__name__)


def _publish_sla(workspace_id, payload: dict) -> None:
    """Push an sla_deadline_update message to the workspace's dashboard group.

    Called whenever an ApprovalStep's escalation_deadline is first set (on
    creation) or changes (on escalation), so the Dashboard SLA panel can
    refresh without polling more frequently than necessary.
    """
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(
        f"dashboard_{workspace_id}",
        {"type": "sla.deadline.update", "payload": payload},
    )


@shared_task
def advance_approval_flow(invoice_id):
    """Runs on every match completion: creates the flow if needed, then
    applies triage rules for possible auto-approval."""
    invoice = Invoice.objects.select_related("workspace", "vendor", "match_result").get(id=invoice_id)
    flow, _ = ApprovalFlow.objects.get_or_create(workspace=invoice.workspace, invoice=invoice)
    match_result = getattr(invoice, "match_result", None)
    if not match_result:
        return

    if flow.state == "draft":
        flow.submit_for_review()
        flow.save()
        step, _ = ApprovalStep.objects.get_or_create(
            flow=flow, order=1,
            defaults={"escalation_deadline": timezone.now() + timedelta(days=2)},
        )
        if step.escalation_deadline:
            _publish_sla(invoice.workspace_id, {
                "step_id": step.id,
                "flow_id": flow.id,
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "vendor": invoice.vendor.name,
                "escalation_deadline": step.escalation_deadline.isoformat(),
                "decision": step.decision,
                "event": "step_created",
            })

    for rule in TriageRule.objects.filter(workspace=invoice.workspace, active=True):
        if rule.matches(invoice, match_result) and flow.state == "pending_review":
            flow.approve()
            flow.save()
            ApprovalStep.objects.filter(flow=flow, decision="pending").update(
                decision="approved", decided_at=timezone.now(), decision_actor=f"triage:{rule.name}"
            )
            break

    if match_result.status == "discrepant" and flow.state == "pending_review":
        flow.dispute()
        flow.save()


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def draft_dispute_email(self, match_result_id):
    from apps.agents.dispute_drafter import draft_dispute_email as run_drafter

    match_result = MatchResult.objects.select_related("invoice", "invoice__vendor").get(id=match_result_id)
    try:
        draft = run_drafter(match_result)
        Dispute.objects.update_or_create(
            match_result=match_result,
            defaults={"email_subject": draft["subject"], "email_body": draft["body"], "status": "draft"},
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def notify_critical_discrepancy(invoice_id):
    """Outbound webhook: post a signed alert to the workspace's configured
    Microsoft Teams / generic webhook URL when a critical discrepancy lands."""
    from .outbound import post_signed_webhook

    invoice = Invoice.objects.select_related("workspace", "match_result").get(id=invoice_id)
    workspace = invoice.workspace
    urls = (workspace.settings_json or {}).get("outbound_webhook_urls", [])
    payload = {
        "event": "critical_discrepancy",
        "invoice_number": invoice.invoice_number,
        "vendor": invoice.vendor.name,
        "severity": invoice.match_result.severity,
        "discrepancies": invoice.match_result.discrepancies,
    }
    for url in urls:
        post_signed_webhook(workspace, url, payload)


@shared_task
def escalate_overdue_steps():
    """Beat: every 15 min, escalate any approval step past its deadline."""
    overdue = ApprovalStep.objects.filter(decision="pending", escalation_deadline__lt=timezone.now())
    escalated = 0
    for step in overdue:
        step.decision = "escalated"
        step.decided_at = timezone.now()
        step.decision_actor = "system:escalation"
        step.save(update_fields=["decision", "decided_at", "decision_actor"])
        next_approver = step.flow.workspace.members.filter(
            workspacemembership__role__in=["owner", "admin", "reviewer"]
        ).exclude(id=step.approver_id).order_by("id").first()
        next_step, created = ApprovalStep.objects.get_or_create(
            flow=step.flow, order=step.order + 1,
            defaults={"approver": next_approver, "escalation_deadline": timezone.now() + timedelta(days=1)},
        )
        # Notify the dashboard that SLA deadlines have changed: the old step
        # is now escalated (no further countdown) and a fresh step was created.
        workspace_id = step.flow.workspace_id
        _publish_sla(workspace_id, {
            "step_id": step.id,
            "flow_id": step.flow_id,
            "invoice_id": str(step.flow.invoice_id),
            "decision": step.decision,
            "event": "step_escalated",
        })
        if created and next_step.escalation_deadline:
            _publish_sla(workspace_id, {
                "step_id": next_step.id,
                "flow_id": next_step.flow_id,
                "invoice_id": str(next_step.flow.invoice_id),
                "escalation_deadline": next_step.escalation_deadline.isoformat(),
                "decision": next_step.decision,
                "event": "step_created",
            })
        from .outbound import post_signed_webhook
        urls = (step.flow.workspace.settings_json or {}).get("outbound_webhook_urls", [])
        for url in urls:
            post_signed_webhook(step.flow.workspace, url, {
                "event": "approval_escalated", "invoice": str(step.flow.invoice_id),
            })
        escalated += 1
    return {"escalated": escalated}


@shared_task
def sync_fx_rates():
    """Beat: daily FX-rate sync from frankfurter.app (free, keyless ECB data)."""
    from django.core.cache import cache
    from django.conf import settings as dj_settings

    response = requests.get(f"{dj_settings.FX_RATES_BASE_URL}/latest", timeout=15)
    response.raise_for_status()
    rates = response.json()
    cache.set("fx_rates:latest", rates, timeout=60 * 60 * 24 * 2)
    return rates


@shared_task
def check_contract_expiry():
    """Beat: daily; flags contracts expiring within 30 days or already expired."""
    today = timezone.now().date()
    soon = today + timedelta(days=30)

    expiring = Contract.objects.filter(valid_until__lte=soon, valid_until__gt=today).exclude(status="expiring")
    expiring_count = expiring.count()
    expiring.update(status="expiring")

    expired = Contract.objects.filter(valid_until__lte=today).exclude(status="expired")
    expired_count = expired.count()
    for contract in expired:
        from .outbound import post_signed_webhook
        urls = (contract.workspace.settings_json or {}).get("outbound_webhook_urls", [])
        for url in urls:
            post_signed_webhook(contract.workspace, url, {
                "event": "contract_expired", "vendor": contract.vendor.name,
                "valid_until": str(contract.valid_until),
            })
    expired.update(status="expired")
    return {"expiring": expiring_count, "expired": expired_count}


@shared_task
def send_weekly_compliance_report():
    """Beat: weekly; renders an HTML report and emails it (Mailpit in dev)
    + posts a summary to Microsoft Teams.  An Excel workbook attachment
    (compliance_report.xlsx) is generated via openpyxl and attached to the
    email so recipients can open it in Excel without logging into the app."""
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.conf import settings as dj_settings
    from .report_export import build_compliance_workbook

    for workspace in Workspace.objects.all():
        stats = _compliance_stats(workspace)
        html = render_to_string("workflow/weekly_report.html", {"workspace": workspace, "stats": stats})
        email = EmailMultiAlternatives(
            subject=f"SupplyChainIQ weekly compliance report — {workspace.name}",
            body="View this email in an HTML-capable client.",
            from_email=dj_settings.DEFAULT_FROM_EMAIL,
            to=[m.email for m in workspace.members.all() if m.email],
        )
        email.attach_alternative(html, "text/html")

        # Attach the Excel workbook if openpyxl is available.
        wb_bytes = build_compliance_workbook(workspace, stats)
        if wb_bytes:
            email.attach(
                f"compliance_report_{workspace.slug}.xlsx",
                wb_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        email.send(fail_silently=True)

        from .outbound import post_signed_webhook
        urls = (workspace.settings_json or {}).get("outbound_webhook_urls", [])
        for url in urls:
            post_signed_webhook(workspace, url, {
                "event": "weekly_compliance_report",
                "stats": stats,
                "note": "Excel attachment sent by email; see compliance_report.xlsx.",
            })


def _compliance_stats(workspace) -> dict:
    invoices = Invoice.objects.filter(workspace=workspace)
    matches = MatchResult.objects.filter(workspace=workspace)
    from .models import Dispute
    return {
        "total_invoices": invoices.count(),
        "discrepant": matches.filter(status="discrepant").count(),
        "critical": matches.filter(severity="critical").count(),
        "expired_contracts": Contract.objects.filter(workspace=workspace, status="expired").count(),
        "open_disputes": Dispute.objects.filter(
            match_result__workspace=workspace, status__in=["draft", "sent"]
        ).count(),
    }
