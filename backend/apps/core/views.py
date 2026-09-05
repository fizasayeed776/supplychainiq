from rest_framework import viewsets, permissions
from django.http import JsonResponse
from .models import Workspace, Vendor, Contract
from .serializers import WorkspaceSerializer, VendorSerializer, ContractSerializer


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
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Order by created_at ascending so the earliest (real) workspace is
        # always [0] in AuthContext — prevents a later "demo" workspace
        # created by scripts/email polling from shadowing the primary tenant.
        return Workspace.objects.filter(members=self.request.user).order_by("created_at")


class VendorViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Vendor.objects.all().order_by("-risk_score")
    serializer_class = VendorSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["workspace"]


class ContractViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Contract.objects.select_related("vendor").all()
    serializer_class = ContractSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["workspace", "vendor", "status"]
