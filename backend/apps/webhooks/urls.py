from django.urls import path
from .views import partner_webhook

urlpatterns = [
    path("partner/", partner_webhook, name="partner-webhook"),
]
