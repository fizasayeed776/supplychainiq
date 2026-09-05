from django.db import models
from apps.core.models import TimeStampedModel, Workspace
from apps.documents.models import Invoice, PurchaseOrder, DeliveryReceipt


class MatchResult(TimeStampedModel):
    STATUS_CHOICES = [
        ("pending", "Pending"), ("matched", "Matched"),
        ("discrepant", "Discrepant"), ("unmatched", "Unmatched"),
    ]
    SEVERITY_CHOICES = [("none", "None"), ("minor", "Minor"), ("major", "Major"), ("critical", "Critical")]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="match_results")
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name="match_result")
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True)
    delivery_receipt = models.ForeignKey(DeliveryReceipt, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    discrepancies = models.JSONField(default=list, blank=True)
    # [{field, expected, actual, delta, reasoning}]
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="none")
    agent_reasoning = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_matches"
    )
    review_action = models.CharField(
        max_length=20, blank=True,
        choices=[("accept", "Accepted discrepancy"), ("dispute", "Dispute"), ("false_positive", "False positive")],
    )

    class Meta:
        indexes = [models.Index(fields=["workspace", "status", "severity"])]
