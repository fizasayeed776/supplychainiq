"""Exercise the live Channels consumers with JWT and Redis channel groups."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from asgiref.sync import sync_to_async
from rest_framework_simplejwt.tokens import RefreshToken

from apps.chat.models import ChatSession
from apps.core.models import Workspace
from apps.documents.models import Invoice
from apps.workflow.models import ApprovalFlow, ApprovalStep
from config.asgi import application
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


async def main():
    workspace, invoice, session, token, approval_id = await _load_fixture()

    invalid = WebsocketCommunicator(application, f"/ws/dashboard/{workspace.id}/?token=invalid")
    invalid_connected, _ = await invalid.connect()
    print("invalid_jwt_connected", invalid_connected)
    await invalid.disconnect()

    missing = WebsocketCommunicator(application, f"/ws/dashboard/{workspace.id}/")
    missing_connected, _ = await missing.connect()
    print("missing_jwt_connected", missing_connected)
    await missing.disconnect()

    dashboard = WebsocketCommunicator(application, f"/ws/dashboard/{workspace.id}/?token={token}")
    dashboard_connected, _ = await dashboard.connect()
    await get_channel_layer().group_send(
        f"dashboard_{workspace.id}",
        {"type": "pipeline.progress", "payload": {"stage": "audit_event", "document": "audit"}},
    )
    dashboard_event = await dashboard.receive_json_from(timeout=5)
    print("dashboard_connected", dashboard_connected, "dashboard_event", dashboard_event)
    await dashboard.disconnect()

    approval = WebsocketCommunicator(application, f"/ws/approval-room/{invoice.id}/?token={token}")
    approval_connected, _ = await approval.connect()
    presence_event = await approval.receive_json_from(timeout=5)
    response = await _decide(approval_id)
    status_event = await approval.receive_json_from(timeout=5)
    print("approval_connected", approval_connected, "presence_event", presence_event, "decision_status", response.status_code, "status_event", status_event)
    await approval.disconnect()

    chat = WebsocketCommunicator(application, f"/ws/chat/{session.id}/?token={token}")
    chat_connected, _ = await chat.connect()
    await chat.send_json_to({"question": "what is the total on invoice INV-4001"})
    frames = []
    while True:
        frame = await chat.receive_json_from(timeout=30)
        frames.append(frame)
        if frame.get("type") == "done":
            break
    print("chat_connected", chat_connected, "token_frame_count", sum(frame.get("type") == "token" for frame in frames), "done", frames[-1])
    await chat.disconnect()


@sync_to_async
def _load_fixture():
    user = get_user_model().objects.get(username="fiza")
    invoice = Invoice.objects.filter(workspace__members=user, approval_flow__isnull=True).first()
    workspace = invoice.workspace
    session = ChatSession.objects.create(workspace=workspace, user=user, title="Realtime audit")
    token = str(RefreshToken.for_user(user).access_token)
    flow, _ = ApprovalFlow.objects.get_or_create(workspace=workspace, invoice=invoice)
    if flow.state == "draft":
        flow.submit_for_review()
        flow.save()
    ApprovalStep.objects.filter(flow=flow).delete()
    ApprovalStep.objects.create(flow=flow, order=1)
    return workspace, invoice, session, token, flow.id


@sync_to_async
def _decide(approval_id):
    user = get_user_model().objects.get(username="fiza")
    client = APIClient()
    client.force_authenticate(user)
    return client.post(f"/api/workflow/approvals/{approval_id}/decide/", {"decision": "approved"}, format="json")


if __name__ == "__main__":
    asyncio.run(main())
