"""
Outbound webhook delivery with HMAC signing and retry, plus a delivery log
so failed Teams/generic-webhook posts can be debugged from the Settings page.
"""
import hashlib
import hmac
import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post_signed_webhook(workspace, url: str, payload: dict, max_attempts: int = 3) -> bool:
    from .models import WebhookDelivery

    body = json.dumps(payload).encode()
    secret = workspace.webhook_secret or settings.PARTNER_WEBHOOK_SECRET
    headers = {"Content-Type": "application/json", "X-SCIQ-Signature": _sign(secret, body)}

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(url, data=body, headers=headers, timeout=10)
            success = response.status_code < 300
            WebhookDelivery.objects.create(
                workspace=workspace, url=url, payload=payload,
                status_code=response.status_code, attempt=attempt, success=success,
            )
            if success:
                return True
        except requests.RequestException as exc:
            WebhookDelivery.objects.create(
                workspace=workspace, url=url, payload=payload,
                attempt=attempt, success=False, error=str(exc),
            )
            logger.warning("Outbound webhook attempt %s to %s failed: %s", attempt, url, exc)
    return False
