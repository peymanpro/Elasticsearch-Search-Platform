"""
Integration tests for faceting.

These tests index a fixture catalog and assert that:

    * Each facet carries the expected bucket values.
    * Bucket counts are consistent with the fixture.
    * Filters change the facet counts (the counts reflect the current
      filtered result set).
    * A search without matches returns empty facets.

The tests skip cleanly when no cluster is reachable.
"""

from __future__ import annotations

import pytest

from apps.search.application.search_with_facets import SearchWithFacetsUseCase
from apps.search.domain.filters import ProductFilters
from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.infrastructure.gateways import ElasticsearchFacetGateway
from apps.search.infrastructure.relevance import RelevanceQueryBuilder
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import index_document
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import load_mapping, load_settings

pytestmark = pytest.mark.integration

TEST_INDEX = "products-facet-test"


FIXTURE_DOCUMENTS = [
    {
        "id": "G-001",
        "sku": "G-001",
        "name": "Wireless Headphones",
        "brand": "Sony",
        "category": "Electronics",
        "description": "A wireless product.",
        "tags": ["wireless"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 349.99,
        "currency": "USD",
        "rating": 4.6,
        "availability": "in_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 100,
    },
    {
        "id": "G-002",
        "sku": "G-002",
        "name": "Wireless Speaker",
        "brand": "JBL",
        "category": "Electronics",
        "description": "A wireless speaker.",
        "tags": ["wireless"],
        "specifications": {"color": "blue"},
        "language": "en",
        "price": 79.95,
        "currency": "USD",
        "rating": 4.2,
        "availability": "in_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 200,
    },
    {
        "id": "G-003",
        "sku": "G-003",
        "name": "Wireless Knife",
        "brand": "Wusthof",
        "category": "Home and Kitchen",
        "description": "A wireless kitchen tool.",
        "tags": ["wireless"],
        "specifications": {"color": "silver"},
        "language": "en",
        "price": 149.95,
        "currency": "USD",
        "rating": 4.8,
        "availability": "out_of_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 300,
    },
    {
        "id": "G-004",
        "sku": "G-004",
        "name": "Wireless Mouse",
        "brand": "Logitech",
        "category": "Electronics",
        "description": "A wireless mouse.",
        "tags": ["wireless"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 29.99,
        "currency": "USD",
        "rating": 3.8,
        "availability": "in_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 400,
    },
    {
        "id": "G-005",
        "sku": "G-005",
        "name": "Wireless Camera",
        "brand": "Canon",
        "category": "Electronics",
        "description": "A premium wireless camera.",
        "tags": ["wireless"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 1299.00,
        "currency": "USD",
        "rating": 4.9,
        "availability": "preorder",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 500,
    },
]


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def facet_index() -> str:
    client = get_client()
    client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)

    settings = load_settings("v2")
    mapping = load_mapping("v2")
    client.indices.create(
        index=TEST_INDEX,
        settings=settings,
        mappings={"dynamic": mapping["dynamic"], "properties": mapping["properties"]},
    )

    for doc in FIXTURE_DOCUMENTS:
        index_document(index=TEST_INDEX, document_id=doc["id"], source=doc)
    client.indices.refresh(index=TEST_INDEX)

    try:
        yield TEST_INDEX
    finally:
        client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


def _search(index: str, text: str, filters: ProductFilters | None = None):
    gateway = ElasticsearchFacetGateway(client=get_client(), index=index)
    composer = RelevanceQueryBuilder()
    use_case = SearchWithFacetsUseCase(gateway=gateway, composer=composer)
    query = SearchQuery.create(
        text,
        pagination=Pagination(page_size=50),
        filters=filters,
    )
    return use_case.execute(query)


def _bucket_map(buckets) -> dict[str, int]:
    return {b.value: b.count for b in buckets}


# ---------------------------------------------------------------------------
# Category facet
# ---------------------------------------------------------------------------
def test_category_facet_has_expected_buckets(facet_index: str) -> None:
    result = _search(facet_index, "wireless")
    counts = _bucket_map(result.facets.categories)
    assert counts.get("Electronics") == 4
    assert counts.get("Home and Kitchen") == 1


# ---------------------------------------------------------------------------
# Brand facet
# ---------------------------------------------------------------------------
def test_brand_facet_has_expected_buckets(facet_index: str) -> None:
    result = _search(facet_index, "wireless")
    counts = _bucket_map(result.facets.brands)
    assert counts.get("Sony") == 1
    assert counts.get("JBL") == 1
    assert counts.get("Wusthof") == 1
    assert counts.get("Logitech") == 1
    assert counts.get("Canon") == 1


# ---------------------------------------------------------------------------
# Availability facet
# ---------------------------------------------------------------------------
def test_availability_facet_counts_each_state(facet_index: str) -> None:
    result = _search(facet_index, "wireless")
    counts = _bucket_map(result.facets.availability)
    assert counts.get("in_stock") == 3
    assert counts.get("out_of_stock") == 1
    assert counts.get("preorder") == 1


# ---------------------------------------------------------------------------
# Price range facet
# ---------------------------------------------------------------------------
def test_price_range_facet_has_expected_buckets(facet_index: str) -> None:
    result = _search(facet_index, "wireless")
    counts = _bucket_map(result.facets.price_ranges)
    # Price bands: 0-50, 50-100, 100-250, 250-500, 500+.
    # G-004 (29.99) -> 0-50
    # G-002 (79.95) -> 50-100
    # G-003 (149.95) -> 100-250
    # G-001 (349.99) -> 250-500
    # G-005 (1299.00) -> 500+
    assert counts.get("0-50") == 1
    assert counts.get("50-100") == 1
    assert counts.get("100-250") == 1
    assert counts.get("250-500") == 1
    assert counts.get("500+") == 1


# ---------------------------------------------------------------------------
# Filter changes the counts
# ---------------------------------------------------------------------------
def test_filter_narrows_the_facet_counts(facet_index: str) -> None:
    # Without filter: category facet has Electronics=4, Home and Kitchen=1.
    unfiltered = _search(facet_index, "wireless")
    assert _bucket_map(unfiltered.facets.categories).get("Electronics") == 4

    # With category=Electronics: only Electronics documents remain, so the
    # category facet should still show Electronics=4 but no Home and Kitchen.
    filtered = _search(
        facet_index,
        "wireless",
        filters=ProductFilters.create(category="Electronics"),
    )
    counts = _bucket_map(filtered.facets.categories)
    assert counts.get("Electronics") == 4
    assert "Home and Kitchen" not in counts


def test_filter_also_narrows_the_hits(facet_index: str) -> None:
    unfiltered = _search(facet_index, "wireless")
    assert unfiltered.search.total == 5

    filtered = _search(
        facet_index,
        "wireless",
        filters=ProductFilters.create(category="Electronics"),
    )
    assert filtered.search.total == 4


# ---------------------------------------------------------------------------
# Combined behavior
# ---------------------------------------------------------------------------
def test_search_returns_both_hits_and_facets(facet_index: str) -> None:
    result = _search(facet_index, "wireless")
    assert result.search.hits
    assert result.facets.categories
    assert result.facets.brands
    assert result.facets.availability
    assert result.facets.price_ranges


def test_no_matching_documents_returns_empty_facets(facet_index: str) -> None:
    result = _search(facet_index, "zxqwerty")
    assert result.search.total == 0
    assert result.facets.is_empty is True
