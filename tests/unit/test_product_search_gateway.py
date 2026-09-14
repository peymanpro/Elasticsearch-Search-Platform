"""
Unit tests for the Elasticsearch product search gateway adapter.

A recording fake client stands in for Elasticsearch, so the tests
exercise:

    * the DSL the adapter builds (via the Phase 3.6 builder),
    * the pagination it passes through,
    * the way it translates an Elasticsearch response into domain types.

No Elasticsearch instance is contacted. Integration coverage against the
real cluster arrives when an index exists (Phase 17 and Phase 21).
"""

from __future__ import annotations

from typing import Any

from apps.search.domain.pagination import Pagination
from apps.search.domain.search_result import SearchResults
from apps.search.domain.strategies import ProductSearchGateway
from apps.search.infrastructure.gateways import ElasticsearchProductSearchGateway


class _FakeElasticsearchClient:
    """Records the arguments to ``search`` and returns a canned response."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self._response


def _empty_response() -> dict[str, Any]:
    return {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}}


def _response_with_hits(hits: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    if total is None:
        total = len(hits)
    return {"hits": {"total": {"value": total, "relation": "eq"}, "hits": hits}}


# ---------------------------------------------------------------------------
# Contract conformance
# ---------------------------------------------------------------------------
def test_gateway_satisfies_product_search_gateway_protocol() -> None:
    gateway = ElasticsearchProductSearchGateway(
        client=_FakeElasticsearchClient(_empty_response()),
        index="products",
    )
    assert isinstance(gateway, ProductSearchGateway)


# ---------------------------------------------------------------------------
# Request translation
# ---------------------------------------------------------------------------
def test_gateway_sends_a_match_clause_on_the_search_field() -> None:
    client = _FakeElasticsearchClient(_empty_response())
    gateway = ElasticsearchProductSearchGateway(client=client, index="products")

    gateway.search(text="monitor", pagination=Pagination())

    call = client.calls[0]
    assert call["index"] == "products"
    assert call["query"] == {"bool": {"must": [{"match": {"name": "monitor"}}]}}


def test_gateway_uses_configured_search_field() -> None:
    client = _FakeElasticsearchClient(_empty_response())
    gateway = ElasticsearchProductSearchGateway(
        client=client, index="products", search_field="description"
    )

    gateway.search(text="portable", pagination=Pagination())

    assert client.calls[0]["query"] == {"bool": {"must": [{"match": {"description": "portable"}}]}}


def test_gateway_translates_pagination_to_from_and_size() -> None:
    client = _FakeElasticsearchClient(_empty_response())
    gateway = ElasticsearchProductSearchGateway(client=client, index="products")

    gateway.search(text="x", pagination=Pagination(page=3, page_size=15))

    assert client.calls[0]["from_"] == 30
    assert client.calls[0]["size"] == 15


# ---------------------------------------------------------------------------
# Response translation
# ---------------------------------------------------------------------------
def test_gateway_translates_hits_into_search_hits() -> None:
    client = _FakeElasticsearchClient(
        _response_with_hits(
            [
                {"_id": "1001", "_score": 4.5, "_source": {"name": "Patient Monitor"}},
                {"_id": "1002", "_score": 3.2, "_source": {"name": "ECG Monitor"}},
            ],
            total=42,
        )
    )
    gateway = ElasticsearchProductSearchGateway(client=client, index="products")

    results = gateway.search(text="monitor", pagination=Pagination())

    assert isinstance(results, SearchResults)
    assert results.total == 42
    assert results.returned == 2
    assert results.hits[0].document_id == "1001"
    assert results.hits[0].score == 4.5
    assert results.hits[0].source == {"name": "Patient Monitor"}
    assert results.hits[1].document_id == "1002"


def test_gateway_handles_empty_result_set() -> None:
    client = _FakeElasticsearchClient(_empty_response())
    gateway = ElasticsearchProductSearchGateway(client=client, index="products")

    results = gateway.search(text="nonexistent", pagination=Pagination())

    assert results.total == 0
    assert results.returned == 0
    assert results.hits == ()


def test_gateway_handles_missing_score_field() -> None:
    client = _FakeElasticsearchClient(_response_with_hits([{"_id": "1", "_source": {"name": "x"}}]))
    gateway = ElasticsearchProductSearchGateway(client=client, index="products")

    results = gateway.search(text="x", pagination=Pagination())

    assert results.hits[0].score == 0.0


def test_gateway_preserves_the_query_that_produced_the_results() -> None:
    client = _FakeElasticsearchClient(_empty_response())
    gateway = ElasticsearchProductSearchGateway(client=client, index="products")

    results = gateway.search(text="monitor", pagination=Pagination(page=2, page_size=5))

    assert results.query.text == "monitor"
    assert results.query.pagination.page == 2
    assert results.query.pagination.page_size == 5
