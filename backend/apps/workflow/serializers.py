from rest_framework import serializers
from .models import ApprovalFlow, ApprovalStep, Dispute, TriageRule


class ApprovalStepSerializer(serializers.ModelSerializer):
    approver_name = serializers.CharField(source="approver.username", read_only=True, default=None)

    class Meta:
        model = ApprovalStep
        fields = ["id", "order", "approver", "approver_name", "decision", "decided_at", "escalation_deadline"]


class ApprovalFlowSerializer(serializers.ModelSerializer):
    steps = ApprovalStepSerializer(many=True, read_only=True)
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    vendor_name = serializers.CharField(source="invoice.vendor.name", read_only=True)

    class Meta:
        model = ApprovalFlow
        fields = ["id", "workspace", "invoice", "invoice_number", "vendor_name", "state", "steps", "created_at"]


class ApprovalDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approved", "rejected"])
    comment = serializers.CharField(required=False, allow_blank=True)


class DisputeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dispute
        fields = ["id", "match_result", "email_subject", "email_body", "status", "sent_at"]
        read_only_fields = ["email_subject", "email_body"]


class TriageRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = TriageRule
        fields = ["id", "workspace", "name", "max_amount", "max_vendor_risk_score", "require_status", "active"]
