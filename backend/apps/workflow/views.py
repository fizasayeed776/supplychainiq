from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ApprovalFlow, ApprovalStep, Dispute, TriageRule
from apps.core.models import WorkspaceMembership
from apps.core.permissions import IsAtLeastViewer, IsAtLeastReviewer, IsAtLeastAdmin
from .serializers import (
    ApprovalFlowSerializer, ApprovalDecisionSerializer, DisputeSerializer,
    TriageRuleSerializer, PendingStepSerializer,
)


class WorkspaceScopedMixin:
    def get_queryset(self):
        return super().get_queryset().filter(workspace__members=self.request.user)


class ApprovalFlowViewSet(WorkspaceScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ApprovalFlow.objects.select_related("invoice", "invoice__vendor").prefetch_related("steps").all()
    serializer_class = ApprovalFlowSerializer
    # Viewers can read; approve/dispute/mark_paid actions enforce higher roles
    # via has_object_permission on IsAtLeastReviewer / IsAtLeastAdmin.
    permission_classes = [permissions.IsAuthenticated, IsAtLeastViewer]
    filterset_fields = ["workspace", "state"]

    def get_permissions(self):
        """Escalate permission requirement for mutating actions."""
        if self.action == "decide":
            return [permissions.IsAuthenticated(), IsAtLeastReviewer()]
        if self.action == "mark_paid":
            return [permissions.IsAuthenticated(), IsAtLeastAdmin()]
        return super().get_permissions()

    @action(detail=False, methods=["get"], url_path="pending-steps")
    def pending_steps(self, request):
        """Return a flat list of pending ApprovalSteps that have an
        escalation_deadline set, scoped to the authenticated user's workspaces.

        Optional query params:
          - workspace: filter to a single workspace ID
          - overdue: 'true' returns only steps past their deadline

        Used by the Dashboard SLA countdown panel.
        """
        qs = (
            ApprovalStep.objects
            .filter(
                decision="pending",
                escalation_deadline__isnull=False,
                flow__workspace__members=request.user,
            )
            .select_related("flow", "flow__invoice", "flow__invoice__vendor", "approver")
            .order_by("escalation_deadline")
        )

        workspace_id = request.query_params.get("workspace")
        if workspace_id:
            qs = qs.filter(flow__workspace_id=workspace_id)

        overdue = request.query_params.get("overdue", "").lower()
        if overdue == "true":
            from django.utils import timezone as tz
            qs = qs.filter(escalation_deadline__lt=tz.now())

        serializer = PendingStepSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        """Human approver acts on the current pending step."""
        flow = self.get_object()
        membership = WorkspaceMembership.objects.filter(workspace=flow.workspace, user=request.user).first()
        if not membership or membership.role not in {"owner", "admin", "reviewer"}:
            return Response({"detail": "approval role required"}, status=status.HTTP_403_FORBIDDEN)
        serializer = ApprovalDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data["decision"]

        step = flow.steps.filter(decision="pending").order_by("order").first()
        if not step:
            return Response({"detail": "no pending step"}, status=status.HTTP_400_BAD_REQUEST)

        step.decision = decision
        step.approver = request.user
        step.decided_at = timezone.now()
        step.decision_actor = request.user.username
        step.save(update_fields=["decision", "approver", "decided_at", "decision_actor"])

        if decision == "approved" and flow.state == "pending_review":
            flow.approve()
            flow.save()
        elif decision == "rejected" and flow.state == "pending_review":
            flow.dispute()
            flow.save()

        async_to_sync(get_channel_layer().group_send)(
            f"approval_room_{flow.invoice_id}",
            {
                "type": "status_change",
                "payload": {
                    "invoice_id": str(flow.invoice_id),
                    "state": flow.state,
                    "decision": decision,
                    "user": request.user.username,
                },
            },
        )

        return Response(ApprovalFlowSerializer(flow).data)

    @action(detail=True, methods=["post"])
    def mark_paid(self, request, pk=None):
        flow = self.get_object()
        membership = WorkspaceMembership.objects.filter(workspace=flow.workspace, user=request.user).first()
        if not membership or membership.role not in {"owner", "admin"}:
            return Response({"detail": "owner or admin role required"}, status=status.HTTP_403_FORBIDDEN)
        flow.mark_paid()
        flow.save()
        return Response(ApprovalFlowSerializer(flow).data)


class DisputeViewSet(viewsets.ModelViewSet):
    queryset = Dispute.objects.select_related("match_result", "match_result__invoice").all()
    serializer_class = DisputeSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return super().get_queryset().filter(match_result__workspace__members=self.request.user)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """One-click send after human review of the AI-drafted email."""
        from django.core.mail import send_mail
        from django.conf import settings

        dispute = self.get_object()
        vendor_email = next(
            (c.get("email") for c in dispute.match_result.invoice.vendor.contacts if c.get("email")), None
        )
        if not vendor_email:
            return Response({"detail": "vendor has no contact email on file"}, status=status.HTTP_400_BAD_REQUEST)

        send_mail(dispute.email_subject, dispute.email_body, settings.DEFAULT_FROM_EMAIL, [vendor_email])
        dispute.status = "sent"
        dispute.sent_at = timezone.now()
        dispute.save(update_fields=["status", "sent_at"])
        return Response(DisputeSerializer(dispute).data)


class TriageRuleViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = TriageRule.objects.all()
    serializer_class = TriageRuleSerializer
    permission_classes = [permissions.IsAuthenticated, IsAtLeastAdmin]
    filterset_fields = ["workspace", "active"]
