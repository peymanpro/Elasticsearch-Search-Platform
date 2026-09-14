"""
Infrastructure probes.

Concrete adapters that satisfy domain-layer ports. This module is the only
place in the search app that reaches out to Elasticsearch: the domain and
application layers depend solely on the ``ClusterHealthProbe`` Protocol
defined in ``apps.search.domain.ports``.

The underlying Elasticsearch client lifecycle is owned by the top-level
``infrastructure.elasticsearch.client`` package (established in Phase 1.4).
This adapter does not create its own client; it consumes the managed one.
"""

from __future__ import annotations

from collections.abc import Callable

from infrastructure.elasticsearch.health import ping as _default_ping


class ElasticsearchClusterHealthProbe:
    """
    Real probe backed by the managed Elasticsearch client.

    The reachability primitive is injected as a callable so that the probe
    can be unit-tested without a running cluster and without patching the
    Elasticsearch client. The default is the ``ping`` function from the
    managed client package, which already returns a boolean and does not
    raise on connection failures.

    The adapter does not add behaviour of its own: it delegates, and it
    propagates any unexpected exception from the underlying callable, since
    a programming error should not be silently converted into "unreachable".
    """

    def __init__(self, ping: Callable[[], bool] | None = None) -> None:
        self._ping: Callable[[], bool] = ping if ping is not None else _default_ping

    def is_reachable(self) -> bool:
        """Return True if the search backend reports itself reachable."""
        return bool(self._ping())
