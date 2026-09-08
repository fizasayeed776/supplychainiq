from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import JsonResponse
from .models import Workspace, Vendor, Contract
from .serializers import WorkspaceSerializer, VendorSerializer, ContractSerializer, _compute_spend_summary
from .permissions import IsAtLeastViewer, IsAtLeastAdmin


def health_check(request):
    return JsonResponse({"status": "ok"})


class WorkspaceScopedMixin:
    """Restrict querysets to workspaces the requesting user belongs to."""

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(workspace__members=self.request.user)


class WorkspaceViewSet(viewsets.ModelViewSet):
    queryset = Workspace.objects.all()
    serializer_class = WorkspaceSerializer
    # GET: any member; mutating workspace settings requires admin+
    permission_classes = [permissions.IsAuthenticated, IsAtLeastAdmin]

    def get_queryset(self):
        # Order by created_at ascending so the earliest (real) workspace is
        # always [0] in AuthContext — prevents a later "demo" workspace
        # created by scripts/email polling from shadowing the primary tenant.
        return Workspace.objects.filter(members=self.request.user).order_by("created_at")


class VendorViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Vendor.objects.all().order_by("-risk_score")
    serializer_class = VendorSerializer
    # Viewers can read vendors; creating/editing requires admin+
    permission_classes = [permissions.IsAuthenticated, IsAtLeastAdmin]
    filterset_fields = ["workspace"]

    @action(detail=True, methods=["get"], url_path="spend-summary")
    def spend_summary(self, request, pk=None):
        """Return a fresh spend summary for a single vendor.

        Identical data to the ``spend_summary`` field on the list/detail
        serializer, but available as a dedicated endpoint so callers can
        refresh it without re-fetching the whole vendor record.
        """
        vendor = self.get_object()
        return Response(_compute_spend_summary(vendor))


class ContractViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Contract.objects.select_related("vendor").all()
    serializer_class = ContractSerializer
    permission_classes = [permissions.IsAuthenticated, IsAtLeastAdmin]
    filterset_fields = ["workspace", "vendor", "status"]
