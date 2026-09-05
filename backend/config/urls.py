from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from apps.core.views import health_check
from apps.core.registration import register

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/register/", register, name="register"),
    path("api/health/", health_check, name="health_check"),
    path("api/core/", include("apps.core.urls")),
    path("api/documents/", include("apps.documents.urls")),
    path("api/matching/", include("apps.matching.urls")),
    path("api/workflow/", include("apps.workflow.urls")),
    path("api/chat/", include("apps.chat.urls")),
    path("webhooks/", include("apps.webhooks.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
