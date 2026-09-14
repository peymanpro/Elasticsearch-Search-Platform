"""
Presentation-layer views for the search application.

At Phase 2.1 the only endpoint is the service-identity endpoint carried
over from Phase 1.5. It is deliberately thin: all real search views will
arrive in Phase 19, at which point they will call use cases from the
application layer rather than returning hard-coded payloads.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.search.presentation.serializers import ServiceRootResponseSerializer


class ServiceRootView(APIView):
    """
    Return the service identity and a coarse status marker.

    This is intentionally a thin APIView rather than a function-based view:
    every subsequent API endpoint in this project is class-based, and this
    establishes that pattern from the first line of API code.
    """

    @extend_schema(
        responses=ServiceRootResponseSerializer,
        description=(
            "Return the service identity and a coarse status marker. "
            "Used by smoke tests and by infrastructure health probes."
        ),
        tags=["service"],
    )
    def get(self, request: Request) -> Response:
        return Response(
            {
                "service": "elasticsearch-search-platform",
                "status": "ok",
            }
        )
