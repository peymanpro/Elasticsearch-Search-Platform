"""
Domain ports.

A port is a contract the domain offers to the application layer and that
infrastructure adapters implement. Ports are deliberately expressed as
``typing.Protocol`` so that implementations do not need to inherit from
anything and the domain package has no runtime dependency on any concrete
adapter.

Nothing in this module may import Django, DRF, or the Elasticsearch client.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ClusterHealthProbe(Protocol):
    """
    Contract for asking whether the search backend is reachable.

    The application layer depends only on this Protocol. Which concrete
    implementation satisfies it — a stub, the real Elasticsearch client, or
    a test double — is decided at composition time.
    """

    def is_reachable(self) -> bool:
        """Return True if the search backend can currently be reached."""
        ...
