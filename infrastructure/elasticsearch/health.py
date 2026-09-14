"""
Elasticsearch cluster-level helpers: reachability and identity.

This module is deliberately separate from ``client.py``. The two modules
answer different questions:

    client.py  : how do we obtain a managed Elasticsearch client?
    health.py  : is the cluster reachable, and what does it say about
                 itself?

They change for different reasons. Connection parameters, pooling, and
retry policy affect the lifecycle module. What "reachable" means, and
which cluster-level facts we expose, affect this module. Keeping them in
one file would create a module with two reasons to change -- the canonical
Single Responsibility violation identified during the project's SOLID
review (Phase 3.1).

The module depends on the client factory but not on the client factory's
internals: it obtains a client via ``get_client`` and asks it questions.
"""

from __future__ import annotations

import logging

from infrastructure.elasticsearch.client import get_client

logger = logging.getLogger(__name__)


def ping() -> bool:
    """
    Return True if the cluster is reachable, False otherwise.

    Connection and transport failures are treated as "unreachable" rather
    than propagated, because the caller is asking a yes/no question. Every
    other failure mode is still surfaced by the underlying client.
    """
    try:
        return bool(get_client().ping())
    except Exception as exc:  # noqa: BLE001 - reachability check returns a boolean by contract
        logger.warning("Elasticsearch ping failed: %s", exc)
        return False


def cluster_info() -> dict:
    """
    Return the cluster's ``GET /`` response.

    Unlike :func:`ping`, this propagates failures: callers use it when they
    need the cluster's identity, and an unreachable cluster should not be
    silently converted into an empty dict.
    """
    return get_client().info()
