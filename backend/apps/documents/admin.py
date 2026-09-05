from django.contrib import admin
from .models import Document, LineItem, PurchaseOrder, Invoice, DeliveryReceipt, ScanRun

admin.site.register(Document)
admin.site.register(LineItem)
admin.site.register(PurchaseOrder)
admin.site.register(Invoice)
admin.site.register(DeliveryReceipt)
admin.site.register(ScanRun)
