from django.urls import re_path
from .consumers import DashboardConsumer, ChatConsumer, ApprovalRoomConsumer

websocket_urlpatterns = [
    re_path(r"ws/dashboard/(?P<workspace_id>[0-9a-f-]+)/$", DashboardConsumer.as_asgi()),
    re_path(r"ws/chat/(?P<session_id>[0-9a-f-]+)/$", ChatConsumer.as_asgi()),
    re_path(r"ws/approval-room/(?P<invoice_id>[0-9a-f-]+)/$", ApprovalRoomConsumer.as_asgi()),
]
