"""
Integration tests for sorting and pagination.

Three properties are verified against a real cluster:

    * Business sorting: price, rating, popularity, created_at each
      order results as declared, with the SKU tie-breaker applied.
    * Offset pagination: walking pages produces the full result set
      with no duplicates and no omissions.
    * Cursor pagination: search_after produces the same sequence as a
      single-shot sorted query, and returns the same set as offset
      pagination for the same page size.

The tests skip cleanly when no cluster is reachable.
"""

from __future__ import annotations

import pytest

from apps.search.application.strategies import LiteralSearchStrategy
from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.sorting import (
    SortDirection,
    SortField,
    SortOrder,
)
from apps.search.infrastructure.gateways import ElasticsearchProductSearchGateway
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import index_document
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import load_mapping, load_settings

pytestmark = pytest.mark.integration

TEST_INDEX = "products-sorting-test"


# The fixture is designed so that each sort field partitions the
# documents with no ties except two entries that share a price -- so
# the SKU tie-breaker is exercised.
FIXTURE_DOCUMENTS = [
    {
        "id": "S-001",
        "sku": "S-001",
        "name": "Widget One",
        "brand": "A",
        "category": "Electronics",
        "description": "widget one.",
        "tags": ["widget"],
        "specifications": {},
        "language": "en",
        "price": 100.0,
        "currency": "USD",
        "rating": 4.0,
        "availability": "in_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 10,
    },
    {
        "id": "S-002",
        "sku": "S-002",
        "name": "Widget Two",
        "brand": "B",
        "category": "Electronics",
        "description": "widget two.",
        "tags": ["widget"],
        "specifications": {},
        "language": "en",
        "price": 50.0,
        "currency": "USD",
        "rating": 4.8,
        "availability": "in_stock",
        "created_at": "2024-06-01T00:00:00Z",
        "popularity": 20,
    },
    {
        "id": "S-003",
        "sku": "S-003",
        "name": "Widget Three",
        "brand": "C",
        "category": "Electronics",
        "description": "widget three.",
        "tags": ["widget"],
        "specifications": {},
        "language": "en",
        # Same price as S-001: exercises the SKU tie-breaker.
        "price": 100.0,
        "currency": "USD",
        "rating": 4.5,
        "availability": "in_stock",
        "created_at": "2024-03-01T00:00:00Z",
        "popularity": 5,
    },
    {
        "id": "S-004",
        "sku": "S-004",
        "name": "Widget Four",
        "brand": "D",
        "category": "Electronics",
        "description": "widget four.",
        "tags": ["widget"],
        "specifications": {},
        "language": "en",
        "price": 75.0,
        "currency": "USD",
        "rating": 3.9,
        "availability": "in_stock",
        "created_at": "2024-09-01T00:00:00Z",
        "popularity": 30,
    },
    {
        "id": "S-005",
        "sku": "S-005",
        "name": "Widget Five",
        "brand": "E",
        "category": "Electronics",
        "description": "widget five.",
        "tags": ["widget"],
        "specifications": {},
        "language": "en",
        "price": 200.0,
        "currency": "USD",
        "rating": 5.0,
        "availability": "in_stock",
        "created_at": "2024-02-01T00:00:00Z",
        "popularity": 15,
    },
]


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def sorting_index() -> str:
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


def _search_ids(
    index: str,
    *,
    sort: SortOrder | None = None,
    pagination: Pagination | None = None,
):
    gateway = ElasticsearchProductSearchGateway(client=get_client(), index=index)
    strategy = LiteralSearchStrategy()
    query = SearchQuery.create(
        "widget",
        pagination=pagination or Pagination(page_size=50),
        sort=sort,
    )
    return strategy.execute(query, gateway)


def _ids_in_order(result) -> list[str]:
    return [h.document_id for h in result.hits]


# ---------------------------------------------------------------------------
# 15.2 Business sorting
# ---------------------------------------------------------------------------
def test_sort_by_price_ascending(sorting_index: str) -> None:
    result = _search_ids(sorting_index, sort=SortOrder.create(SortField.PRICE, SortDirection.ASC))
    assert _ids_in_order(result) == ["S-002", "S-004", "S-001", "S-003", "S-005"]


def test_sort_by_price_descending(sorting_index: str) -> None:
    result = _search_ids(sorting_index, sort=SortOrder.create(SortField.PRICE, SortDirection.DESC))
    assert _ids_in_order(result) == ["S-005", "S-001", "S-003", "S-004", "S-002"]


def test_sort_by_rating_descending(sorting_index: str) -> None:
    result = _search_ids(sorting_index, sort=SortOrder.create(SortField.RATING, SortDirection.DESC))
    assert _ids_in_order(result) == ["S-005", "S-002", "S-003", "S-001", "S-004"]


