"""
Unit tests for Elasticsearch cluster-level helpers.

These tests do not require a running Elasticsearch cluster. The
underlying client is patched at the method level, so the tests verify the
behaviour of ``ping`` and ``cluster_info`` without any network call.
Integration coverage against a live cluster is provided by
``tests/integration/test_elasticsearch_connection.py``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from elasticsearch import Elasticsearch
from infrastructure.elasticsearch.client import reset_client_cache
from infrastructure.elasticsearch.health import cluster_info, ping


@pytest.fixture(autouse=True)
def _clean_client_cache() -> None:
    reset_client_cache()
    yield
    reset_client_cache()


def test_ping_returns_true_when_cluster_responds() -> None:
    with patch.object(Elasticsearch, "ping", return_value=True):
        assert ping() is True


def test_ping_returns_false_when_cluster_is_unreachable() -> None:
    with patch.object(Elasticsearch, "ping", side_effect=ConnectionError("refused")):
        assert ping() is False


def test_cluster_info_returns_client_response() -> None:
    payload = {"cluster_name": "test", "version": {"number": "8.15.0"}}
    with patch.object(Elasticsearch, "info", return_value=payload):
        assert cluster_info() == payload


def test_cluster_info_propagates_failures() -> None:
    with (
        patch.object(Elasticsearch, "info", side_effect=ConnectionError("refused")),
        pytest.raises(ConnectionError),
    ):
        cluster_info()
