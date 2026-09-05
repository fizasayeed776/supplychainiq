"""
Inbound partner webhook: receives EDI-style JSON (simulated supplier system
pushing POs and shipment notices). HMAC-verified, deduplicated, and
enqueue-and-return so the HTTP response stays sub-second even under a
webhook storm — all real processing happens in Celery.
"""
import hashlib
import hmac
import json

from django.conf import settings
from django.core.files.base import ContentFile
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .dedup import is_duplicate_delivery


def _verify_signature(secret: str, body: bytes, signature: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@api_view(["POST"])
@permission_classes([AllowAny])
def partner_webhook(request):
    signature = request.headers.get("X-SCIQ-Signature", "")
    body = request.body
    if not _verify_signature(settings.PARTNER_WEBHOOK_SECRET, body, signature):
        return Response({"detail": "invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

    payload = json.loads(body)
    delivery_id = payload.get("delivery_id") or request.headers.get("X-Delivery-Id")
    if not delivery_id:
        return Response({"detail": "delivery_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    if is_duplicate_delivery(delivery_id):
        return Response({"detail": "duplicate, already processed"}, status=status.HTTP_200_OK)

    from .tasks import process_partner_payload
    process_partner_payload.delay(payload)
    return Response({"detail": "accepted"}, status=status.HTTP_202_ACCEPTED)
