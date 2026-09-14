"""
Integration tests for filtering.

Each filter dimension is exercised against a small fixture catalog
whose documents are chosen so that each dimension partitions the set.
Combined filters are tested for the intersection case.

The tests skip cleanly when no cluster is reachable.
"""

from __future__ import annotations

import pytest

from apps.search.application.strategies import LiteralSearchStrategy
from apps.search.domain.filters import ProductFilters
from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.infrastructure.gateways import ElasticsearchProductSearchGateway
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import index_document
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import load_mapping, load_settings

pytestmark = pytest.mark.integration

TEST_INDEX = "products-filter-test"


FIXTURE_DOCUMENTS = [
    {
        "id": "F-001",
        "sku": "F-001",
        "name": "Wireless Headphones",
        "brand": "Sony",
        "category": "Electronics",
        "description": "A wireless product for audio.",
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
        "id": "F-002",
        "sku": "F-002",
        "name": "Wireless Speaker",
        "brand": "JBL",
        "category": "Electronics",
        "description": "A portable wireless speaker.",
        "tags": ["wireless"],
        "specifications": {"color": "blue"},
        "language": "en",
        "price": 79.95,
        "currency": "USD",
        "rating": 4.2,
        "availability": "out_of_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 200,
    },
    {
        "id": "F-003",
        "sku": "F-003",
        "name": "Wireless Chef Knife",
        "brand": "Wusthof",
        "category": "Home and Kitchen",
        "description": "A wireless kitchen tool.",
        "tags": ["wireless"],
        "specifications": {"color": "silver"},
        "language": "en",
        "price": 149.95,
        "currency": "USD",
        "rating": 4.8,
        "availability": "in_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 300,
    },
    {
        "id": "F-004",
        "sku": "F-004",
        "name": "Budget Wireless Mouse",
        "brand": "Logitech",
        "category": "Electronics",
        "description": "A cheap wireless mouse.",
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
        "id": "F-005",
        "sku": "F-005",
        "name": "Premium Wireless Camera",
        "brand": "Canon",
        "category": "Electronics",
        "description": "A premium wireless camera.",
        "tags": ["wireless"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 1299.00,
        "currency": "USD",
        "rating": 4.9,
        "availability": "in_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 500,
    },
]


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def filter_index() -> str:
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


def _search_ids(index: str, filters: ProductFilters) -> list[str]:
    gateway = ElasticsearchProductSearchGateway(client=get_client(), index=index)
    strategy = LiteralSearchStrategy()
    results = strategy.execute(
        SearchQuery.create("wireless", pagination=Pagination(page_size=50), filters=filters),
        gateway,
    )
    return sorted(hit.document_id for hit in results.hits)


# ---------------------------------------------------------------------------
# 14.1 Category
# ---------------------------------------------------------------------------
def test_category_filter_narrows_to_one_category(filter_index: str) -> None:
    ids = _search_ids(filter_index, ProductFilters.create(category="Electronics"))
    assert ids == ["F-001", "F-002", "F-004", "F-005"]


def test_category_filter_on_home_and_kitchen(filter_index: str) -> None:
    ids = _search_ids(filter_index, ProductFilters.create(category="Home and Kitchen"))
    assert ids == ["F-003"]


# ---------------------------------------------------------------------------
# 14.2 Brand
# ---------------------------------------------------------------------------
def test_brand_filter_returns_only_that_brand(filter_index: str) -> None:
    ids = _search_ids(filter_index, ProductFilters.create(brand="Sony"))
    assert ids == ["F-001"]


def test_brand_filter_with_no_matches(filter_index: str) -> None:
    ids = _search_ids(filter_index, ProductFilters.create(brand="Nonexistent"))
    assert ids == []


# ---------------------------------------------------------------------------
# 14.3 Price
# ---------------------------------------------------------------------------
def test_price_range_filter(filter_index: str) -> None:
    ids = _search_ids(filter_index, ProductFilters.create(price_min=50.0, price_max=200.0))
    assert ids == ["F-002", "F-003"]


def test_price_minimum_only(filter_index: str) -> None:
    ids = _search_ids(filter_index, ProductFilters.create(price_min=300.0))
    assert ids == ["F-001", "F-005"]


def test_price_maximum_only(filter_index: str) -> None:
    ids = _search_ids(filter_index, ProductFilters.create(price_max=50.0))
    assert ids == ["F-004"]


# ---------------------------------------------------------------------------
# 14.4 Rating
# ---------------------------------------------------------------------------
def test_rating_minimum_filter(filter_index: str) -> None:
    ids = _search_ids(filter_index, ProductFilters.create(rating_min=4.5))
    assert ids == ["F-001", "F-003", "F-005"]


def test_rating_range_filter(filter_index: str) -> None:
    ids = _search_ids(filter_index, ProductFilters.create(rating_min=3.5, rating_max=4.5))
    assert ids == ["F-002", "F-004"]


# ---------------------------------------------------------------------------
# 14.5 Availability
# ---------------------------------------------------------------------------
def test_availability_in_stock(filter_index: str) -> None:
    ids = _search_ids(filter_index, ProductFilters.create(availability="in_stock"))
    assert ids == ["F-001", "F-003", "F-004", "F-005"]


def test_availability_out_of_stock(filter_index: str) -> None:
    ids = _search_ids(filter_index, ProductFilters.create(availability="out_of_stock"))
    assert ids == ["F-002"]


# ---------------------------------------------------------------------------
# Combined filters
# ---------------------------------------------------------------------------
def test_combined_category_and_price(filter_index: str) -> None:
    # Electronics AND price <= 200 should produce F-002 and F-004.
    ids = _search_ids(
        filter_index,
        ProductFilters.create(category="Electronics", price_max=200.0),
    )
    assert ids == ["F-002", "F-004"]


def test_combined_category_and_availability(filter_index: str) -> None:
    # Electronics AND out_of_stock should produce F-002.
    ids = _search_ids(
        filter_index,
        ProductFilters.create(category="Electronics", availability="out_of_stock"),
    )
    assert ids == ["F-002"]


def test_combined_filter_with_no_matches(filter_index: str) -> None:
    # Electronics AND Home and Kitchen is an empty intersection.
    ids = _search_ids(
        filter_index,
        ProductFilters.create(category="Electronics", brand="Wusthof"),
    )
    assert ids == []


def test_empty_filters_returns_all_matching(filter_index: str) -> None:
    # No filters should return all five documents that match "wireless".
    ids = _search_ids(filter_index, ProductFilters.create())
    assert len(ids) == 5
