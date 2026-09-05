from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ChatSession, ChatMessage
from .serializers import ChatSessionSerializer, ChatMessageSerializer
from .rag import answer_question


class ChatSessionViewSet(viewsets.ModelViewSet):
    queryset = ChatSession.objects.prefetch_related("messages").all()
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["workspace"]

    def get_queryset(self):
        return super().get_queryset().filter(workspace__members=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def ask(self, request, pk=None):
        """Non-streaming fallback for clients not using the websocket.
        The React app normally streams via ChatConsumer instead."""
        session = self.get_object()
        question = request.data.get("question", "")
        if not question:
            return Response({"detail": "question is required"}, status=status.HTTP_400_BAD_REQUEST)

        ChatMessage.objects.create(session=session, role="user", content=question)
        result = answer_question(question, session.workspace_id)
        assistant_message = ChatMessage.objects.create(
            session=session, role="assistant", content=result["answer"], citations=result["citations"]
        )
        return Response(ChatMessageSerializer(assistant_message).data)
