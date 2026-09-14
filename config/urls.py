"""
Root URL configuration.

The only endpoint present at Phase 1.2 is a trivial service-identity
endpoint, used by the smoke test and by infrastructure health probes.
Real search endpoints arrive in Phase 19.
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.urls import path


def service_root(request: HttpRequest) -> JsonResponse:
    """Return the service identity and a coarse status marker."""
    return JsonResponse(
        {
            "service": "elasticsearch-search-platform",
            "status": "ok",
        }
    )


urlpatterns = [
    path("", service_root, name="service-root"),
]
