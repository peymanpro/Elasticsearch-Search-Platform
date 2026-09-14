"""
Composition root for the presentation layer.

This module is the single place where concrete infrastructure adapters are
chosen and injected into application use cases. Views ask the composition
root for a ready-to-use use case; they do not construct use cases or
adapters themselves.

At Phase 2.2 the composition root uses the stub probe from
``apps.search.infrastructure.probes``. Phase 2.4 will replace that stub
with an adapter backed by the real Elasticsearch client. Views will not
need to change when that happens — this is the point of keeping composition
separate from behaviour.
"""

from __future__ import annotations

from apps.search.application.get_service_status import GetServiceStatusUseCase
from apps.search.infrastructure.probes import StubClusterHealthProbe


def build_get_service_status_use_case() -> GetServiceStatusUseCase:
    """Build the use case the service-root endpoint depends on."""
    return GetServiceStatusUseCase(cluster_health_probe=StubClusterHealthProbe())
