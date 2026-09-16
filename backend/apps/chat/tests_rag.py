"""
Additional tests for apps/chat/rag.py — chunk_text and guardrail behaviour.
The aggregate-tool tests already live in tests.py; this file covers the
retrieval/generation paths without real LLM or pgvector calls.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.chat.rag import chunk_text


# =============================================================================
# chunk_text
# =============================================================================

class ChunkTextTests(TestCase):

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(chunk_text(""), [])

    def test_single_chunk_when_text_fits(self):
        text = " ".join(f"word{i}" for i in range(10))
        chunks = chunk_text(text, max_tokens=50, overlap_tokens=5)
        self.assertEqual(len(chunks), 1)
        self.assertIn("word0", chunks[0])

    def test_multiple_chunks_created(self):
        # 200 words, max_tokens=50, overlap=10 → step=40 → ceil(200/40)=5 chunks
        text = " ".join(f"word{i}" for i in range(200))
        chunks = chunk_text(text, max_tokens=50, overlap_tokens=10)
        self.assertGreater(len(chunks), 1)

    def test_overlap_means_last_words_of_chunk_appear_in_next(self):
        text = " ".join(str(i) for i in range(100))
        chunks = chunk_text(text, max_tokens=20, overlap_tokens=5)
        # The last 5 words of chunk[0] should appear at the start of chunk[1]
        last_words_of_first = chunks[0].split()[-5:]
        first_words_of_second = chunks[1].split()[:5]
        self.assertEqual(last_words_of_first, first_words_of_second)

    def test_single_word_text(self):
        chunks = chunk_text("hello", max_tokens=500, overlap_tokens=50)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], "hello")

    def test_whitespace_only_text_returns_empty(self):
        self.assertEqual(chunk_text("   \n\t  "), [])


# =============================================================================
# answer_question — guardrail (no matching chunks + no aggregate → not-found)
# =============================================================================

class AnswerQuestionGuardrailTests(TestCase):
    """When hybrid_retrieve returns empty and there is no aggregate result,
    answer_question must return the 'I couldn't find' message — not hallucinate."""

    @patch("apps.chat.rag.maybe_run_aggregate_tool", return_value=None)
    @patch("apps.chat.rag.hybrid_retrieve", return_value=([], {}))
    def test_empty_retrieval_returns_not_found(self, _retrieve, _aggregate):
        from apps.chat.rag import answer_question
        result = answer_question("What is the payment term for vendor X?", "workspace-123")

        self.assertIn("couldn't find", result["answer"].lower())
        self.assertEqual(result["citations"], [])

    @patch("apps.chat.rag.maybe_run_aggregate_tool", return_value=None)
    @patch("apps.chat.rag.hybrid_retrieve", return_value=([], {}))
    def test_specific_doc_id_not_in_chunks_returns_not_found(self, _retrieve, _aggregate):
        """Requesting a specific invoice number that isn't in any chunk must
        return the guardrail message even if chunks were retrieved."""
        from apps.chat.rag import answer_question
        result = answer_question("Show me invoice INV-9999", "workspace-123")
        self.assertIn("couldn't find", result["answer"].lower())


# =============================================================================
# stream_answer_question — not-found path
# =============================================================================

class StreamAnswerNotFoundTests(TestCase):

    @patch("apps.chat.rag.maybe_run_aggregate_tool", return_value=None)
    @patch("apps.chat.rag.hybrid_retrieve", return_value=([], {}))
    def test_stream_yields_not_found_then_done(self, _retrieve, _aggregate):
        from apps.chat.rag import stream_answer_question
        events = list(stream_answer_question("unknown question", "ws-id"))

        types = [e["type"] for e in events]
        self.assertIn("token", types)
        self.assertIn("done", types)
        token_content = " ".join(e["content"] for e in events if e["type"] == "token")
        self.assertIn("couldn't find", token_content.lower())
