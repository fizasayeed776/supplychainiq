import hashlib
import logging
from datetime import datetime

from celery import chain, shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_date

from .models import Document, ScanRun

logger = logging.getLogger(__name__)


def _publish_progress(workspace_id, payload):
    """Push a pipeline-progress event to the workspace's dashboard group."""
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(
        f"dashboard_{workspace_id}",
        {"type": "pipeline.progress", "payload": payload},
    )


def content_hash_of(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def ingest_document(self, document_id):
    """Entry point per uploaded/received file. Dispatches the per-file
    pipeline as a chain so a failure at any stage can retry without
    redoing prior (already-cached/committed) work."""
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.warning("ingest_document: document %s vanished, skipping", document_id)
        return

    # Idempotency guard: duplicate content for this workspace is a no-op.
    dup = (
        Document.objects.filter(workspace=doc.workspace, content_hash=doc.content_hash)
        .exclude(id=doc.id)
        .exists()
    )
    if dup:
        doc.ocr_status = "not_needed"
        doc.save(update_fields=["ocr_status"])
        _publish_progress(doc.workspace_id, {"document": str(doc.id), "stage": "duplicate_skipped"})
        return

    native_text = _read_native_text(doc.file.path, doc.file.name)
    is_native_text = native_text is not None
    if is_native_text:
        doc.raw_text = native_text
        doc.ocr_status = "not_needed"
        doc.save(update_fields=["raw_text", "ocr_status"])
    pipeline = (
        chain(extract_document.s(document_id))
        if is_native_text
        else chain(ocr_document.s(document_id), extract_document.si(document_id))
    )
    pipeline.apply_async()


def _read_native_text(path: str, name: str):
    if name.lower().endswith(".txt"):
        with open(path, "r", encoding="utf-8", errors="replace") as text_file:
            return text_file.read()
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
        return text or None
    except Exception:
        return None


@shared_task(bind=True, max_retries=5, retry_backoff=True, retry_backoff_max=300, acks_late=True)
def ocr_document(self, document_id):
    from .ocr import ocr_pdf, vision_fallback_ocr
    from django.conf import settings

    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.warning("ocr_document: document %s vanished, skipping", document_id)
        return
    doc.ocr_status = "running"
    doc.failure_reason = ""
    doc.save(update_fields=["ocr_status", "failure_reason"])
    _publish_progress(doc.workspace_id, {"document": str(doc.id), "stage": "ocr_running"})

    try:
        result = ocr_pdf(doc.file.path)
        if result["confidence"] < settings.OCR_LOW_CONFIDENCE_THRESHOLD:
            result = vision_fallback_ocr(doc.file.path)
            doc.ocr_status = "low_confidence"
        else:
            doc.ocr_status = "done"
        doc.raw_text = result["text"]
        doc.confidence = result["confidence"]
        doc.save(update_fields=["raw_text", "confidence", "ocr_status"])
        _publish_progress(doc.workspace_id, {"document": str(doc.id), "stage": "ocr_done"})
    except Exception as exc:
        doc.ocr_status = "failed"
        doc.failure_reason = str(exc)[:2000]
        if self.request.retries < self.max_retries:
            doc.ocr_status = "pending"
        doc.save(update_fields=["ocr_status", "failure_reason"])
        if self.request.retries >= self.max_retries:
            logger.error("ocr_document permanently failed for %s", document_id, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, retry_backoff=True, acks_late=True)
def extract_document(self, document_id):
    """Extractor agent: raw text -> schema-enforced structured JSON."""
    from apps.agents.extractor import run_extractor

    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.warning("extract_document: document %s vanished, skipping", document_id)
        return
    doc.extraction_status = "running"
    doc.failure_reason = ""
    doc.save(update_fields=["extraction_status", "failure_reason"])
    try:
        extraction = run_extractor(doc)
        doc.extraction = extraction["fields"]
        doc.type = extraction.get("document_type", doc.type)
        doc.confidence = extraction.get("confidence", doc.confidence)
        doc.extraction_status = "done"
        doc.save(update_fields=["extraction", "type", "confidence", "extraction_status"])
        _materialize_structured_record(doc)
        embed_chunks.delay(document_id)
        _publish_progress(doc.workspace_id, {"document": str(doc.id), "stage": "extraction_done"})
    except Exception as exc:
        status = "failed" if self.request.retries >= self.max_retries else "pending"
        doc.extraction_status = status
        doc.failure_reason = str(exc)[:2000]
        doc.save(update_fields=["extraction_status", "failure_reason"])
        logger.error("extract_document failed for %s", document_id, exc_info=True)
        raise self.retry(exc=exc)


def _materialize_structured_record(doc: Document):
    """Turn extraction JSON into a structured record and idempotent line items."""
    from .models import PurchaseOrder, Invoice, DeliveryReceipt, LineItem
    from apps.core.models import Contract, Vendor

    fields = doc.extraction
    line_items = fields.get("line_items", [])
    vendor = doc.vendor
    vendor_name = fields.get("vendor_name")
    if vendor is None and vendor_name:
        vendor, _ = Vendor.objects.get_or_create(
            workspace=doc.workspace,
            name=vendor_name,
        )
        doc.vendor = vendor
        doc.save(update_fields=["vendor"])

    if doc.type in {"po", "invoice", "delivery_receipt", "contract"} and vendor is None:
        logger.warning(
            "Skipping structured materialization for document %s (type=%s): vendor could not be resolved",
            doc.id,
            doc.type,
        )
        return

    if doc.type == "po":
        PurchaseOrder.objects.update_or_create(
            document=doc,
            defaults={
                "workspace": doc.workspace, "vendor": vendor,
                "po_number": fields.get("po_number", ""), "order_date": fields.get("order_date"),
                "currency": fields.get("currency", "USD"), "total_amount": fields.get("total_amount"),
            },
        )
    elif doc.type == "invoice":
        Invoice.objects.update_or_create(
            document=doc,
            defaults={
                "workspace": doc.workspace, "vendor": vendor,
                "invoice_number": fields.get("invoice_number", ""),
                "referenced_po_number": fields.get("referenced_po_number", ""),
                "invoice_date": fields.get("invoice_date"), "due_date": fields.get("due_date"),
                "currency": fields.get("currency", "USD"), "total_amount": fields.get("total_amount"),
            },
        )
    elif doc.type == "delivery_receipt":
        DeliveryReceipt.objects.update_or_create(
            document=doc,
            defaults={
                "workspace": doc.workspace, "vendor": vendor,
                "referenced_po_number": fields.get("referenced_po_number", ""),
                "delivery_date": fields.get("delivery_date"),
                "is_partial": fields.get("is_partial", False),
            },
        )
    elif doc.type == "contract":
        if vendor is not None:
            Contract.objects.update_or_create(
                source_document_id=doc.id,
                defaults={
                    "workspace": doc.workspace,
                    "vendor": vendor,
                    "file": doc.file.name,
                    "terms": {
                        "rate_cards": fields.get("rate_cards", []),
                        "payment_days": fields.get("payment_days"),
                        "sla": fields.get("sla", {}),
                    },
                    "valid_from": parse_date(fields.get("valid_from")) if fields.get("valid_from") else None,
                    "valid_until": parse_date(fields.get("valid_until")) if fields.get("valid_until") else None,
                },
            )

    positions = []
    for i, li in enumerate(line_items):
        positions.append(i)
        LineItem.objects.update_or_create(
            document=doc,
            position=i,
            defaults={
                "sku": li.get("sku", ""), "description": li.get("description", ""),
                "quantity": li.get("quantity", 0), "unit_price": li.get("unit_price", 0),
                "currency": li.get("currency", fields.get("currency", "USD")),
            },
        )
    LineItem.objects.filter(document=doc).exclude(position__in=positions).delete()

    from apps.matching.tasks import try_three_way_match
    if doc.type == "invoice":
        try_three_way_match.delay(str(doc.invoice.id))


@shared_task(bind=True, max_retries=3, retry_backoff=True, acks_late=True)
def poll_mailpit(self):
    """Import unseen Mailpit attachments through the normal document pipeline."""
    import requests

    from apps.core.models import Workspace

    try:
        workspace = Workspace.objects.get(slug=settings.MAILPIT_WORKSPACE_SLUG)
        response = requests.get(
            f"{settings.MAILPIT_API_URL.rstrip('/')}/api/v1/messages",
            params={"limit": 100}, timeout=5,
        )
        response.raise_for_status()
        for message in response.json().get("messages", []):
            message_id = message.get("ID") or message.get("Id") or message.get("id")
            if not message_id:
                continue
            detail_response = requests.get(
                f"{settings.MAILPIT_API_URL.rstrip('/')}/api/v1/message/{message_id}", timeout=5
            )
            detail_response.raise_for_status()
            for attachment in detail_response.json().get("Attachments", []):
                part_id = attachment.get("PartID") or attachment.get("part_id")
                file_name = attachment.get("FileName") or attachment.get("filename") or "attachment"
                if not message_id or not part_id:
                    continue
                seen_key = f"mailpit-imported:{message_id}:{part_id}"
                if cache.get(seen_key):
                    continue
                content_response = requests.get(
                    f"{settings.MAILPIT_API_URL.rstrip('/')}/api/v1/message/{message_id}/part/{part_id}",
                    timeout=5,
                )
                content_response.raise_for_status()
                raw = content_response.content
                content_hash = hashlib.sha256(raw).hexdigest()
                doc, created = Document.objects.get_or_create(
                    workspace=workspace,
                    content_hash=content_hash,
                    defaults={
                        "type": "other", "source": "email",
                        "file": ContentFile(raw, name=file_name),
                    },
                )
                cache.set(seen_key, True, timeout=None)
                if created:
                    ingest_document.delay(str(doc.id))
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def embed_chunks(self, document_id):
    """Chunk (~500 tokens, overlapping) and embed via the configured embedding
    model. Cache key = SHA-256 of chunk text; a hit skips the API call."""
    from apps.chat.rag import chunk_text
    from apps.chat.models import Chunk
    from apps.agents.client import get_llm_client

    doc = Document.objects.get(id=document_id)
    client = get_llm_client()
    chunks = chunk_text(doc.raw_text or "", max_tokens=500, overlap_tokens=50)

    for position, chunk_str in enumerate(chunks):
        cache_key = f"emb:{hashlib.sha256(chunk_str.encode()).hexdigest()}"
        vector = cache.get(cache_key)
        if vector is None:
            vector = client.embed(chunk_str)
            cache.set(cache_key, vector, timeout=None)  # embeddings are content-addressed, cache forever
        Chunk.objects.update_or_create(
            document=doc, position=position,
            defaults={"text": chunk_str, "embedding": vector, "token_count": len(chunk_str.split())},
        )

    # After all chunks are embedded, snapshot current LLM usage counters into
    # the associated ScanRun so per-run cost/cache data is visible in the API.
    if doc.scan_run_id:
        _stamp_scan_run_usage(doc.scan_run_id)


def _stamp_scan_run_usage(scan_run_id) -> None:
    """Write a snapshot of current LLM usage counters into ScanRun.statistics.

    Safe to call from any task — errors are swallowed so they never fail the
    calling task.  The snapshot reflects cumulative monthly counters, not a
    per-run delta, which is sufficient for the cost-visibility requirement."""
    try:
        from apps.agents.usage import get_snapshot
        from django.utils import timezone

        scan_run = ScanRun.objects.get(id=scan_run_id)
        existing = scan_run.statistics or {}
        existing["llm_usage"] = get_snapshot()
        existing["llm_usage_updated_at"] = timezone.now().isoformat()
        scan_run.statistics = existing
        scan_run.save(update_fields=["statistics"])
    except Exception:
        logger.exception("_stamp_scan_run_usage failed for scan_run_id=%s", scan_run_id)
