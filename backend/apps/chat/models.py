from django.db import models
from pgvector.django import VectorField
from django.conf import settings

from apps.core.models import TimeStampedModel, Workspace
from apps.documents.models import Document


class Chunk(TimeStampedModel):
    """RAG retrieval unit."""
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    text = models.TextField()
    embedding = VectorField(dimensions=1536)
    token_count = models.PositiveIntegerField(default=0)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("document", "position")


class ChatSession(TimeStampedModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="chat_sessions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=255, blank=True)


class ChatMessage(TimeStampedModel):
    ROLE_CHOICES = [("user", "User"), ("assistant", "Assistant")]
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    citations = models.JSONField(default=list, blank=True)  # [{chunk_id, document_id, snippet}]

    class Meta:
        ordering = ["created_at"]
