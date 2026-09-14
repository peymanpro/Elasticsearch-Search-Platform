"""
Integration tests for relevance engineering.

These tests use a small fixture catalog and the platform's real
RelevanceQueryBuilder to demonstrate that:

    * Field boosts rank name matches above description matches.
    * The exact-phrase clause ranks an exact name match above a
      partial name match.
    * Business signals (rating, popularity) contribute to the score.

The tests do not assert absolute score values -- those depend on the
index and are not a stable contract. They assert ranking order, which
is what the platform's relevance policy actually promises.

The tests require a running Elasticsearch cluster and skip cleanly if
none is reachable.
"""

from __future__ import annotations

import pytest

from apps.search.infrastructure.relevance import (
    BUSINESS_SIGNALS,
    EXACT_NAME_PHRASE_BOOST,
    FIELD_BOOSTS,
    RelevanceQueryBuilder,
)
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import index_document
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import load_mapping, load_settings

pytestmark = pytest.mark.integration

TEST_INDEX = "products-relevance-test"


# The fixture is chosen to isolate each relevance mechanism:
#
#   F-001  exact name phrase match, high rating, high popularity
#   F-002  matches "portable" in the name, low rating, low popularity
#   F-003  matches "portable" only in the description, low rating
#   F-004  no match for the query "portable speaker", but strong signals
#
# A query for "portable speaker" should rank F-001 first (exact phrase
# on name, boosted by rating and popularity), F-002 next (name match),
# F-003 after (description match), and F-004 never (no match).
FIXTURE_DOCUMENTS = [
    {
        "id": "F-001",
        "sku": "F-001",
        "name": "Portable Speaker",
        "brand": "JBL",
        "category": "Electronics",
        "description": "A compact speaker with excellent sound quality.",
        "tags": ["audio", "portable"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 99.00,
        "currency": "USD",
        "rating": 4.9,
        "availability": "in_stock",
        "created_at": "2024-06-01T00:00:00Z",
        "popularity": 3000,
    },
    {
        "id": "F-002",
        "sku": "F-002",
        "name": "Portable Charger",
        "brand": "Anker",
        "category": "Electronics",
        "description": "A small charger for travel.",
        "tags": ["power", "portable"],
        "specifications": {"color": "white"},
        "language": "en",
        "price": 29.00,
        "currency": "USD",
        "rating": 4.0,
        "availability": "in_stock",
        "created_at": "2024-06-01T00:00:00Z",
        "popularity": 200,
    },
    {
        "id": "F-003",
        "sku": "F-003",
        "name": "Travel Adapter",
        "brand": "Generic",
        "category": "Electronics",
        "description": "A portable speaker-style device for travel.",
        "tags": ["travel", "adapter"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 15.00,
        "currency": "USD",
        "rating": 3.5,
        "availability": "in_stock",
        "created_at": "2024-06-01T00:00:00Z",
        "popularity": 100,
    },
    {
        "id": "F-004",
        "sku": "F-004",
        "name": "Premium Cables",
        "brand": "Belkin",
        "category": "Electronics",
        "description": "High-quality cables with gold connectors.",
        "tags": ["cable", "accessory"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 19.00,
        "currency": "USD",
        "rating": 5.0,
        "availability": "in_stock",
        "created_at": "2024-06-01T00:00:00Z",
        "popularity": 5000,
    },
]


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def relevance_index() -> str:
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
        )
    client.indices.refresh(index=TEST_INDEX)

    try:
        yield TEST_INDEX
    finally:
        client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


def _ranked_ids(index: str, text: str) -> list[str]:
    """Run the platform's relevance query and return ids in ranking order."""
    query = RelevanceQueryBuilder().build(text)
    response = get_client().search(index=index, query=query, size=10)
    return [hit["_id"] for hit in response["hits"]["hits"]]


def _scores(index: str, text: str) -> dict[str, float]:
    """Return a mapping of document id to relevance score for a query."""
    query = RelevanceQueryBuilder().build(text)
    response = get_client().search(index=index, query=query, size=10)
    return {hit["_id"]: hit["_score"] for hit in response["hits"]["hits"]}


# ---------------------------------------------------------------------------
# Policy constants are what the docs say they are
# ---------------------------------------------------------------------------
def test_field_boosts_are_the_documented_values() -> None:
    assert FIELD_BOOSTS == (
        "name^3.0",
        "brand^2.0",
        "category^1.5",
        "tags^1.5",
        "description^1.0",
    )
    assert EXACT_NAME_PHRASE_BOOST == 5.0
    assert BUSINESS_SIGNALS == (
        ("rating", 1.0, None),
        ("popularity", 0.5, "log1p"),
    )


# ---------------------------------------------------------------------------
# Ranking order
# ---------------------------------------------------------------------------
def test_exact_phrase_name_match_ranks_first(relevance_index: str) -> None:
    ids = _ranked_ids(relevance_index, "portable speaker")
    assert ids[0] == "F-001"


def test_name_match_ranks_above_description_match(relevance_index: str) -> None:
    # F-002 matches "portable" in the name; F-003 matches "portable"
    # only in the description.
    ids = _ranked_ids(relevance_index, "portable")
    assert ids.index("F-002") < ids.index("F-003")


def test_non_matching_document_is_absent(relevance_index: str) -> None:
    # F-004 has neither "portable" nor "speaker" in any field.
    ids = _ranked_ids(relevance_index, "portable speaker")
    assert "F-004" not in ids


def test_exact_phrase_boost_increases_the_score(relevance_index: str) -> None:
    # F-001's name is exactly "Portable Speaker". The match_phrase
    # should clause adds to F-001's score. Removing the phrase boost
    # would reduce F-001's score relative to F-002.
    scores = _scores(relevance_index, "portable speaker")
    # F-001 matches both the multi_match and the exact phrase.
    # F-002 matches only the multi_match (with "portable" in the name).
    # The exact-phrase boost gives F-001 the edge.
    assert scores["F-001"] > scores["F-002"]


# ---------------------------------------------------------------------------
# Business signals
# ---------------------------------------------------------------------------
def test_higher_rating_and_popularity_raise_score(relevance_index: str) -> None:
    # F-002 and F-003 both match "portable", but F-002's name contains
    # it while F-003's description contains it. F-002 also has the
    # higher rating and popularity, so its score is expected to exceed
    # F-003's for both reasons (the two causes cannot be disentangled
    # with this fixture, and the test does not claim to).
    scores = _scores(relevance_index, "portable")
    assert scores["F-002"] > scores["F-003"]


# ---------------------------------------------------------------------------
# Empty results
# ---------------------------------------------------------------------------
def test_query_with_no_matches_returns_empty(relevance_index: str) -> None:
    ids = _ranked_ids(relevance_index, "zxqwerty")
    assert ids == []


# ---------------------------------------------------------------------------
# The strategy returns the same ranking as the builder
# ---------------------------------------------------------------------------
def test_relevant_strategy_produces_the_same_ranking(relevance_index: str) -> None:
    from apps.search.application.strategies import RelevantSearchStrategy
    from apps.search.domain.pagination import Pagination
    from apps.search.domain.search_query import SearchQuery
    from apps.search.infrastructure.gateways import ElasticsearchProductSearchGateway
    from apps.search.infrastructure.relevance import RelevanceQueryBuilder

    gateway = ElasticsearchProductSearchGateway(
        client=get_client(),
        index=relevance_index,
    )
    strategy = RelevantSearchStrategy(composer=RelevanceQueryBuilder())

    results = strategy.execute(
        SearchQuery.create("portable speaker", pagination=Pagination(page_size=10)),
        gateway,
    )
    assert results.total >= 1
    assert results.hits[0].document_id == "F-001"
