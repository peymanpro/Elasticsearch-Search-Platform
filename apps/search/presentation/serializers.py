"""
Presentation-layer serializers.

Serializers describe the HTTP representation of a request or response.
They are not the domain model; they translate between HTTP and the
application layer's data shapes.
"""

from __future__ import annotations

from rest_framework import serializers


class ServiceRootResponseSerializer(serializers.Serializer):
    """Response shape of the service-root endpoint."""

    service = serializers.CharField(help_text="Service identifier.")
    status = serializers.CharField(help_text="Coarse service-status marker.")
