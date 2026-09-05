from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import MatchResult
from .serializers import MatchResultSerializer


class MatchResultViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MatchResult.objects.select_related(
        "invoice", "invoice__vendor", "invoice__document",
        "purchase_order", "purchase_order__document",
        "delivery_receipt", "delivery_receipt__document",
    ).prefetch_related(
        "invoice__document__line_items",
        "purchase_order__document__line_items",
        "delivery_receipt__document__line_items",
    ).all().order_by("-created_at")
    serializer_class = MatchResultSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["workspace", "status", "severity"]

    def get_queryset(self):
        return super().get_queryset().filter(workspace__members=self.request.user)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """Accept / dispute / mark-false-positive a discrepancy (human-in-the-loop)."""
        match = self.get_object()
        action_value = request.data.get("action")
        if action_value not in {"accept", "dispute", "false_positive"}:
            return Response({"detail": "invalid action"}, status=status.HTTP_400_BAD_REQUEST)

        match.review_action = action_value
        match.reviewed_by = request.user
        match.save(update_fields=["review_action", "reviewed_by"])

        if action_value == "dispute":
            from apps.workflow.tasks import draft_dispute_email
            draft_dispute_email.delay(str(match.id))

        return Response(MatchResultSerializer(match).data)
