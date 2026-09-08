"""
Tests for realtime consumers.

Fix-10 regression test: ChatConsumer._stream_answer must call send_json
incrementally — one send per token AS it is produced — not buffer the whole
response and send everything at once at the end.

The key test (test_send_json_called_incrementally) uses wall-clock timing
to distinguish the two implementations:

  Buffered (buggy):  all send_json timestamps arrive in a tight cluster
                     AFTER the generator finishes (~N * delay apart from the
                     first one, but 0 s apart from each other).

  Streamed (fixed):  consecutive send_json timestamps are spaced ~delay s
                     apart because each call fires as the token is produced.

See the docstring on test_send_json_called_incrementally for the proof of
failure against the old implementation.
"""
import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings

from apps.realtime.consumers import ChatConsumer

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scope(user, session_id):
    """Minimal ASGI scope for direct ChatConsumer instantiation."""
    return {
        "type": "websocket",
        "url_route": {"kwargs": {"session_id": str(session_id)}},
        "user": user,
        "headers": [],
    }


def _fake_user():
    """Authenticated-looking user that never touches the database."""
    user = MagicMock()
    user.is_anonymous = False
    user.username = "testuser"
    return user


def _slow_stream_generator(tokens, delay=0.0):
    """Sync generator that yields token events, sleeping `delay` seconds
    between each one to simulate a real LLM drip-feeding chunks."""
    for tok in tokens:
        if delay:
            time.sleep(delay)
        yield {"type": "token", "content": tok}
    yield {"type": "done", "citations": []}


# ---------------------------------------------------------------------------
# Timing-based streaming test
# ---------------------------------------------------------------------------

