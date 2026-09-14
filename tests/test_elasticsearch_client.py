"""
Unit tests for the Elasticsearch client lifecycle and settings.

These tests do not require a running Elasticsearch cluster. They exercise
configuration parsing and lifecycle management, mocking the underlying
client where network behavior would otherwise be required. Integration
tests against a live cluster arrive in Phase 1.6, once Docker Compose is
in place.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from elasticsearch import Elasticsearch
from infrastructure.elasticsearch.client import (
    cluster_info,
    get_client,
    ping,
    reset_client_cache,
)
from infrastructure.elasticsearch.config import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_URL,
    ElasticsearchSettings,
)

_ES_ENV_KEYS = (
    "ELASTICSEARCH_URL",
    "ELASTICSEARCH_USERNAME",
    "ELASTICSEARCH_PASSWORD",
    "ELASTICSEARCH_TIMEOUT",
    "ELASTICSEARCH_MAX_RETRIES",
)


@pytest.fixture(autouse=True)
def _clean_client_cache() -> None:
    """Guarantee a fresh client cache around each test."""
    reset_client_cache()
    yield
    reset_client_cache()


# ---------------------------------------------------------------------------
# Settings parsing
# ---------------------------------------------------------------------------
class TestElasticsearchSettings:
    def test_defaults_apply_when_environment_is_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in _ES_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)

        settings = ElasticsearchSettings.from_env()

        assert settings.url == DEFAULT_URL
        assert settings.username is None
        assert settings.password is None
        assert settings.timeout == DEFAULT_TIMEOUT
        assert settings.max_retries == DEFAULT_MAX_RETRIES

    def test_values_are_read_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ELASTICSEARCH_URL", "http://es.internal:9200")
        monkeypatch.setenv("ELASTICSEARCH_USERNAME", "elastic")
        monkeypatch.setenv("ELASTICSEARCH_PASSWORD", "s3cret")
        monkeypatch.setenv("ELASTICSEARCH_TIMEOUT", "5")
        monkeypatch.setenv("ELASTICSEARCH_MAX_RETRIES", "7")

        settings = ElasticsearchSettings.from_env()

        assert settings.url == "http://es.internal:9200"
        assert settings.username == "elastic"
        assert settings.password == "s3cret"
        assert settings.timeout == 5.0
        assert settings.max_retries == 7

    def test_blank_values_fall_back_to_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ELASTICSEARCH_URL", "   ")
        monkeypatch.setenv("ELASTICSEARCH_USERNAME", "")
        monkeypatch.setenv("ELASTICSEARCH_PASSWORD", "")
        monkeypatch.setenv("ELASTICSEARCH_TIMEOUT", "")
        monkeypatch.setenv("ELASTICSEARCH_MAX_RETRIES", "  ")

        settings = ElasticsearchSettings.from_env()

        assert settings.url == DEFAULT_URL
        assert settings.username is None
        assert settings.password is None
        assert settings.timeout == DEFAULT_TIMEOUT
        assert settings.max_retries == DEFAULT_MAX_RETRIES


# ---------------------------------------------------------------------------
# Client lifecycle
# ---------------------------------------------------------------------------
class TestClientLifecycle:
    def test_get_client_returns_elasticsearch_instance(self) -> None:
        client = get_client()
        assert isinstance(client, Elasticsearch)

    def test_get_client_returns_the_same_instance_on_repeated_calls(self) -> None:
        first = get_client()
        second = get_client()
        assert first is second

    def test_reset_client_cache_forces_a_new_instance(self) -> None:
        first = get_client()
        reset_client_cache()
        second = get_client()
        assert first is not second


# ---------------------------------------------------------------------------
# Health-check helpers
# ---------------------------------------------------------------------------
class TestHealthHelpers:
    def test_ping_returns_true_when_cluster_responds(self) -> None:
        with patch.object(Elasticsearch, "ping", return_value=True):
            assert ping() is True

    def test_ping_returns_false_when_cluster_is_unreachable(self) -> None:
        with patch.object(Elasticsearch, "ping", side_effect=ConnectionError("refused")):
            assert ping() is False

    def test_cluster_info_returns_client_response(self) -> None:
        payload = {"cluster_name": "test", "version": {"number": "8.15.0"}}
        with patch.object(Elasticsearch, "info", return_value=payload):
            assert cluster_info() == payload

    def test_cluster_info_propagates_failures(self) -> None:
        with (
            patch.object(Elasticsearch, "info", side_effect=ConnectionError("refused")),
            pytest.raises(ConnectionError),
        ):
            cluster_info()
