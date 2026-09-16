"""
Tests for workflow/outbound.py — post_signed_webhook.
"""
import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from apps.core.models import Workspace, Vendor
from apps.workflow.models import WebhookDelivery


@override_settings(PARTNER_WEBHOOK_SECRET="test-outbound-secret")
class PostSignedWebhookTests(TestCase):

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Outbound WS", slug="outbound-ws",
            webhook_secret="workspace-level-secret",
        )

    def _expected_sig(self, secret, payload):
        body = json.dumps(payload).encode()
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    @patch("apps.workflow.outbound.requests.post")
    def test_successful_post_returns_true(self, mock_post):
        mock_post.return_value.status_code = 200

        from apps.workflow.outbound import post_signed_webhook
        result = post_signed_webhook(self.workspace, "https://example.com/hook", {"event": "test"})

        self.assertTrue(result)
        mock_post.assert_called_once()

    @patch("apps.workflow.outbound.requests.post")
    def test_creates_webhook_delivery_on_success(self, mock_post):
        mock_post.return_value.status_code = 200

        from apps.workflow.outbound import post_signed_webhook
        post_signed_webhook(self.workspace, "https://example.com/hook", {"event": "test"})

        delivery = WebhookDelivery.objects.get(workspace=self.workspace)
        self.assertTrue(delivery.success)
        self.assertEqual(delivery.status_code, 200)
        self.assertEqual(delivery.attempt, 1)

    @patch("apps.workflow.outbound.requests.post")
    def test_hmac_signature_uses_workspace_secret(self, mock_post):
        """The X-SCIQ-Signature header must be HMAC-SHA256 of the body using
        workspace.webhook_secret. This is the regression test for Step 5."""
        mock_post.return_value.status_code = 200
        payload = {"event": "critical_discrepancy", "invoice": "INV-1"}

        from apps.workflow.outbound import post_signed_webhook
        post_signed_webhook(self.workspace, "https://example.com/hook", payload)

        call_kwargs = mock_post.call_args
        sent_headers = call_kwargs[1]["headers"] if "headers" in call_kwargs[1] else call_kwargs[0][2]
        # headers passed as kwarg
        headers = mock_post.call_args.kwargs.get("headers") or mock_post.call_args[1].get("headers")
        body = json.dumps(payload).encode()
        expected_sig = hmac.new("workspace-level-secret".encode(), body, hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-SCIQ-Signature"], expected_sig)

    @patch("apps.workflow.outbound.requests.post")
    def test_falls_back_to_settings_secret_when_workspace_secret_empty(self, mock_post):
        self.workspace.webhook_secret = ""
        self.workspace.save()
        mock_post.return_value.status_code = 200
        payload = {"event": "test"}

        from apps.workflow.outbound import post_signed_webhook
        post_signed_webhook(self.workspace, "https://example.com/hook", payload)

        headers = mock_post.call_args.kwargs.get("headers") or mock_post.call_args[1].get("headers")
        body = json.dumps(payload).encode()
        expected_sig = hmac.new("test-outbound-secret".encode(), body, hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-SCIQ-Signature"], expected_sig)

    @patch("apps.workflow.outbound.requests.post")
    def test_all_attempts_exhausted_returns_false(self, mock_post):
        """All three attempts fail → post_signed_webhook returns False and
        creates a WebhookDelivery row for every attempt."""
        import requests as req_lib
        mock_post.side_effect = req_lib.RequestException("Connection refused")

        from apps.workflow.outbound import post_signed_webhook
        result = post_signed_webhook(
            self.workspace, "https://dead.example.com/hook",
            {"event": "test"}, max_attempts=3,
        )

        self.assertFalse(result)
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(
            WebhookDelivery.objects.filter(workspace=self.workspace, success=False).count(), 3
        )

    @patch("apps.workflow.outbound.requests.post")
    def test_stops_after_first_success(self, mock_post):
        """First attempt succeeds → no further attempts made."""
        mock_post.return_value.status_code = 202

        from apps.workflow.outbound import post_signed_webhook
        result = post_signed_webhook(
            self.workspace, "https://example.com/hook",
            {"event": "ok"}, max_attempts=3,
        )

        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 1)

    @patch("apps.workflow.outbound.requests.post")
    def test_4xx_response_does_not_retry(self, mock_post):
        """A 4xx status is treated as a failure but does not raise —
        the loop continues (and creates a delivery row with success=False)."""
        mock_post.return_value.status_code = 404

        from apps.workflow.outbound import post_signed_webhook
        result = post_signed_webhook(
            self.workspace, "https://example.com/hook",
            {"event": "bad"}, max_attempts=2,
        )

        self.assertFalse(result)
        self.assertEqual(mock_post.call_count, 2)
        deliveries = WebhookDelivery.objects.filter(workspace=self.workspace)
        self.assertEqual(deliveries.count(), 2)
        self.assertTrue(all(not d.success for d in deliveries))
