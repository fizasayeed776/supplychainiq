from rest_framework import serializers
from .models import Document, LineItem, PurchaseOrder, Invoice, DeliveryReceipt, ScanRun


class LineItemSerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = LineItem
        fields = ["id", "sku", "description", "quantity", "unit_price", "currency", "position", "total"]


class DocumentSerializer(serializers.ModelSerializer):
    line_items = LineItemSerializer(many=True, read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default=None)

    class Meta:
        model = Document
        fields = [
            "id", "workspace", "type", "source", "file", "content_hash", "ocr_status",
            "extraction_status", "failure_reason", "raw_text", "extraction", "confidence", "vendor", "vendor_name",
            "line_items", "created_at",
        ]
        read_only_fields = [
            "content_hash", "ocr_status", "extraction_status", "failure_reason",
            "raw_text", "confidence",
        ]


class DocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "workspace", "type", "vendor", "file"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    line_items = LineItemSerializer(source="document.line_items", many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = ["id", "document", "workspace", "vendor", "po_number", "order_date",
                  "currency", "total_amount", "line_items"]


class InvoiceSerializer(serializers.ModelSerializer):
    line_items = LineItemSerializer(source="document.line_items", many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = ["id", "document", "workspace", "vendor", "invoice_number",
                  "referenced_po_number", "invoice_date", "due_date", "currency",
                  "total_amount", "line_items"]


class DeliveryReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryReceipt
        fields = ["id", "document", "workspace", "vendor", "referenced_po_number",
                  "delivery_date", "is_partial"]


class ScanRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScanRun
        fields = ["id", "workspace", "trigger", "statistics", "started_at", "finished_at", "duration_seconds"]
