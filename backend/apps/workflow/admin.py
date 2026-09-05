from django.contrib import admin
from .models import ApprovalFlow, ApprovalStep, Dispute, TriageRule, WebhookDelivery

admin.site.register(ApprovalFlow)
admin.site.register(ApprovalStep)
admin.site.register(Dispute)
admin.site.register(TriageRule)
admin.site.register(WebhookDelivery)
