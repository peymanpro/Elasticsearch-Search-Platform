"""
Presentation-layer views for the search application.

Views are deliberately thin: they translate an HTTP request into a call on
an application use case, then translate the use case's result back into an
HTTP response. They contain no business logic.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.search.presentation.composition import build_get_service_status_use_case
from apps.search.presentation.serializers import ServiceRootResponseSerializer


class ServiceRootView(APIView):
    """
    Return the service identity and a coarse status marker.

    The status is derived by the application layer from the domain's
    ``ServiceStatus`` value object. This view does not decide what "healthy"
    means and does not talk to Elasticsearch.
    """

    @extend_schema(
        responses=ServiceRootResponseSerializer,
        description=(
            "Return the service identity and a coarse status marker. "
            "Status is derived from the reachability of the search backend."
        ),
        tags=["service"],
    )
    def get(self, request: Request) -> Response:
        status = build_get_service_status_use_case().execute()
        return Response(
            {
                "service": status.service_name,
                "status": status.state.value,
            }
        )
