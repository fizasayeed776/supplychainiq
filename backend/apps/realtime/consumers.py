import json

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    """Per-workspace group: pipeline progress, match results, new
    discrepancies, and SLA countdown updates — powers the live dashboard
    feed without the client ever polling."""

    async def connect(self):
        self.workspace_id = self.scope["url_route"]["kwargs"]["workspace_id"]
        self.group_name = f"dashboard_{self.workspace_id}"

        if self.scope["user"].is_anonymous or not await self._is_member():
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def _is_member(self):
        from apps.core.models import Workspace
        return Workspace.objects.filter(id=self.workspace_id, members=self.scope["user"]).exists()

    async def pipeline_progress(self, event):
        await self.send_json({"type": "pipeline_progress", "payload": event["payload"]})


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """Streams RAG responses token by token to the Chat page."""

    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        if self.scope["user"].is_anonymous:
            await self.close(code=4403)
            return
        await self.accept()

    async def receive_json(self, content, **kwargs):
        question = content.get("question", "")
        if not question:
            return
        await self._stream_answer(question)

    @database_sync_to_async
    def _persist_and_get_stream(self, question):
        from apps.chat.models import ChatSession, ChatMessage
        from apps.chat.rag import answer_question

        session = ChatSession.objects.get(id=self.session_id)
        ChatMessage.objects.create(session=session, role="user", content=question)
        result = answer_question(question, session.workspace_id)
        ChatMessage.objects.create(
            session=session, role="assistant", content=result["answer"], citations=result["citations"]
        )
        return result

    async def _stream_answer(self, question):
        result = await self._persist_and_get_stream(question)
        # Token-chunked emission so the UI can render a typing effect even
        # though the underlying LLM call above is non-streaming in this stub.
        words = result["answer"].split(" ")
        buffer = []
        for word in words:
            buffer.append(word)
            await self.send_json({"type": "token", "content": word + " "})
        await self.send_json({"type": "done", "citations": result["citations"]})


class ApprovalRoomConsumer(AsyncJsonWebsocketConsumer):
    """Presence (who is reviewing an invoice) + live status changes."""

    async def connect(self):
        self.invoice_id = self.scope["url_route"]["kwargs"]["invoice_id"]
        self.group_name = f"approval_room_{self.invoice_id}"
        if self.scope["user"].is_anonymous:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(self.group_name, {
            "type": "presence_update",
            "payload": {"user": self.scope["user"].username, "event": "joined"},
        })

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_send(self.group_name, {
                "type": "presence_update",
                "payload": {"user": self.scope["user"].username, "event": "left"},
            })
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def presence_update(self, event):
        await self.send_json({"type": "presence", "payload": event["payload"]})

    async def status_change(self, event):
        await self.send_json({"type": "status_change", "payload": event["payload"]})
