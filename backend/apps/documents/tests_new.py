"""
Additional document tests — OCR module coverage.
Kept in a separate file so the original tests.py stays unchanged.
"""
import hashlib
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.core.models import Vendor, Workspace
from apps.documents.models import Document


class OCRPdfTests(TestCase):
    """ocr.ocr_pdf — normal path and per-page confidence averaging."""

    def _fake_page(self, words, confs):
        """Return a dict that pytesseract.image_to_data would return."""
        return {"text": words, "conf": confs}

    @patch("apps.documents.ocr.convert_from_path")
    @patch("apps.documents.ocr.pytesseract.image_to_data")
    def test_single_page_returns_text_and_confidence(self, mock_itd, mock_cfp):
        """Single page with high-confidence words → correct text + avg confidence."""
        fake_page = MagicMock()
        mock_cfp.return_value = [fake_page]
        mock_itd.return_value = {
            "text": ["Invoice", "123", ""],
            "conf": ["90", "85", "-1"],
        }

        from apps.documents.ocr import ocr_pdf
        result = ocr_pdf("/fake/path.pdf")

        self.assertIn("Invoice", result["text"])
        self.assertIn("123", result["text"])
        self.assertAlmostEqual(result["confidence"], (90 + 85) / 2 / 100.0, places=3)
        self.assertEqual(result["pages"], 1)

    @patch("apps.documents.ocr.convert_from_path")
    @patch("apps.documents.ocr.pytesseract.image_to_data")
    def test_no_words_gives_zero_confidence(self, mock_itd, mock_cfp):
        """A blank page with no detected words → confidence 0.0."""
        mock_cfp.return_value = [MagicMock()]
        mock_itd.return_value = {"text": ["", ""], "conf": ["-1", "-1"]}

        from apps.documents.ocr import ocr_pdf
        result = ocr_pdf("/fake/blank.pdf")

        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["pages"], 1)

    @patch("apps.documents.ocr.convert_from_path")
    @patch("apps.documents.ocr.pytesseract.image_to_data")
    def test_multi_page_confidence_is_averaged(self, mock_itd, mock_cfp):
        """Two pages with different confidence → result is the average."""
        mock_cfp.return_value = [MagicMock(), MagicMock()]
        mock_itd.side_effect = [
            {"text": ["word"], "conf": ["80"]},   # page 1: 0.80
            {"text": ["word"], "conf": ["60"]},   # page 2: 0.60
        ]

        from apps.documents.ocr import ocr_pdf
        result = ocr_pdf("/fake/two_page.pdf")

        self.assertAlmostEqual(result["confidence"], 0.70, places=3)
        self.assertEqual(result["pages"], 2)


class VisionFallbackOCRTests(TestCase):
    """vision_fallback_ocr — cache hit skips LLM; cache miss calls transcribe."""

    @patch("apps.agents.client.get_llm_client")
    @patch("builtins.open", create=True)
    def test_cache_miss_calls_transcribe(self, mock_open, mock_get_client):
        fake_bytes = b"PDF bytes"
        mock_open.return_value.__enter__.return_value.read.return_value = fake_bytes

        mock_client = MagicMock()
        mock_client.transcribe_image_document.return_value = "Transcribed text"
        mock_get_client.return_value = mock_client

        from django.core.cache import cache
        file_hash = hashlib.sha256(fake_bytes).hexdigest()
        cache.delete(f"vision-ocr:{file_hash}")

        from apps.documents.ocr import vision_fallback_ocr
        result = vision_fallback_ocr("/fake/scan.pdf")

        self.assertEqual(result["text"], "Transcribed text")
        self.assertAlmostEqual(result["confidence"], 0.9)
        self.assertIsNone(result["pages"])
        mock_client.transcribe_image_document.assert_called_once_with("/fake/scan.pdf")

    @patch("apps.agents.client.get_llm_client")
    @patch("builtins.open", create=True)
    def test_cache_hit_skips_llm_call(self, mock_open, mock_get_client):
        fake_bytes = b"Cached PDF bytes"
        mock_open.return_value.__enter__.return_value.read.return_value = fake_bytes

        file_hash = hashlib.sha256(fake_bytes).hexdigest()
        from django.core.cache import cache
        cache.set(f"vision-ocr:{file_hash}", {"text": "cached", "confidence": 0.9, "pages": None})

        from apps.documents.ocr import vision_fallback_ocr
        result = vision_fallback_ocr("/fake/cached.pdf")

        self.assertEqual(result["text"], "cached")
        mock_get_client.assert_not_called()
