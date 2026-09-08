"""
Workspace-scoped RBAC permission classes.

Role hierarchy (most → least privileged):
  owner     full access including workspace management
  admin     everything except deleting/transferring the workspace
  reviewer  can approve/dispute invoices; read-only elsewhere
  viewer    read-only everywhere

Usage in a viewset:

    from apps.core.permissions import IsAtLeastReviewer, IsAtLeastAdmin

    class MyViewSet(viewsets.ModelViewSet):
        permission_classes = [IsAuthenticated, IsAtLeastAdmin]

For actions that need the workspace derived from the object (e.g. approve
on an ApprovalFlow), use the mixin instead of overriding has_permission.
"""
from rest_framework.permissions import BasePermission, IsAuthenticated  # noqa: F401

from .models import WorkspaceMembership

# Role ordering used for comparisons.
_ROLE_RANK = {"owner": 4, "admin": 3, "reviewer": 2, "viewer": 1}


def _role_rank(role: str) -> int:
    return _ROLE_RANK.get(role, 0)


def _membership_for(user, workspace) -> WorkspaceMembership | None:
    return WorkspaceMembership.objects.filter(workspace=workspace, user=user).first()


def _workspace_from_request(request) -> object | None:
    """Best-effort: extract workspace from query params or request data.
    Used for list/create actions where there is no object yet."""
    workspace_id = (
        request.query_params.get("workspace")
        or request.data.get("workspace")
    )
    if workspace_id:
        from .models import Workspace
        return Workspace.objects.filter(id=workspace_id).first()
    return None


class _MinRolePermission(BasePermission):
    """Base class. Subclasses set `min_role`."""
    min_role: str = "viewer"
    message = "Your workspace role does not permit this action."

    def _check(self, user, workspace) -> bool:
        if workspace is None:
            # Can't determine workspace — allow through and let the viewset
            # handle scoping (the queryset filter already restricts data).
            return True
        m = _membership_for(user, workspace)
        if m is None:
            return False
        return _role_rank(m.role) >= _role_rank(self.min_role)

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # For safe (read) methods viewers are always allowed.
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        workspace = _workspace_from_request(request)
        return self._check(request.user, workspace)

    def has_object_permission(self, request, view, obj):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        workspace = getattr(obj, "workspace", None)
        # If the object IS a Workspace, use it directly.
        if workspace is None:
            from .models import Workspace
            if isinstance(obj, Workspace):
                workspace = obj
        # Traverse one FK level for objects that have workspace on a parent.
        if workspace is None:
            workspace = getattr(getattr(obj, "invoice", None), "workspace", None)
        if workspace is None:
            workspace = getattr(getattr(obj, "match_result", None), "workspace", None)
        return self._check(request.user, workspace)


class IsAtLeastViewer(_MinRolePermission):
    """Any workspace member (viewer+). Effectively: authenticated + member."""
    min_role = "viewer"


class IsAtLeastReviewer(_MinRolePermission):
    """reviewer, admin, or owner — can approve/dispute invoices."""
    min_role = "reviewer"


class IsAtLeastAdmin(_MinRolePermission):
    """admin or owner — can manage workspace settings, webhooks, triage rules."""
    min_role = "admin"


class IsOwner(_MinRolePermission):
    """owner only — full access including workspace deletion/transfer."""
    min_role = "owner"
