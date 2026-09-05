from rest_framework.routers import DefaultRouter
from .views import ApprovalFlowViewSet, DisputeViewSet, TriageRuleViewSet

router = DefaultRouter()
router.register("approvals", ApprovalFlowViewSet, basename="approvalflow")
router.register("disputes", DisputeViewSet, basename="dispute")
router.register("triage-rules", TriageRuleViewSet, basename="triagerule")

urlpatterns = router.urls
