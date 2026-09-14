"""
Root URL configuration.

The only endpoint present at Phase 1.3 is a service-identity endpoint
implemented as a Django REST Framework view. Real search endpoints are
added in Phase 19.
"""

from __future__ import annotations

from django.urls import path
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class ServiceRootView(APIView):
    """
    Return the service identity and a coarse status marker.

    This is intentionally a thin APIView rather than a function-based view:
    every subsequent API endpoint in this project is class-based, and this
    establishes that pattern from the first line of API code.
    """

    def get(self, request: Request) -> Response:
        return Response(
            {
                "service": "elasticsearch-search-platform",
                "status": "ok",
            }
        )


urlpatterns = [
    path("", ServiceRootView.as_view(), name="service-root"),
]
