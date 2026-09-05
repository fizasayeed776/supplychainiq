from rest_framework.routers import DefaultRouter
from .views import (
    DocumentViewSet, PurchaseOrderViewSet, InvoiceViewSet,
    DeliveryReceiptViewSet, ScanRunViewSet,
)

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="document")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchaseorder")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("delivery-receipts", DeliveryReceiptViewSet, basename="deliveryreceipt")
router.register("scan-runs", ScanRunViewSet, basename="scanrun")

urlpatterns = router.urls
