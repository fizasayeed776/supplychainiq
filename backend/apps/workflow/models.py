from django.conf import settings
from django.db import models
from django_fsm import FSMField, transition

from apps.core.models import TimeStampedModel, Workspace
from apps.documents.models import Invoice
from apps.matching.models import MatchResult


class ApprovalFlow(TimeStampedModel):
    """State machine per invoice: draft -> pending_review -> approved/disputed -> paid."""
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="approval_flows")
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name="approval_flow")
    state = FSMField(default="draft")

    @transition(field=state, source="draft", target="pending_review")
    def submit_for_review(self):
        pass

    @transition(field=state, source="pending_review", target="approved")
    def approve(self):
        pass

    @transition(field=state, source="pending_review", target="disputed")
    def dispute(self):
        pass

    @transition(field=state, source="disputed", target="pending_review")
    def resubmit(self):
        pass

    @transition(field=state, source="approved", target="paid")
    def mark_paid(self):
        pass


class ApprovalStep(TimeStampedModel):
    DECISION_CHOICES = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("escalated", "Escalated")]
    flow = models.ForeignKey(ApprovalFlow, on_delete=models.CASCADE, related_name="steps")
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="approval_steps")
    order = models.PositiveIntegerField(default=0)
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, default="pending")
    decided_at = models.DateTimeField(null=True, blank=True)
    escalation_deadline = models.DateTimeField(null=True, blank=True)
    decision_actor = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["order"]


class Dispute(TimeStampedModel):
    STATUS_CHOICES = [("draft", "Draft"), ("sent", "Sent"), ("resolved", "Resolved")]
    match_result = models.OneToOneField(MatchResult, on_delete=models.CASCADE, related_name="dispute")
    email_subject = models.CharField(max_length=255, blank=True)
    email_body = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    sent_at = models.DateTimeField(null=True, blank=True)


class TriageRule(TimeStampedModel):
    """User-defined auto-approval rules, e.g. 'auto-approve matched invoices
    under $500 from low-risk vendors', evaluated on match completion."""
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="triage_rules")
    name = models.CharField(max_length=255)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    max_vendor_risk_score = models.FloatField(null=True, blank=True)
    require_status = models.CharField(max_length=20, default="matched")
    active = models.BooleanField(default=True)

    def matches(self, invoice, match_result) -> bool:
        if not self.active or match_result.status != self.require_status:
            return False
        if self.max_amount is not None and (invoice.total_amount or 0) > self.max_amount:
            return False
        if self.max_vendor_risk_score is not None and invoice.vendor.risk_score > self.max_vendor_risk_score:
            return False
        return True


class WebhookDelivery(TimeStampedModel):
    """Outbound webhook attempt log, for debugging Teams/generic alerts."""
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="webhook_deliveries")
    url = models.URLField()
    payload = models.JSONField()
    status_code = models.PositiveIntegerField(null=True, blank=True)
    attempt = models.PositiveIntegerField(default=1)
    success = models.BooleanField(default=False)
    error = models.TextField(blank=True)
