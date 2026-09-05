from celery import shared_task
from django.core.files.base import ContentFile
from django.db import IntegrityError


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def process_partner_payload(self, payload):
    """Materializes an inbound EDI-style PO/shipment-notice payload into a
    Document, then hands off to the normal ingestion pipeline."""
    from apps.core.models import Workspace, Vendor
    from apps.documents.models import Document
    from apps.documents.tasks import ingest_document, content_hash_of
    import json, hashlib, tempfile, os

    try:
        workspace = Workspace.objects.get(slug=payload["workspace_slug"])
        vendor, _ = Vendor.objects.get_or_create(workspace=workspace, name=payload["vendor_name"])

        raw = json.dumps(payload, sort_keys=True).encode()
        content_hash = hashlib.sha256(raw).hexdigest()

        doc, created = Document.objects.get_or_create(
            workspace=workspace,
            content_hash=content_hash,
            defaults={
                "type": payload.get("document_type", "po"),
                "source": "webhook",
                "extraction": payload.get("fields", {}),
                "vendor": vendor,
                "file": ContentFile(raw, name=f"webhook_{content_hash}.json"),
            },
        )
        if created:
            ingest_document.delay(str(doc.id))
    except Exception as exc:
        raise self.retry(exc=exc)
