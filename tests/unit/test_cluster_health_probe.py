"""
Unit tests for the Elasticsearch cluster health probe adapter.

The adapter is tested against injected ping callables; no Elasticsearch
client is created and no network call is made. Integration coverage
against a live cluster is provided by
``tests/integration/test_elasticsearch_connection.py``.
"""

from __future__ import annotations

import pytest

from apps.search.domain.ports import ClusterHealthProbe
from apps.search.infrastructure.probes import ElasticsearchClusterHealthProbe


def test_probe_satisfies_cluster_health_probe_protocol() -> None:
    # The domain declares the contract; the adapter must satisfy it.
    probe = ElasticsearchClusterHealthProbe(ping=lambda: True)
    assert isinstance(probe, ClusterHealthProbe)


def test_is_reachable_returns_true_when_ping_is_true() -> None:
    probe = ElasticsearchClusterHealthProbe(ping=lambda: True)
    assert probe.is_reachable() is True


def test_is_reachable_returns_false_when_ping_is_false() -> None:
    probe = ElasticsearchClusterHealthProbe(ping=lambda: False)
    assert probe.is_reachable() is False


def test_ping_callable_is_invoked_on_each_call() -> None:
    calls = {"count": 0}

    def counting_ping() -> bool:
        calls["count"] += 1
        return True

    probe = ElasticsearchClusterHealthProbe(ping=counting_ping)
    probe.is_reachable()
    probe.is_reachable()

    assert calls["count"] == 2


def test_unexpected_errors_from_ping_propagate() -> None:
    # A programming error is not "unreachable"; the adapter must not
    # swallow it. Reachability failures are handled by the managed ping
    # function itself (Phase 1.4), not by this adapter.
    def broken_ping() -> bool:
        raise RuntimeError("programming error")

    probe = ElasticsearchClusterHealthProbe(ping=broken_ping)
    with pytest.raises(RuntimeError):
        probe.is_reachable()


def test_default_ping_is_the_managed_client_ping() -> None:
    # When no callable is injected, the adapter must delegate to the
    # managed client's ping, not to a stub or an unrelated function.
    from infrastructure.elasticsearch import client as client_module

    probe = ElasticsearchClusterHealthProbe()
    assert probe._ping is client_module.ping
