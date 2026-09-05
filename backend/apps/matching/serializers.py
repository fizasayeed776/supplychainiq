from rest_framework import serializers
from .models import MatchResult


class _LineItemInlineSerializer(serializers.Serializer):
    sku = serializers.CharField()
    description = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=4)
    currency = serializers.CharField()


class _InvoiceDetailSerializer(serializers.Serializer):
    invoice_number = serializers.CharField()
    invoice_date = serializers.DateField(allow_null=True)
    due_date = serializers.DateField(allow_null=True)
    currency = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    line_items = serializers.SerializerMethodField()

    def get_line_items(self, obj):
        return _LineItemInlineSerializer(obj.document.line_items.all(), many=True).data


class _PODetailSerializer(serializers.Serializer):
    po_number = serializers.CharField()
    order_date = serializers.DateField(allow_null=True)
    currency = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    line_items = serializers.SerializerMethodField()

    def get_line_items(self, obj):
        return _LineItemInlineSerializer(obj.document.line_items.all(), many=True).data


class _DRDetailSerializer(serializers.Serializer):
    referenced_po_number = serializers.CharField()
    delivery_date = serializers.DateField(allow_null=True)
    is_partial = serializers.BooleanField()
    line_items = serializers.SerializerMethodField()

    def get_line_items(self, obj):
        return _LineItemInlineSerializer(obj.document.line_items.all(), many=True).data


class MatchResultSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    vendor_name = serializers.CharField(source="invoice.vendor.name", read_only=True)
    invoice_detail = serializers.SerializerMethodField()
    po_detail = serializers.SerializerMethodField()
    dr_detail = serializers.SerializerMethodField()

    class Meta:
        model = MatchResult
        fields = [
            "id", "workspace", "invoice", "invoice_number", "vendor_name",
            "purchase_order", "delivery_receipt", "status", "discrepancies",
            "severity", "agent_reasoning", "reviewed_by", "review_action", "created_at",
            "invoice_detail", "po_detail", "dr_detail",
        ]
        read_only_fields = [
            "status", "discrepancies", "severity", "agent_reasoning",
        ]

    def get_invoice_detail(self, obj):
        return _InvoiceDetailSerializer(obj.invoice).data

    def get_po_detail(self, obj):
        return _PODetailSerializer(obj.purchase_order).data if obj.purchase_order else None

    def get_dr_detail(self, obj):
        return _DRDetailSerializer(obj.delivery_receipt).data if obj.delivery_receipt else None
