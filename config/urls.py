"""
Root URL configuration.

Endpoints present at Phase 1.5:

* ``/``             - service identity, used by smoke tests and probes.
* ``/api/schema/``  - OpenAPI 3 schema (YAML).
* ``/api/docs/``    - Swagger UI rendered from the schema.

Real search endpoints are added in Phase 19.
"""

from __future__ import annotations

from django.urls import path
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class ServiceRootResponseSerializer(serializers.Serializer):
    """Response shape of the service-root endpoint."""

    service = serializers.CharField(help_text="Service identifier.")
    status = serializers.CharField(help_text="Coarse service-status marker.")


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


urlpatterns = [
    path("", ServiceRootView.as_view(), name="service-root"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
