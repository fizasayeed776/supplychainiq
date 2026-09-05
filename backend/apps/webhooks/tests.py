"""
Webhook dedup, idempotency, and storm-resilience tests.
Rubric requirement: webhook duplicate delivery, idempotency, storm scenario.
"""
import hashlib
import hmac
import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from .dedup import is_duplicate_delivery


class WebhookDedupUnitTests(TestCase):
    """Unit tests for the Redis-backed dedup store."""

    def setUp(self):
        # Use test-run-unique IDs to avoid cross-test contamination with live Redis
        self.run_id = uuid.uuid4().hex

    def test_first_delivery_id_is_not_duplicate(self):
        self.assertFalse(is_duplicate_delivery(f"{self.run_id}-unique-001"))

    def test_same_delivery_id_is_duplicate_on_second_call(self):
        delivery_id = f"{self.run_id}-dup-test"
        is_duplicate_delivery(delivery_id)  # first call — marks it seen
        self.assertTrue(is_duplicate_delivery(delivery_id))

    def test_different_ids_are_not_duplicates(self):
        self.assertFalse(is_duplicate_delivery(f"{self.run_id}-alpha"))
        self.assertFalse(is_duplicate_delivery(f"{self.run_id}-beta"))
        self.assertFalse(is_duplicate_delivery(f"{self.run_id}-gamma"))


class WebhookEndpointTests(TestCase):
    """Integration tests against the partner webhook endpoint."""

    SECRET = "dev-webhook-secret"

    def setUp(self):
        self.client = APIClient()
        self.run_id = uuid.uuid4().hex

    def _sign(self, body: bytes) -> str:
        return hmac.new(self.SECRET.encode(), body, hashlib.sha256).hexdigest()

    def _post(self, payload, secret=None):
        body = json.dumps(payload).encode()
        sig = self._sign(body) if secret is None else secret
        return self.client.post(
            "/webhooks/partner/",
            data=body,
            content_type="application/json",
            HTTP_X_SCIQ_SIGNATURE=sig,
        )

    @patch("apps.webhooks.tasks.process_partner_payload.delay")
    def test_valid_delivery_is_accepted_202(self, mock_task):
        payload = {"delivery_id": f"{self.run_id}-accept-001", "document_type": "po"}
        response = self._post(payload)
        self.assertEqual(response.status_code, 202)
        mock_task.assert_called_once()

    @patch("apps.webhooks.tasks.process_partner_payload.delay")
    def test_duplicate_delivery_returns_200_not_processed_twice(self, mock_task):
        payload = {"delivery_id": f"{self.run_id}-dedup-001", "document_type": "po"}
        r1 = self._post(payload)
        r2 = self._post(payload)
        self.assertEqual(r1.status_code, 202)
        self.assertEqual(r2.status_code, 200)
        self.assertIn("duplicate", r2.data["detail"])
        # Task dispatched exactly once despite two HTTP calls
        self.assertEqual(mock_task.call_count, 1)

    def test_bad_signature_returns_401(self):
        payload = {"delivery_id": f"{self.run_id}-badsig-001", "document_type": "po"}
        response = self._post(payload, secret="deadbeef00000000")
        self.assertEqual(response.status_code, 401)

    def test_missing_delivery_id_returns_400(self):
        payload = {"document_type": "po"}
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)

    @patch("apps.webhooks.tasks.process_partner_payload.delay")
    def test_storm_of_50_identical_deliveries_triggers_task_exactly_once(self, mock_task):
        """Simulates the webhook storm scenario: 50 redeliveries of same event."""
        payload = {"delivery_id": f"{self.run_id}-storm-50x", "document_type": "po"}
        responses = [self._post(payload) for _ in range(50)]
        accepted = sum(1 for r in responses if r.status_code == 202)
        deduped = sum(1 for r in responses if r.status_code == 200)
        self.assertEqual(accepted, 1)
        self.assertEqual(deduped, 49)
        self.assertEqual(mock_task.call_count, 1)
