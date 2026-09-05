from django.contrib import admin
from .models import Chunk, ChatSession, ChatMessage

admin.site.register(Chunk)
admin.site.register(ChatSession)
admin.site.register(ChatMessage)
