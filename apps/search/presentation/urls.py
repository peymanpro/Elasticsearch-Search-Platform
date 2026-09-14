"""
URL configuration for the search application's presentation layer.

Every endpoint here is exposed under the root path. The search API
lives under /api/, and the service-identity endpoint lives at /.

See docs/24-search-api.md.
"""

from __future__ import annotations

from django.urls import path

from apps.search.presentation.views import (
    ExplainView,
    HealthView,
    SearchView,
    ServiceRootView,
    SuggestView,
)

app_name = "search"

urlpatterns = [
    path("", ServiceRootView.as_view(), name="service-root"),
    path("api/search/", SearchView.as_view(), name="search"),
    path("api/suggest/", SuggestView.as_view(), name="suggest"),
    path("api/explain/", ExplainView.as_view(), name="explain"),
    path("api/health/", HealthView.as_view(), name="health"),
]
