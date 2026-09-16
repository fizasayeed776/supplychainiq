"""
Consumer tests for DashboardConsumer and ApprovalRoomConsumer.
ChatConsumer is already covered in tests.py (streaming regression tests).
"""
import asyncio
import uuid
from unittest.mock import patch, AsyncMock, MagicMock

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings

from apps.core.models import Workspace, WorkspaceMembership, Vendor
from apps.realtime.routing import websocket_urlpatterns

User = get_user_model()


def _inject_user(user, router):
    """Thin ASGI middleware that stuffs a user into scope without JWT."""
    async def app(scope, receive, send):
        scope["user"] = user
        await router(scope, receive, send)
    return app


@database_sync_to_async
def _create_user(username):
    return User.objects.create_user(username=username, password="x")


# =============================================================================
# DashboardConsumer
# =============================================================================

@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class DashboardConsumerTests(TransactionTestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="dash_user", password="x")
        self.workspace = Workspace.objects.create(name="Dash WS", slug="dash-ws")
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.user, role="viewer"
        )

    def _app(self, user):
        return _inject_user(user, URLRouter(websocket_urlpatterns))

    async def test_member_can_connect(self):
        app = self._app(self.user)
        url = f"/ws/dashboard/{self.workspace.id}/"
        comm = WebsocketCommunicator(app, url)
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.disconnect()

    async def test_anonymous_user_is_rejected(self):
        from django.contrib.auth.models import AnonymousUser
        app = self._app(AnonymousUser())
        url = f"/ws/dashboard/{self.workspace.id}/"
        comm = WebsocketCommunicator(app, url)
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4403)

    async def test_non_member_is_rejected(self):
        other = await _create_user("dash_other")
        app = self._app(other)
        url = f"/ws/dashboard/{self.workspace.id}/"
        comm = WebsocketCommunicator(app, url)
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4403)

    async def test_pipeline_progress_event_forwarded(self):
        """A pipeline_progress channel-layer message must reach the client."""
        from channels.layers import get_channel_layer

        app = self._app(self.user)
        url = f"/ws/dashboard/{self.workspace.id}/"
        comm = WebsocketCommunicator(app, url)
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        layer = get_channel_layer()
        await layer.group_send(
            f"dashboard_{self.workspace.id}",
            {
                "type": "pipeline_progress",
                "payload": {"stage": "ocr_done", "document": "doc-123"},
            },
        )

        msg = await asyncio.wait_for(comm.receive_json_from(), timeout=2.0)
        self.assertEqual(msg["type"], "pipeline_progress")
        self.assertEqual(msg["payload"]["stage"], "ocr_done")
        await comm.disconnect()


# =============================================================================
# ApprovalRoomConsumer
# =============================================================================

@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class ApprovalRoomConsumerTests(TransactionTestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="apr_user", password="x")
        self.invoice_id = uuid.uuid4()

    def _app(self, user):
        return _inject_user(user, URLRouter(websocket_urlpatterns))

    async def test_authenticated_user_can_connect(self):
        app = self._app(self.user)
        url = f"/ws/approval-room/{self.invoice_id}/"
        comm = WebsocketCommunicator(app, url)
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        # Should receive a presence event for own join
        msg = await asyncio.wait_for(comm.receive_json_from(), timeout=2.0)
        self.assertEqual(msg["type"], "presence")
        self.assertEqual(msg["payload"]["event"], "joined")
        await comm.disconnect()

    async def test_anonymous_user_is_rejected(self):
        from django.contrib.auth.models import AnonymousUser
        app = self._app(AnonymousUser())
        url = f"/ws/approval-room/{self.invoice_id}/"
        comm = WebsocketCommunicator(app, url)
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4403)

    async def test_second_user_sees_first_user_join(self):
        """When a second user connects to the same approval room, the first
        user already in the room receives a 'joined' presence event."""
        app = self._app(self.user)
        url = f"/ws/approval-room/{self.invoice_id}/"

        comm1 = WebsocketCommunicator(app, url)
        await comm1.connect()
        # drain the self-join event
        await asyncio.wait_for(comm1.receive_json_from(), timeout=2.0)

        user2 = await _create_user("apr_user2")
        app2 = self._app(user2)
        comm2 = WebsocketCommunicator(app2, url)
        await comm2.connect()
        # drain user2's own join event
        await asyncio.wait_for(comm2.receive_json_from(), timeout=2.0)

        # comm1 should also receive the joined event for user2
        msg = await asyncio.wait_for(comm1.receive_json_from(), timeout=2.0)
        self.assertEqual(msg["type"], "presence")
        self.assertEqual(msg["payload"]["user"], "apr_user2")
        self.assertEqual(msg["payload"]["event"], "joined")

        await comm1.disconnect()
        await comm2.disconnect()

    async def test_status_change_event_forwarded(self):
        from channels.layers import get_channel_layer

        app = self._app(self.user)
        url = f"/ws/approval-room/{self.invoice_id}/"
        comm = WebsocketCommunicator(app, url)
        await comm.connect()
        await asyncio.wait_for(comm.receive_json_from(), timeout=2.0)  # drain join

        layer = get_channel_layer()
        await layer.group_send(
            f"approval_room_{self.invoice_id}",
            {
                "type": "status_change",
                "payload": {"state": "approved", "invoice_id": str(self.invoice_id)},
            },
        )

        msg = await asyncio.wait_for(comm.receive_json_from(), timeout=2.0)
        self.assertEqual(msg["type"], "status_change")
        self.assertEqual(msg["payload"]["state"], "approved")
        await comm.disconnect()
