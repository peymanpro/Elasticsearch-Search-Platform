"""
Integration tests for failure handling.

These tests exercise the platform's behavior when Elasticsearch is
unreachable, times out, or is missing the index the platform targets.
They complement the happy-path tests: a search platform that returns
results when everything works is table stakes; one that returns a
shaped, diagnosable error when it does not is the difference between
an operational system and a fragile one.

The tests use mocks at the boundary of the Elasticsearch client (not
at the boundary of the use case) so that every layer between the view
and the client is exercised.

The tests require the DRF test client; they do not require a running
Elasticsearch for the unreachable and timeout cases. The missing-index
case is real and requires a cluster.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from elastic_transport import ConnectionError as TransportConnectionError
from elastic_transport import ConnectionTimeout
from rest_framework.test import APIClient

from elasticsearch import Elasticsearch
from infrastructure.elasticsearch.health import ping


# ---------------------------------------------------------------------------
# Cluster unreachable
# ---------------------------------------------------------------------------
class TestClusterUnreachable:
    """Behavior when the search backend is not reachable at all."""

    def test_health_reports_unhealthy_when_cluster_is_down(self) -> None:
        with patch(
            "infrastructure.elasticsearch.health.get_client",
            side_effect=TransportConnectionError("connection refused"),
        ):
            client = APIClient()
            response = client.get("/api/health/")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "unhealthy"
        assert body["cluster"]["status"] == "unreachable"
        assert body["index"]["points_at"] is None
        assert body["index"]["document_count"] == 0

    def test_service_root_reports_degraded_when_cluster_is_down(self) -> None:
        # Service-root uses the health probe; when the probe fails, the
        # status is degraded, not healthy.
        with patch(
            "infrastructure.elasticsearch.health.get_client",
            side_effect=TransportConnectionError("connection refused"),
        ):
            client = APIClient()
            response = client.get("/")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"


# ---------------------------------------------------------------------------
# Search endpoints: transport failures produce shaped errors
# ---------------------------------------------------------------------------
class TestSearchBackendFailures:
    """
    Every search endpoint returns a shaped 503 or 504 on backend failure.

    The adapters receive an injected ``Elasticsearch`` client; they do
    not call ``get_client`` themselves. The correct way to make a call
    fail is therefore to patch the client's method (``search`` or
    ``explain``), which is where the adapters actually reach out.
    """

    def test_search_returns_503_when_client_raises_connection_error(self) -> None:
        with patch.object(
            Elasticsearch,
            "search",
            side_effect=TransportConnectionError("refused"),
        ):
            response = APIClient().post(
                "/api/search/",
                {"query": "wireless"},
                format="json",
            )

        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "backend_unavailable"
        assert "message" in body["error"]

    def test_search_returns_504_on_connection_timeout(self) -> None:
        with patch.object(
            Elasticsearch,
            "search",
            side_effect=ConnectionTimeout("timeout"),
        ):
            response = APIClient().post(
                "/api/search/",
                {"query": "wireless"},
                format="json",
            )

        assert response.status_code == 504
        body = response.json()
        assert body["error"]["code"] == "backend_timeout"

    def test_suggest_returns_503_when_client_raises_connection_error(self) -> None:
        with patch.object(
            Elasticsearch,
            "search",
            side_effect=TransportConnectionError("refused"),
        ):
            response = APIClient().get("/api/suggest/?q=wire")

        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "backend_unavailable"

    def test_explain_returns_503_when_client_raises_connection_error(self) -> None:
        with patch.object(
            Elasticsearch,
            "explain",
            side_effect=TransportConnectionError("refused"),
        ):
            response = APIClient().post(
                "/api/explain/",
                {"query": "wireless", "document_id": "SKU-1001"},
                format="json",
            )

        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "backend_unavailable"


# ---------------------------------------------------------------------------
# Domain errors from the API layer
# ---------------------------------------------------------------------------
class TestDomainErrorsAreShaped:
    """Domain validation errors are translated to the shaped 400 body."""

    def test_search_page_zero_produces_shaped_error(self) -> None:
        response = APIClient().post(
            "/api/search/",
            {"query": "wireless", "page": 0},
            format="json",
        )
        assert response.status_code == 400
        body = response.json()
        # DRF's ValidationError is now wrapped; the shape carries the
        # code the caller branches on.
        assert "error" in body
        assert body["error"]["code"] == "invalid_request"

    def test_missing_required_field_produces_shaped_error(self) -> None:
        response = APIClient().post("/api/search/", {}, format="json")
        assert response.status_code == 400
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "invalid_request"


# ---------------------------------------------------------------------------
# Missing index (requires a live cluster)
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestMissingIndex:
    """Behavior when the alias the platform targets does not resolve."""

    @pytest.fixture(scope="class", autouse=True)
    def _require_cluster(self) -> None:
        if not ping():
            pytest.skip("Elasticsearch is not reachable.")

    def test_search_against_nonexistent_index_returns_503(self) -> None:
        # Patch the composition root to point the search gateway at a
        # physical index that does not exist. The gateway's search call
        # will produce an Elasticsearch NotFoundError, which the
        # exception handler translates to 503.
        from apps.search.infrastructure.gateways import (
            ElasticsearchProductSearchGateway,
        )

        def _build_missing_index_gateway():
            from apps.search.application.search_products import SearchProductsUseCase
            from apps.search.infrastructure.relevance import RelevanceQueryBuilder

            gateway = ElasticsearchProductSearchGateway(
                client=__import__(
                    "infrastructure.elasticsearch.client", fromlist=["get_client"]
                ).get_client(),
                index="products-does-not-exist-at-all",
            )
            return SearchProductsUseCase(
                gateway=gateway,
                relevance_composer=RelevanceQueryBuilder(),
            )

        with patch(
            "apps.search.presentation.views.build_search_products_use_case",
            _build_missing_index_gateway,
        ):
            response = APIClient().post(
                "/api/search/",
                {"query": "wireless"},
                format="json",
            )

        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "backend_unavailable"
