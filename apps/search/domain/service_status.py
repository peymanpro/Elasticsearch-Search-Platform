"""
Domain value objects for the service-status concern.

These types express what the domain considers meaningful about a service
status report. They carry no framework knowledge: no Django, no DRF, no
Elasticsearch client.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ServiceState(StrEnum):
    """Coarse service state used by the presentation layer."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    """
    Result of asking the platform for its own status.

    Attributes:
        service_name: Stable identifier for this service.
        state: Coarse state, derived from the dependencies' reachability.
        elasticsearch_reachable: Whether the search backend could be reached.
    """

    service_name: str
    state: ServiceState
    elasticsearch_reachable: bool

    @classmethod
    def from_probe(cls, service_name: str, elasticsearch_reachable: bool) -> ServiceStatus:
        """
        Construct a status from a dependency probe result.

        The classification rule lives on the domain type, not in the use case
        or the view, so that it is expressed once and can be tested once.
        """
        state = ServiceState.HEALTHY if elasticsearch_reachable else ServiceState.DEGRADED
        return cls(
            service_name=service_name,
            state=state,
            elasticsearch_reachable=elasticsearch_reachable,
        )
