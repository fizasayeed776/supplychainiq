from rest_framework.routers import DefaultRouter
from .views import WorkspaceViewSet, VendorViewSet, ContractViewSet

router = DefaultRouter()
router.register("workspaces", WorkspaceViewSet, basename="workspace")
router.register("vendors", VendorViewSet, basename="vendor")
router.register("contracts", ContractViewSet, basename="contract")

urlpatterns = router.urls
