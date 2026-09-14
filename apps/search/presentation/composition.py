"""
Composition root for the presentation layer.

This module is the single place where concrete infrastructure adapters are
chosen and injected into application use cases. Views ask the composition
root for a ready-to-use use case; they do not construct use cases or
adapters themselves.

At Phase 2.4 the composition root wires the real
``ElasticsearchClusterHealthProbe`` into the service-status use case. The
view and the application layer are unchanged from Phase 2.2, which is the
point: replacing a stub with the real adapter does not ripple outward.
"""

from __future__ import annotations

from apps.search.application.get_service_status import GetServiceStatusUseCase
from apps.search.infrastructure.probes import ElasticsearchClusterHealthProbe


def build_get_service_status_use_case() -> GetServiceStatusUseCase:
    """Build the use case the service-root endpoint depends on."""
    return GetServiceStatusUseCase(cluster_health_probe=ElasticsearchClusterHealthProbe())
