import uuid
from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Workspace(TimeStampedModel):
    """A company/team; owns all other entities."""
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="WorkspaceMembership", related_name="workspaces"
    )
    settings_json = models.JSONField(default=dict, blank=True)
    webhook_secret = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.name


class WorkspaceMembership(TimeStampedModel):
    ROLE_CHOICES = [("owner", "Owner"), ("admin", "Admin"), ("reviewer", "Reviewer"), ("viewer", "Viewer")]
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="viewer")

    class Meta:
        unique_together = ("workspace", "user")


class Vendor(TimeStampedModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="vendors")
    name = models.CharField(max_length=255)
    contacts = models.JSONField(default=list, blank=True)  # [{name, email, phone}]
    payment_terms_days = models.PositiveIntegerField(default=30)
    risk_score = models.FloatField(default=0.0)  # 0 (low) - 100 (high)
    risk_factors = models.JSONField(default=dict, blank=True)
    risk_explanation = models.TextField(blank=True)
    risk_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("workspace", "name")
        indexes = [models.Index(fields=["workspace", "risk_score"])]

    def __str__(self):
        return self.name


class Contract(TimeStampedModel):
    STATUS_CHOICES = [("active", "Active"), ("expiring", "Expiring soon"), ("expired", "Expired"), ("draft", "Draft")]
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="contracts")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="contracts")
    source_document_id = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    file = models.FileField(upload_to="contracts/", null=True, blank=True)
    terms = models.JSONField(default=dict, blank=True)  # {rate_cards, payment_days, sla}
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    def __str__(self):
        return f"{self.vendor.name} contract ({self.status})"
