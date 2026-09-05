"""
OCR helpers. Tesseract does the heavy lifting locally (free); low-confidence
pages fall back to a vision-capable LLM call (cheap, cached by content hash).
"""
import logging
import hashlib

import pytesseract
from django.conf import settings
from pdf2image import convert_from_path

logger = logging.getLogger(__name__)

pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD


def ocr_pdf(file_path: str) -> dict:
    """Run Tesseract over every page of a scanned PDF.

    Returns {"text": str, "confidence": float 0..1, "pages": int}.
    """
    pages = convert_from_path(file_path, dpi=300)
    texts, confidences = [], []

    for page in pages:
        data = pytesseract.image_to_data(page, output_type=pytesseract.Output.DICT)
        words = [w for w in data["text"] if w.strip()]
        confs = [int(c) for c, w in zip(data["conf"], data["text"]) if w.strip() and c != "-1"]
        texts.append(" ".join(words))
        if confs:
            confidences.append(sum(confs) / len(confs) / 100.0)

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return {"text": "\n\n".join(texts), "confidence": avg_confidence, "pages": len(pages)}


def vision_fallback_ocr(file_path: str) -> dict:
    """Low-confidence fallback: ask the vision-capable fast model to transcribe.

    Cheap (pennies) and covered by the standard prompt/response cache upstream.
    """
    from apps.agents.client import get_llm_client
    from django.core.cache import cache

    with open(file_path, "rb") as document_file:
        file_hash = hashlib.sha256(document_file.read()).hexdigest()
    cache_key = f"vision-ocr:{file_hash}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    client = get_llm_client()
    text = client.transcribe_image_document(file_path)
    result = {"text": text, "confidence": 0.9, "pages": None}
    cache.set(cache_key, result, timeout=60 * 60 * 24 * 7)
    return result