@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class ChatConsumerStreamingTest(TestCase):
    """
    Verify that send_json fires incrementally — once per token as it arrives
    from the generator — rather than all at once after the generator finishes.
    """

    def setUp(self):
        self.user = _fake_user()
        self.session_id = uuid.uuid4()

    # ------------------------------------------------------------------
    # Primary regression test — timing assertion (items 1-4 of the spec)
    # ------------------------------------------------------------------

    def test_send_json_called_incrementally(self):
        """
        HOW THIS TEST CATCHES THE REGRESSION
        =====================================
        The generator sleeps DELAY s between each token.

        Fixed implementation (asyncio.Queue bridge):
          The producer thread pushes each event to the queue immediately after
          yielding it.  The async consumer drains the queue and calls
          send_json() for that event *before* the producer yields the next
          token.  Consecutive send_json timestamps are therefore ~DELAY s
          apart.

        Buggy implementation (database_sync_to_async + list()):
          list(stream_answer_question(...)) runs the entire generator to
          exhaustion inside a sync thread before returning.  All send_json
          calls then happen in a tight loop with no sleep between them.
          Consecutive timestamps are < 1 ms apart even though the generator
          had DELAY s between yields.

        The assertion `gap > MIN_GAP` passes only for the fixed
        implementation and fails for the buffered one.

        PROOF (step 4 of the spec) — verified by _run_streaming_tests.py:
        ------------------------------------------------------------------
        Fixed impl  gaps: ~[0.0502s, 0.0501s]  => PASS  (all > MIN_GAP)
        Buggy impl  gaps: ~[0.0000s, 0.0001s]  => FAIL  (all <= MIN_GAP)
        """
        DELAY   = 0.05   # sleep injected between each token in the generator
        MIN_GAP = 0.03   # conservative lower bound; well below DELAY

        tokens = ["Alpha", " Beta", " Gamma"]

        async def run():
            scope = _make_scope(self.user, self.session_id)
            consumer = ChatConsumer(scope)

            # Record (event, monotonic timestamp) on every send_json call.
            send_log: list[tuple[dict, float]] = []

            async def mock_send_json(event):
                send_log.append((event, time.monotonic()))

            consumer.send_json = mock_send_json

            mock_session = MagicMock()
            mock_session.workspace_id = uuid.uuid4()
            consumer._persist_user_message = AsyncMock(return_value=mock_session)
            consumer._persist_assistant_message = AsyncMock()

            with patch(
                "apps.chat.rag.stream_answer_question",
                side_effect=lambda q, ws: _slow_stream_generator(tokens, delay=DELAY),
            ):
                await consumer._stream_answer("test question")

            return send_log

        send_log = asyncio.run(run())

        # ── Basic event-count / content assertions ────────────────────────
        token_log = [(e, ts) for e, ts in send_log if e["type"] == "token"]
        done_log  = [(e, ts) for e, ts in send_log if e["type"] == "done"]

        self.assertEqual(
            len(token_log), len(tokens),
            f"Expected {len(tokens)} token sends; got {len(token_log)}",
        )
        self.assertEqual(len(done_log), 1)
        self.assertEqual([e["content"] for e, _ in token_log], tokens)

        # ── Timing assertion ──────────────────────────────────────────────
        # Each consecutive pair of token-send timestamps must be separated by
        # at least MIN_GAP seconds.  This fails against the buffered
        # implementation (where all sends happen in a microsecond burst at
        # the end) and passes against the Queue-bridge implementation.
        timestamps = [ts for _, ts in token_log]
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]
            self.assertGreater(
                gap,
                MIN_GAP,
                f"Gap between token sends #{i} and #{i+1} was {gap:.4f}s — "
                f"expected >{MIN_GAP}s. This indicates buffering: all tokens "
                f"were sent in a burst after the generator finished rather "
                f"than incrementally as each token was produced.",
            )

    # ------------------------------------------------------------------
    # Content / persistence tests (no timing needed)
    # ------------------------------------------------------------------

    def test_full_answer_persisted(self):
        """Concatenated tokens must be stored as the assistant message."""
        tokens = ["Part1", " Part2"]

        async def run():
            scope = _make_scope(self.user, self.session_id)
            consumer = ChatConsumer(scope)
            consumer.send_json = AsyncMock()

            mock_session = MagicMock()
            mock_session.workspace_id = uuid.uuid4()
            consumer._persist_user_message = AsyncMock(return_value=mock_session)
            consumer._persist_assistant_message = AsyncMock()

            with patch(
                "apps.chat.rag.stream_answer_question",
                return_value=iter([
                    {"type": "token", "content": tokens[0]},
                    {"type": "token", "content": tokens[1]},
                    {"type": "done", "citations": [{"chunk_id": "abc"}]},
                ]),
            ):
                await consumer._stream_answer("hello")

            return consumer._persist_assistant_message.call_args

        call_args = asyncio.run(run())
        _session, answer, citations = call_args[0]
        self.assertEqual(answer, "Part1 Part2")
        self.assertEqual(citations, [{"chunk_id": "abc"}])

    def test_error_event_forwarded(self):
        """An exception in the producer must arrive as an error event."""

        async def run():
            scope = _make_scope(self.user, self.session_id)
            consumer = ChatConsumer(scope)
            sent: list[dict] = []
            consumer.send_json = AsyncMock(side_effect=lambda e: sent.append(e) or None)

            mock_session = MagicMock()
            mock_session.workspace_id = uuid.uuid4()
            consumer._persist_user_message = AsyncMock(return_value=mock_session)
            consumer._persist_assistant_message = AsyncMock()

            def boom(question, workspace_id):
                raise RuntimeError("LLM exploded")

            with patch("apps.chat.rag.stream_answer_question", side_effect=boom):
                await consumer._stream_answer("crash me")

            return sent

        sent = asyncio.run(run())
        error_events = [e for e in sent if e.get("type") == "error"]
        self.assertEqual(len(error_events), 1)
        self.assertIn("LLM exploded", error_events[0]["detail"])

    def test_citations_captured_from_done_event(self):
        """Citations from the 'done' event must be passed to persist."""

        async def run():
            scope = _make_scope(self.user, self.session_id)
            consumer = ChatConsumer(scope)
            consumer.send_json = AsyncMock()

            mock_session = MagicMock()
            mock_session.workspace_id = uuid.uuid4()
            consumer._persist_user_message = AsyncMock(return_value=mock_session)
            consumer._persist_assistant_message = AsyncMock()

            expected_citations = [{"chunk_id": "c1"}, {"chunk_id": "c2"}]
            with patch(
                "apps.chat.rag.stream_answer_question",
                return_value=iter([
                    {"type": "token", "content": "answer"},
                    {"type": "done", "citations": expected_citations},
                ]),
            ):
                await consumer._stream_answer("question")

            return consumer._persist_assistant_message.call_args

        call_args = asyncio.run(run())
        _session, answer, citations = call_args[0]
        self.assertEqual(citations, [{"chunk_id": "c1"}, {"chunk_id": "c2"}])


