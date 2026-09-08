from django.db import models
from apps.core.models import TimeStampedModel, Workspace, Vendor


class ScanRun(TimeStampedModel):
    TRIGGER_CHOICES = [("webhook", "Webhook"), ("scheduled", "Scheduled"), ("manual", "Manual"), ("email", "Email")]
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="scan_runs")
    trigger = models.CharField(max_length=20, choices=TRIGGER_CHOICES)
    statistics = models.JSONField(default=dict, blank=True)  # {documents, matched, discrepant, errors}
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)


class Document(TimeStampedModel):
    TYPE_CHOICES = [
        ("po", "Purchase Order"),
        ("invoice", "Invoice"),
        ("delivery_receipt", "Delivery Receipt"),
        ("contract", "Contract"),
        ("other", "Other"),
    ]
    OCR_STATUS_CHOICES = [
        ("pending", "Pending"), ("not_needed", "Not needed (native text)"),
        ("running", "Running"), ("done", "Done"), ("low_confidence", "Low confidence"),
        ("failed", "Failed"),
    ]
    EXTRACTION_STATUS_CHOICES = [
        ("pending", "Pending"), ("running", "Running"),
        ("done", "Done"), ("failed", "Failed"),
    ]
    SOURCE_CHOICES = [("upload", "Upload"), ("email", "Email"), ("webhook", "Webhook")]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="documents")
    scan_run = models.ForeignKey(ScanRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="upload")
    file = models.FileField(upload_to="documents/")
    content_hash = models.CharField(max_length=64, db_index=True)  # SHA-256, idempotency key
    ocr_status = models.CharField(max_length=20, choices=OCR_STATUS_CHOICES, default="pending")
    extraction_status = models.CharField(max_length=20, choices=EXTRACTION_STATUS_CHOICES, default="pending")
    failure_reason = models.TextField(blank=True)
    raw_text = models.TextField(blank=True)
    extraction = models.JSONField(default=dict, blank=True)  # schema-enforced extracted fields
    confidence = models.FloatField(null=True, blank=True)  # overall extraction confidence 0-1
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "content_hash"])]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "content_hash"], name="uniq_doc_per_workspace_hash")
        ]

    def __str__(self):
        return f"{self.get_type_display()} · {self.id}"

    def delete(self, *args, **kwargs):
        file_name = self.file.name
        result = super().delete(*args, **kwargs)
        if file_name:
            self.file.storage.delete(file_name)
        return result


class LineItem(TimeStampedModel):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="line_items")
    sku = models.CharField(max_length=128, blank=True)
    description = models.CharField(max_length=512, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "position"], name="uniq_line_item_position")
        ]

    @property
    def total(self):
        return self.quantity * self.unit_price


class PurchaseOrder(TimeStampedModel):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="purchase_order")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="purchase_orders")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="purchase_orders")
    po_number = models.CharField(max_length=64, db_index=True)
    order_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)


class Invoice(TimeStampedModel):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="invoice")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invoices")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="invoices")
    invoice_number = models.CharField(max_length=64, db_index=True)
    referenced_po_number = models.CharField(max_length=64, blank=True)  # as extracted, may be loose/messy
    invoice_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)


class DeliveryReceipt(TimeStampedModel):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="delivery_receipt")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="delivery_receipts")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="delivery_receipts")
    referenced_po_number = models.CharField(max_length=64, blank=True)
    delivery_date = models.DateField(null=True, blank=True)
    is_partial = models.BooleanField(default=False)
