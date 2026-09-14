"""
Root URL configuration.

Responsibilities of this module:

* Include the search app's presentation-layer URL configuration.
* Expose the OpenAPI schema and the Swagger UI, which are cross-cutting
  concerns owned by the project configuration rather than by any single
  application.

All application endpoints live under ``apps/search/presentation/urls.py``.
"""

from __future__ import annotations

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("", include("apps.search.presentation.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
