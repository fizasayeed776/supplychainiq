from rest_framework import serializers
from .models import ApprovalFlow, ApprovalStep, Dispute, TriageRule


class ApprovalStepSerializer(serializers.ModelSerializer):
    approver_name = serializers.CharField(source="approver.username", read_only=True, default=None)

    class Meta:
        model = ApprovalStep
        fields = [
            "id", "order", "approver", "approver_name",
            "decision", "decided_at", "escalation_deadline",
            "decision_actor",
        ]


class PendingStepSerializer(serializers.ModelSerializer):
    """Flat representation used by the Dashboard SLA countdown panel.

    Returns every pending ApprovalStep (decision='pending') that has an
    escalation_deadline set, along with enough invoice/vendor context for
    the UI to render a labelled countdown without a second request.
    """

    approver_name = serializers.CharField(source="approver.username", read_only=True, default=None)
    flow_id = serializers.IntegerField(source="flow.id", read_only=True)
    flow_state = serializers.CharField(source="flow.state", read_only=True)
    invoice_id = serializers.UUIDField(source="flow.invoice.id", read_only=True)
    invoice_number = serializers.CharField(source="flow.invoice.invoice_number", read_only=True)
    vendor_name = serializers.CharField(source="flow.invoice.vendor.name", read_only=True)
    workspace = serializers.IntegerField(source="flow.workspace_id", read_only=True)

    class Meta:
        model = ApprovalStep
        fields = [
            "id", "order", "decision", "decided_at", "escalation_deadline",
            "approver", "approver_name",
            "flow_id", "flow_state",
            "invoice_id", "invoice_number", "vendor_name",
            "workspace",
        ]


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
