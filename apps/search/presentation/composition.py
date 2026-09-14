"""
Composition root for the presentation layer.

This module is the single place where concrete infrastructure adapters are
chosen and injected into application use cases. Views ask the composition
root for a ready-to-use use case; they do not construct use cases or
adapters themselves.

Dependency Inversion at the composition boundary (Phase 3.2)
------------------------------------------------------------
The use case depends only on the domain-defined ``ClusterHealthProbe``
Protocol. This composition function is the one place where a concrete
implementation is chosen. That choice is parameterised -- the ``probe``
argument -- so that:

    * production code calls it with no arguments and gets the real
      Elasticsearch adapter,
    * tests call it with a fake adapter and get a use case that behaves
      according to the fake.

The seam is what makes the inversion observable rather than declared.
"""

from __future__ import annotations

from apps.search.application.get_service_status import GetServiceStatusUseCase
from apps.search.domain.ports import ClusterHealthProbe
from apps.search.infrastructure.probes import ElasticsearchClusterHealthProbe


def build_get_service_status_use_case(
    probe: ClusterHealthProbe | None = None,
) -> GetServiceStatusUseCase:
    """
    Build the use case the service-root endpoint depends on.

    Args:
        probe: Optional adapter satisfying the domain's ``ClusterHealthProbe``
            Protocol. When omitted (the production path), the real
            Elasticsearch-backed adapter is used. When supplied (the test
            path), the given adapter is injected instead.
    """
    adapter: ClusterHealthProbe = probe if probe is not None else ElasticsearchClusterHealthProbe()
    return GetServiceStatusUseCase(cluster_health_probe=adapter)
