from django.db import IntegrityError
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Document, PurchaseOrder, Invoice, DeliveryReceipt, ScanRun
from .serializers import (
    DocumentSerializer, DocumentUploadSerializer, PurchaseOrderSerializer,
    InvoiceSerializer, DeliveryReceiptSerializer, ScanRunSerializer,
)
from .tasks import ingest_document, content_hash_of


class WorkspaceScopedMixin:
    def get_queryset(self):
        return super().get_queryset().filter(workspace__members=self.request.user)


class DocumentViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Document.objects.select_related("vendor").prefetch_related("line_items").order_by("-created_at")
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["workspace", "type", "ocr_status", "vendor"]

    def get_serializer_class(self):
        return DocumentUploadSerializer if self.action == "create" else DocumentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(source="upload")
        instance.content_hash = content_hash_of(instance.file.path)

        existing = Document.objects.filter(
            workspace=instance.workspace,
            content_hash=instance.content_hash,
        ).exclude(pk=instance.pk).first()
        if existing:
            instance.delete()
            return Response(
                {
                    "detail": "This document was already uploaded.",
                    "existing_document_id": str(existing.id),
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            instance.save(update_fields=["content_hash"])
        except IntegrityError:
            existing = Document.objects.filter(
                workspace=instance.workspace,
                content_hash=instance.content_hash,
            ).exclude(pk=instance.pk).first()
            instance.delete()
            if existing:
                return Response(
                    {
                        "detail": "This document was already uploaded.",
                        "existing_document_id": str(existing.id),
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            raise

        ingest_document.delay(str(instance.id))
        return Response(DocumentSerializer(instance).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="correct-extraction")
    def correct_extraction(self, request, pk=None):
        """Allow manual correction of specific extracted fields (human-in-the-loop)."""
        document = self.get_object()
        corrections = request.data.get("corrections")
        if not isinstance(corrections, dict) or not corrections:
            return Response(
                {"detail": "corrections must be a non-empty object of field:value pairs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Merge corrections into existing extraction — don't replace the whole dict
        extraction = dict(document.extraction or {})
        extraction.update(corrections)
        document.extraction = extraction
        # Record that this document was manually corrected
        document.failure_reason = ""  # clear any prior failure
        document.save(update_fields=["extraction", "failure_reason", "updated_at"])

        return Response(DocumentSerializer(document).data)


class PurchaseOrderViewSet(WorkspaceScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = PurchaseOrder.objects.select_related("vendor", "document").all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["workspace", "vendor"]


class InvoiceViewSet(WorkspaceScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Invoice.objects.select_related("vendor", "document").all()
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["workspace", "vendor"]


class DeliveryReceiptViewSet(WorkspaceScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = DeliveryReceipt.objects.select_related("vendor", "document").all()
    serializer_class = DeliveryReceiptSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["workspace", "vendor"]


class ScanRunViewSet(WorkspaceScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ScanRun.objects.all().order_by("-started_at")
    serializer_class = ScanRunSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["workspace", "trigger"]
