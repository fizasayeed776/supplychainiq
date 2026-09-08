import asyncio
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

    async def sla_deadline_update(self, event):
        """Pushed whenever an ApprovalStep's escalation_deadline is set or
        changes (new step created, step escalated).  The payload contains
        enough info for the Dashboard to refresh its SLA countdown panel."""
        await self.send_json({"type": "sla_deadline_update", "payload": event["payload"]})


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
    def _persist_user_message(self, question):
        from apps.chat.models import ChatSession, ChatMessage

        session = ChatSession.objects.get(id=self.session_id)
        ChatMessage.objects.create(session=session, role="user", content=question)
        return session

    @database_sync_to_async
    def _persist_assistant_message(self, session, answer, citations):
        from apps.chat.models import ChatMessage

        ChatMessage.objects.create(
            session=session, role="assistant", content=answer, citations=citations
        )

    async def _stream_answer(self, question):
        """True streaming: a sync producer thread runs stream_answer_question
        and pushes each event onto an asyncio.Queue as it arrives; this async
        method drains the queue and forwards events to the WebSocket immediately
        — no buffering of the full response before sending begins."""
        session = await self._persist_user_message(question)

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def producer():
            from apps.chat.rag import stream_answer_question
            from django.db import close_old_connections

            try:
                for event in stream_answer_question(question, session.workspace_id):
                    asyncio.run_coroutine_threadsafe(queue.put(event), loop).result()
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "error", "detail": str(exc)}), loop
                ).result()
            finally:
                # Release Django DB connections borrowed by the thread so they
                # are not leaked back into the thread pool.
                close_old_connections()
                asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

        # Run the sync generator concurrently in the default thread-pool executor.
        # We do NOT await this — the queue draining loop below runs while it produces.
        loop.run_in_executor(None, producer)

        full_tokens: list[str] = []
        citations: list = []
        while True:
            event = await queue.get()
            if event is None:
                break
            await self.send_json(event)
            if event["type"] == "token":
                full_tokens.append(event["content"])
            elif event["type"] == "done":
                citations = event.get("citations", [])

        await self._persist_assistant_message(session, "".join(full_tokens), citations)


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
