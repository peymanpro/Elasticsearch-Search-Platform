"""
Use case: report the platform's own service status.

The use case coordinates: it asks a domain port whether the search backend
is reachable, then asks the domain to classify the outcome. It does not
know which concrete probe it holds, and it does not touch HTTP, Django, or
the Elasticsearch client.
"""

from __future__ import annotations

from apps.search.domain.ports import ClusterHealthProbe
from apps.search.domain.service_status import ServiceStatus

SERVICE_NAME = "elasticsearch-search-platform"


class GetServiceStatusUseCase:
    """Return the current service status of the platform."""

    def __init__(self, cluster_health_probe: ClusterHealthProbe) -> None:
        self._cluster_health_probe = cluster_health_probe

    def execute(self) -> ServiceStatus:
        """Run the use case and return the domain result."""
        reachable = self._cluster_health_probe.is_reachable()
        return ServiceStatus.from_probe(
            service_name=SERVICE_NAME,
            elasticsearch_reachable=reachable,
        )
