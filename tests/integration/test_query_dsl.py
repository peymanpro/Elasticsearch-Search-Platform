"""
Integration tests for the Elasticsearch query DSL surface.

These tests exercise each DSL feature the platform uses -- match,
multi_match, match_phrase, term, range, and bool composition --
against a live index loaded with a small fixture dataset. They are
the executable form of the Phase 8 design: if a query type is
claimed to work, one of these tests proves it.

The tests are marked as integration and skip cleanly when no cluster
is reachable.
"""

from __future__ import annotations

import pytest

from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import index_document
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import load_mapping, load_settings
from infrastructure.elasticsearch.query.builder import QueryBuilder
from infrastructure.elasticsearch.query.clauses import (
    MatchClause,
    MatchPhraseClause,
    MultiMatchClause,
    RangeClause,
    TermClause,
)

pytestmark = pytest.mark.integration

TEST_INDEX = "products-dsl-test"


FIXTURE_DOCUMENTS = [
    {
        "id": "T-001",
        "sku": "T-001",
        "name": "Wireless Noise-Cancelling Headphones",
        "brand": "Sony",
        "category": "Electronics",
        "description": "Over-ear wireless headphones with active noise cancellation.",
        "tags": ["wireless", "bluetooth", "noise-cancelling"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 349.99,
        "currency": "USD",
        "rating": 4.6,
        "availability": "in_stock",
        "created_at": "2024-09-15T10:30:00Z",
        "popularity": 842,
    },
    {
        "id": "T-002",
        "sku": "T-002",
        "name": "Wired Studio Headphones",
        "brand": "Audio-Technica",
        "category": "Electronics",
        "description": "Wired over-ear studio monitoring headphones.",
        "tags": ["wired", "studio", "monitoring"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 149.00,
        "currency": "USD",
        "rating": 4.4,
        "availability": "in_stock",
        "created_at": "2024-05-01T08:00:00Z",
        "popularity": 320,
    },
    {
        "id": "T-003",
        "sku": "T-003",
        "name": "Portable Bluetooth Speaker",
        "brand": "JBL",
        "category": "Electronics",
        "description": "Compact portable bluetooth speaker with 12-hour battery.",
        "tags": ["portable", "bluetooth", "speaker"],
        "specifications": {"color": "blue"},
        "language": "en",
        "price": 79.95,
        "currency": "USD",
        "rating": 4.2,
        "availability": "out_of_stock",
        "created_at": "2024-03-10T14:00:00Z",
        "popularity": 512,
    },
    {
        "id": "T-004",
        "sku": "T-004",
        "name": "Stainless Steel Chef Knife",
        "brand": "Wusthof",
        "category": "Home and Kitchen",
        "description": "Forged 8-inch chef knife with full tang.",
        "tags": ["kitchen", "knife", "chef"],
        "specifications": {"color": "silver"},
        "language": "en",
        "price": 149.95,
        "currency": "USD",
        "rating": 4.8,
        "availability": "in_stock",
        "created_at": "2024-08-02T14:00:00Z",
        "popularity": 315,
    },
    {
        "id": "T-005",
        "sku": "T-005",
        "name": "Yoga Mat Non-Slip 6mm",
        "brand": "Manduka",
        "category": "Sports",
        "description": "6mm non-slip yoga mat with closed-cell surface.",
        "tags": ["yoga", "mat", "fitness"],
        "specifications": {"color": "blue"},
        "language": "en",
        "price": 88.00,
        "currency": "USD",
        "rating": 4.7,
        "availability": "in_stock",
        "created_at": "2024-01-25T07:45:00Z",
        "popularity": 1056,
    },
]


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def dsl_index() -> str:
    """Create a temporary index with the products mapping and fixture docs."""
    client = get_client()
    client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)

    settings = load_settings("v1")
    mapping = load_mapping("v1")
    client.indices.create(
        index=TEST_INDEX,
        settings=settings,
        mappings={"dynamic": mapping["dynamic"], "properties": mapping["properties"]},
    )

    for doc in FIXTURE_DOCUMENTS:
        index_document(
            index=TEST_INDEX,
            document_id=doc["id"],
            source=doc,
            refresh=False,
        )
    client.indices.refresh(index=TEST_INDEX)

    try:
        yield TEST_INDEX
    finally:
        client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


def _search(index: str, query: dict, size: int = 10) -> list[str]:
    """Run a query and return the ids of the matching documents."""
    response = get_client().search(index=index, query=query, size=size)
    return sorted(hit["_id"] for hit in response["hits"]["hits"])


# ---------------------------------------------------------------------------
# 8.1 Match query
# ---------------------------------------------------------------------------
def test_match_query_finds_documents_by_one_field(dsl_index: str) -> None:
    query = QueryBuilder().must(MatchClause(field="name", value="headphones")).build()
    ids = _search(dsl_index, query)
    assert ids == ["T-001", "T-002"]


def test_match_query_analyzes_its_input(dsl_index: str) -> None:
    # Case of the query does not matter because the analyzer lowercases.
    lower = QueryBuilder().must(MatchClause(field="name", value="headphones")).build()
    upper = QueryBuilder().must(MatchClause(field="name", value="HEADPHONES")).build()
    assert _search(dsl_index, lower) == _search(dsl_index, upper)


# ---------------------------------------------------------------------------
# 8.2 Multi match
# ---------------------------------------------------------------------------
def test_multi_match_searches_several_fields(dsl_index: str) -> None:
    # "wusthof" appears only in the brand field of T-004. If multi_match
    # were only searching name, it would find nothing.
    query = QueryBuilder().must(MultiMatchClause(fields=("name", "brand"), value="wusthof")).build()
    ids = _search(dsl_index, query)
    assert ids == ["T-004"]


# ---------------------------------------------------------------------------
# 8.4 Must (mandatory clause)
# ---------------------------------------------------------------------------
def test_must_clause_requires_every_clause_to_match(dsl_index: str) -> None:
    query = (
        QueryBuilder()
        .must(MatchClause(field="name", value="headphones"))
        .must(TermClause(field="category.keyword", value="Electronics"))
        .build()
    )
    ids = _search(dsl_index, query)
    assert ids == ["T-001", "T-002"]


# ---------------------------------------------------------------------------
# 8.5 Should (optional, contributes to score)
# ---------------------------------------------------------------------------
def test_should_clause_boosts_score_without_being_required(dsl_index: str) -> None:
    query = (
        QueryBuilder()
        .must(MatchClause(field="category", value="electronics"))
        .should(MatchClause(field="brand", value="sony"))
        .minimum_should_match(0)
        .build()
    )
    response = get_client().search(index=dsl_index, query=query, size=10)
    by_id = {h["_id"]: h["_score"] for h in response["hits"]["hits"]}
    # All three Electronics docs match the must clause; only T-001
    # additionally matches the should clause, so its score is higher.
    assert by_id["T-001"] > by_id["T-002"]
    assert by_id["T-001"] > by_id["T-003"]


# ---------------------------------------------------------------------------
# 8.6 Filter (exact, no scoring)
# ---------------------------------------------------------------------------
def test_filter_clause_narrows_results(dsl_index: str) -> None:
    query = QueryBuilder().filter(TermClause(field="category.keyword", value="Electronics")).build()
    ids = _search(dsl_index, query)
    assert ids == ["T-001", "T-002", "T-003"]


# ---------------------------------------------------------------------------
# 8.7 Must not (exclusion)
# ---------------------------------------------------------------------------
def test_must_not_clause_excludes_documents(dsl_index: str) -> None:
    query = (
        QueryBuilder()
        .filter(TermClause(field="category.keyword", value="Electronics"))
        .must_not(TermClause(field="brand.keyword", value="Sony"))
        .build()
    )
    ids = _search(dsl_index, query)
    assert ids == ["T-002", "T-003"]


# ---------------------------------------------------------------------------
# 8.8 Match phrase
# ---------------------------------------------------------------------------
def test_match_phrase_requires_the_words_in_order(dsl_index: str) -> None:
    # "stainless steel" is adjacent in T-004's name.
    in_order = QueryBuilder().must(MatchPhraseClause(field="name", value="stainless steel")).build()
    reversed_order = (
        QueryBuilder().must(MatchPhraseClause(field="name", value="steel stainless")).build()
    )
    assert _search(dsl_index, in_order) == ["T-004"]
    assert _search(dsl_index, reversed_order) == []


def test_match_phrase_does_not_match_a_single_word(dsl_index: str) -> None:
    # A phrase query must see all its tokens in the document.
    query = QueryBuilder().must(MatchPhraseClause(field="name", value="headphones studio")).build()
    assert _search(dsl_index, query) == []


# ---------------------------------------------------------------------------
# 8.9 Term (exact, no analysis)
# ---------------------------------------------------------------------------
def test_term_query_matches_the_exact_keyword(dsl_index: str) -> None:
    query = QueryBuilder().filter(TermClause(field="availability", value="out_of_stock")).build()
    ids = _search(dsl_index, query)
    assert ids == ["T-003"]


def test_term_query_does_not_analyze_its_input(dsl_index: str) -> None:
    # The keyword field stores "Sony" exactly. A term query with
    # "sony" would match the analyzed brand field but not the keyword.
    exact = QueryBuilder().filter(TermClause(field="brand.keyword", value="Sony")).build()
    wrong_case = QueryBuilder().filter(TermClause(field="brand.keyword", value="sony")).build()
    assert _search(dsl_index, exact) == ["T-001"]
    assert _search(dsl_index, wrong_case) == []


# ---------------------------------------------------------------------------
# 8.10 Range
# ---------------------------------------------------------------------------
def test_range_query_on_price(dsl_index: str) -> None:
    query = QueryBuilder().filter(RangeClause(field="price", gte=100.0, lte=200.0)).build()
    ids = _search(dsl_index, query)
    assert ids == ["T-002", "T-004"]


def test_range_query_with_only_lower_bound(dsl_index: str) -> None:
    query = QueryBuilder().filter(RangeClause(field="price", gte=200.0)).build()
    ids = _search(dsl_index, query)
    assert ids == ["T-001"]


def test_range_query_on_rating(dsl_index: str) -> None:
    query = QueryBuilder().filter(RangeClause(field="rating", gte=4.7)).build()
    ids = _search(dsl_index, query)
    assert ids == ["T-004", "T-005"]


# ---------------------------------------------------------------------------
# Combined clauses
# ---------------------------------------------------------------------------
def test_combined_must_filter_and_range(dsl_index: str) -> None:
    # "wireless" is in T-001's description; T-003's description says
    # "bluetooth" but not "wireless", so this combination isolates T-001.
    query = (
        QueryBuilder()
        .must(MatchClause(field="description", value="wireless"))
        .filter(TermClause(field="availability", value="in_stock"))
        .filter(RangeClause(field="price", lte=400.0))
        .build()
    )
    ids = _search(dsl_index, query)
    assert ids == ["T-001"]


def test_a_query_matching_no_documents_returns_empty(dsl_index: str) -> None:
    query = QueryBuilder().must(MatchClause(field="name", value="nonexistent")).build()
    assert _search(dsl_index, query) == []
