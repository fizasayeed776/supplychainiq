from rest_framework.routers import DefaultRouter
from .views import MatchResultViewSet

router = DefaultRouter()
router.register("results", MatchResultViewSet, basename="matchresult")

urlpatterns = router.urls
