"""
Unit tests for the Elasticsearch cluster helpers.

These tests patch the underlying client method so that no network
call is made. Integration coverage against a running cluster is
provided by tests/integration/.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from elasticsearch import Elasticsearch
from infrastructure.elasticsearch.client import reset_client_cache
from infrastructure.elasticsearch.health import (
    cluster_health,
    nodes_info,
)


@pytest.fixture(autouse=True)
def _clean_client_cache() -> None:
    reset_client_cache()
    yield
    reset_client_cache()


def test_cluster_health_returns_client_response() -> None:
    payload = {"cluster_name": "esp-cluster", "status": "green"}
    with patch.object(Elasticsearch, "cluster", create=True):
        # The client exposes `cluster` as a namespace; patching the
        # leaf method is awkward, so we patch the whole namespace with
        # a small stub that returns our payload.
        class _Stub:
            def health(self) -> dict:
                return payload

        with patch("infrastructure.elasticsearch.health.get_client") as fake:
            fake.return_value = type("C", (), {"cluster": _Stub()})()
            assert cluster_health() == payload


def test_cluster_health_propagates_failures() -> None:
    with patch("infrastructure.elasticsearch.health.get_client") as fake:

        class _Stub:
            def health(self) -> dict:
                raise ConnectionError("refused")

        fake.return_value = type("C", (), {"cluster": _Stub()})()
        with pytest.raises(ConnectionError):
            cluster_health()


def test_nodes_info_returns_client_response() -> None:
    payload = {"nodes": {"node-1": {"name": "esp-node-01"}}}
    with patch("infrastructure.elasticsearch.health.get_client") as fake:

        class _Stub:
            def info(self) -> dict:
                return payload

        fake.return_value = type("C", (), {"nodes": _Stub()})()
        assert nodes_info() == payload


def test_nodes_info_propagates_failures() -> None:
    with patch("infrastructure.elasticsearch.health.get_client") as fake:

        class _Stub:
            def info(self) -> dict:
                raise ConnectionError("refused")

        fake.return_value = type("C", (), {"nodes": _Stub()})()
        with pytest.raises(ConnectionError):
            nodes_info()
