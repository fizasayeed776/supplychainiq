"""
Public self-service registration.

POST /api/auth/register/
{
    "email":          "alice@acme.com",
    "password":       "…",
    "full_name":      "Alice Nguyen",
    "workspace_name": "Acme Procurement"   # optional — defaults to "<Name>'s Workspace"
}

On success:
  - Creates a Django User (username = email, email = email, first/last name split from full_name)
  - Slugifies workspace_name → Workspace.slug (appends a short uid suffix on collision)
  - Creates WorkspaceMembership(role="owner")
  - Returns JWT access + refresh tokens so the browser is immediately logged in

Each signup is a brand-new isolated tenant.  There is no "join existing workspace"
flow here — that would require an invite token system that is out of scope.
"""
import re
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.text import slugify
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Workspace, WorkspaceMembership

User = get_user_model()


# ── Input serializer ──────────────────────────────────────────────────────────

class RegistrationSerializer(serializers.Serializer):
    email          = serializers.EmailField(max_length=254)
    password       = serializers.CharField(write_only=True, min_length=8)
    full_name      = serializers.CharField(max_length=150)
    workspace_name = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_email(self, value):
        normalised = value.strip().lower()
        if User.objects.filter(email__iexact=normalised).exists():
            raise serializers.ValidationError("This email is already registered.")
        return normalised

    def validate_password(self, value):
        # Run Django's AUTH_PASSWORD_VALIDATORS (configured in settings)
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate_full_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Full name is required.")
        return name


# ── Slug helper ───────────────────────────────────────────────────────────────

def _unique_slug(base: str) -> str:
    """Slugify base; append a 6-char uid suffix until the slug is unique."""
    slug = slugify(base)[:48] or "workspace"
    if not Workspace.objects.filter(slug=slug).exists():
        return slug
    for _ in range(10):
        candidate = f"{slug}-{uuid.uuid4().hex[:6]}"
        if not Workspace.objects.filter(slug=candidate).exists():
            return candidate
    # Absolute fallback — practically unreachable
    return f"ws-{uuid.uuid4().hex[:12]}"


# ── View ──────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """
    Public registration endpoint.  No authentication required.
    Returns {access, refresh, user: {id, email, full_name}, workspace: {id, name, slug}}.
    """
    serializer = RegistrationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    email      = data["email"]
    password   = data["password"]
    full_name  = data["full_name"]
    ws_name    = (data.get("workspace_name") or "").strip() or f"{full_name.split()[0]}'s Workspace"

    # Split full_name into first / last
    parts      = full_name.split(maxsplit=1)
    first_name = parts[0]
    last_name  = parts[1] if len(parts) > 1 else ""

    # Create user  (username = email — simplejwt's default auth field is username,
    # so we store email as username too so /api/auth/token/ still works with email)
    user = User.objects.create_user(
        username   = email,
        email      = email,
        password   = password,
        first_name = first_name,
        last_name  = last_name,
    )

    # Create workspace + membership
    slug      = _unique_slug(ws_name)
    workspace = Workspace.objects.create(name=ws_name, slug=slug)
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role="owner")

    # Issue JWT tokens
    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "access":  str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id":        user.id,
                "email":     user.email,
                "full_name": full_name,
            },
            "workspace": {
                "id":   str(workspace.id),
                "name": workspace.name,
                "slug": workspace.slug,
            },
        },
        status=status.HTTP_201_CREATED,
    )