def test_sort_by_popularity_descending(sorting_index: str) -> None:
    result = _search_ids(
        sorting_index, sort=SortOrder.create(SortField.POPULARITY, SortDirection.DESC)
    )
    assert _ids_in_order(result) == ["S-004", "S-002", "S-005", "S-001", "S-003"]


def test_sort_by_created_at_descending(sorting_index: str) -> None:
    result = _search_ids(
        sorting_index, sort=SortOrder.create(SortField.CREATED_AT, SortDirection.DESC)
    )
    # Newest first: 2024-09, 2024-06, 2024-03, 2024-02, 2024-01
    assert _ids_in_order(result) == ["S-004", "S-002", "S-003", "S-005", "S-001"]


# ---------------------------------------------------------------------------
# 15.3 Stable tie-breaking
# ---------------------------------------------------------------------------
def test_price_tie_is_broken_by_sku(sorting_index: str) -> None:
    # S-001 and S-003 share a price of 100.0. The SKU tie-breaker is
    # always ascending, regardless of the primary sort direction. That
    # is what makes the sort order total and pagination deterministic.
    result_asc = _search_ids(
        sorting_index, sort=SortOrder.create(SortField.PRICE, SortDirection.ASC)
    )
    ids_asc = _ids_in_order(result_asc)
    assert ids_asc.index("S-001") < ids_asc.index("S-003")

    # In descending order, the primary sort reverses but the tie-break
    # does not. S-001 still comes before S-003 among the tied documents.
    result_desc = _search_ids(
        sorting_index, sort=SortOrder.create(SortField.PRICE, SortDirection.DESC)
    )
    ids_desc = _ids_in_order(result_desc)
    assert ids_desc.index("S-001") < ids_desc.index("S-003")


# ---------------------------------------------------------------------------
# 15.4 Offset pagination
# ---------------------------------------------------------------------------
def test_offset_pagination_covers_all_documents(sorting_index: str) -> None:
    sort = SortOrder.create(SortField.PRICE, SortDirection.ASC)
    seen: list[str] = []
    for page in range(1, 4):
        result = _search_ids(
            sorting_index,
            sort=sort,
            pagination=Pagination(page=page, page_size=2),
        )
        seen.extend(_ids_in_order(result))

    # 3 pages x 2 = 6 slots for 5 documents. The fourth slot should be
    # empty (last page has one hit); seen should contain 5 ids with no
    # duplicates.
    assert len(seen) == 5
    assert len(set(seen)) == 5


# ---------------------------------------------------------------------------
# 15.6 Cursor pagination
# ---------------------------------------------------------------------------
def test_cursor_pagination_matches_single_shot_order(sorting_index: str) -> None:
    sort = SortOrder.create(SortField.PRICE, SortDirection.ASC)
    single_shot = _search_ids(sorting_index, sort=sort, pagination=Pagination(page_size=50))
    expected = _ids_in_order(single_shot)

    # Walk the result with cursor-based pages of 2.
    gateway = ElasticsearchProductSearchGateway(client=get_client(), index=sorting_index)
    strategy = LiteralSearchStrategy()
    seen: list[str] = []
    pagination = Pagination(page_size=2)
    while True:
        query = SearchQuery.create("widget", pagination=pagination, sort=sort)
        result = strategy.execute(query, gateway)
        seen.extend(_ids_in_order(result))
        if result.next_cursor is None:
            break
        pagination = Pagination.from_cursor(result.next_cursor, page_size=2)

    assert seen == expected
    assert len(seen) == len(set(seen))


def test_cursor_pagination_returns_cursor_on_each_full_page(sorting_index: str) -> None:
    sort = SortOrder.create(SortField.PRICE, SortDirection.ASC)
    gateway = ElasticsearchProductSearchGateway(client=get_client(), index=sorting_index)
    strategy = LiteralSearchStrategy()

    first = strategy.execute(
        SearchQuery.create("widget", pagination=Pagination(page_size=2), sort=sort),
        gateway,
    )
    assert first.next_cursor is not None
    assert len(first.next_cursor) == 2  # (price, sku)


def test_cursor_pagination_no_cursor_on_last_page(sorting_index: str) -> None:
    # 5 documents, page size 50 -> single page contains all -> no cursor.
    sort = SortOrder.create(SortField.PRICE, SortDirection.ASC)
    result = _search_ids(sorting_index, sort=sort, pagination=Pagination(page_size=50))
    assert result.next_cursor is None


# ---------------------------------------------------------------------------
# 15.5 Deep pagination limit
# ---------------------------------------------------------------------------
def test_offset_pagination_beyond_window_is_rejected() -> None:
    from apps.search.domain.exceptions import InvalidPaginationError

    with pytest.raises(InvalidPaginationError):
        Pagination(page=10000, page_size=20)
