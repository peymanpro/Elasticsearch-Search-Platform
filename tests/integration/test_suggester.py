"""
Integration tests for the Elasticsearch product suggester.

These tests create a v2 index (the version that carries the
``name_suggest`` field), load a small fixture catalog, and exercise the
``bool_prefix`` query through the ``ElasticsearchProductSuggester``
adapter.

The fixture documents include both ``name`` and ``name_suggest`` set to
the same value. In production the ``name_suggest`` field would be fed
by ``copy_to`` from ``name``; the fixture is explicit so the tests do
not depend on that mechanism being wired yet. See docs/17-autocomplete.md.

The tests skip cleanly when no cluster is reachable.
"""

from __future__ import annotations

import pytest

from apps.search.domain.suggest_query import SuggestQuery
from apps.search.infrastructure.suggester import ElasticsearchProductSuggester
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import index_document
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import load_mapping, load_settings

pytestmark = pytest.mark.integration

TEST_INDEX = "products-suggest-test"


FIXTURE_DOCUMENTS = [
    {
        "id": "S-001",
        "sku": "S-001",
        "name": "Wireless Noise-Cancelling Headphones",
        "name_suggest": "Wireless Noise-Cancelling Headphones",
        "brand": "Sony",
        "category": "Electronics",
        "description": "Over-ear wireless headphones.",
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
        "id": "S-002",
        "sku": "S-002",
        "name": "Wireless Mouse",
        "name_suggest": "Wireless Mouse",
        "brand": "Logitech",
        "category": "Electronics",
        "description": "A wireless mouse.",
        "tags": ["wireless"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 29.99,
        "currency": "USD",
        "rating": 4.4,
        "availability": "in_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 200,
    },
    {
        "id": "S-003",
        "sku": "S-003",
        "name": "Wired Studio Headphones",
        "name_suggest": "Wired Studio Headphones",
        "brand": "Audio-Technica",
        "category": "Electronics",
        "description": "Wired studio monitor headphones.",
        "tags": ["studio"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 149.00,
        "currency": "USD",
        "rating": 4.5,
        "availability": "in_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 150,
    },
    {
        "id": "S-004",
        "sku": "S-004",
        "name": "Portable Bluetooth Speaker",
        "name_suggest": "Portable Bluetooth Speaker",
        "brand": "JBL",
        "category": "Electronics",
        "description": "A portable speaker.",
        "tags": ["portable"],
        "specifications": {"color": "blue"},
        "language": "en",
        "price": 79.95,
        "currency": "USD",
        "rating": 4.2,
        "availability": "in_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 300,
    },
]


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def suggest_index() -> str:
    """Create a v2 index and load the fixture documents."""
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


def _suggest(index: str, prefix: str, limit: int = 5) -> tuple[str, ...]:
    """Run the suggester for a prefix and return the result tuple."""
    adapter = ElasticsearchProductSuggester(client=get_client(), index=index)
    return adapter.suggest(SuggestQuery.create(prefix, limit=limit))


# ---------------------------------------------------------------------------
# Basic prefix matching
# ---------------------------------------------------------------------------
def test_single_word_prefix_matches(suggest_index: str) -> None:
    results = _suggest(suggest_index, "wire")
    assert any("Wireless" in r for r in results) or any("Wired" in r for r in results)


def test_prefix_on_first_word_returns_full_name(suggest_index: str) -> None:
    results = _suggest(suggest_index, "wirel")
    assert "Wireless Noise-Cancelling Headphones" in results
    assert "Wireless Mouse" in results


def test_multi_word_prefix_matches(suggest_index: str) -> None:
    # "wireless noi" should match the first document via the 2-gram path.
    results = _suggest(suggest_index, "wireless noi")
    assert "Wireless Noise-Cancelling Headphones" in results


def test_prefix_matching_a_word_inside_the_name(suggest_index: str) -> None:
    # "studio" is not the first word of any name but is present in
    # "Wired Studio Headphones". search_as_you_type matches across
    # the whole name, not only the first token.
    results = _suggest(suggest_index, "studio")
    assert "Wired Studio Headphones" in results


# ---------------------------------------------------------------------------
# Limit and deduplication
# ---------------------------------------------------------------------------
def test_limit_is_respected(suggest_index: str) -> None:
    results = _suggest(suggest_index, "wire", limit=1)
    assert len(results) <= 1


def test_results_are_deduplicated(suggest_index: str) -> None:
    results = _suggest(suggest_index, "wireless")
    # No duplicate suggestion strings.
    assert len(results) == len(set(results))


# ---------------------------------------------------------------------------
# Non-matching and edge cases
# ---------------------------------------------------------------------------
def test_no_matches_returns_empty(suggest_index: str) -> None:
    results = _suggest(suggest_index, "zxqwerty")
    assert results == ()


def test_case_does_not_affect_matching(suggest_index: str) -> None:
    lower = _suggest(suggest_index, "wireless")
    upper = _suggest(suggest_index, "WIRELESS")
    assert lower == upper
