"""
URL configuration for finance_tracker project.
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from api.views.meta import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", HealthView.as_view(), name="health_check"),
    path("api/v1/", include("api.urls", namespace="api")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("", RedirectView.as_view(url="/api/docs/", permanent=False)),
]