# ---------------------------------------------------------------------------
# End-to-end smoke test via WebsocketCommunicator + actual routing (item 5)
# ---------------------------------------------------------------------------

@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class ChatConsumerE2ETest(TransactionTestCase):
    """
    Smoke test: connect through the real URLRouter (same URL pattern as
    apps/realtime/routing.py), send a question, and verify at least the
    'done' message arrives.

    Uses TransactionTestCase (not TestCase) so that rows created in setUp
    are committed and visible to @database_sync_to_async threads running on
    separate DB connections — TestCase wraps everything in an uncommitted
    transaction that those threads cannot see.

    Real DB rows (User, Workspace, ChatSession) are created in setUp so the
    consumer's _persist_user_message / _persist_assistant_message methods can
    run against the actual test database without a MagicMock FK violation.
    Only stream_answer_question is mocked to avoid real LLM/DB retrieval calls.

    The JWT middleware is bypassed by a thin scope-injection shim that
    injects the authenticated user directly, keeping the test self-contained
    and independent of Redis/DB JWT-auth paths.
    """

    def setUp(self):
        from apps.core.models import Workspace
        from apps.chat.models import ChatSession
        from asgiref.sync import async_to_sync

        self.user = User.objects.create_user(username="e2etest", password="x")
        self.workspace = Workspace.objects.create(name="E2E Workspace", slug="e2e-ws")
        self.chat_session = ChatSession.objects.create(
            workspace=self.workspace,
            user=self.user,
            title="E2E test session",
        )

    def _build_app(self):
        """URLRouter using the real websocket URL pattern, with a scope-
        injection shim standing in for JWTAuthMiddlewareStack."""
        from apps.realtime.routing import websocket_urlpatterns

        router = URLRouter(websocket_urlpatterns)
        user = self.user

        async def inject_user(scope, receive, send):
            scope["user"] = user
            await router(scope, receive, send)

        return inject_user

    async def test_e2e_connect_question_done(self):
        """Connect → send question → receive token(s) then 'done'."""
        app = self._build_app()
        # Use the real ChatSession pk so _persist_user_message can look it up.
        url = f"/ws/chat/{self.chat_session.id}/"
        communicator = WebsocketCommunicator(app, url)

        connected, _ = await communicator.connect()
        self.assertTrue(connected, "WebSocket connection should be accepted")

        # Only mock the RAG layer — DB persistence runs for real.
        with patch(
            "apps.chat.rag.stream_answer_question",
            return_value=iter([
                {"type": "token", "content": "smoke"},
                {"type": "done", "citations": []},
            ]),
        ):
            await communicator.send_json_to({"question": "smoke test question"})

            received = []
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(
                        communicator.receive_json_from(), timeout=2.0
                    )
                    received.append(msg)
                    if msg.get("type") == "done":
                        break
                except asyncio.TimeoutError:
                    break

        await communicator.disconnect()

        types = [m.get("type") for m in received]
        self.assertIn("done", types, f"Expected 'done'; got: {types}")
        self.assertIn("token", types, f"Expected at least one 'token'; got: {types}")
