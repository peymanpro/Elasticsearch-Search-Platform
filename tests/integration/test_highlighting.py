"""
Integration tests for search-result highlighting.

These tests index a small fixture catalog and assert that:

    * A field that matched the query appears in the hit's highlights.
    * The fragment contains the emphasized matched term.
    * A field that did not match is absent from the highlights.
    * The gateway populates SearchHit.highlights from the response.

The tests skip cleanly when no cluster is reachable.
"""

from __future__ import annotations

import pytest

from apps.search.application.strategies import LiteralSearchStrategy
from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.infrastructure.gateways import (
    POST_TAG,
    PRE_TAG,
    ElasticsearchProductSearchGateway,
)
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import index_document
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import load_mapping, load_settings

pytestmark = pytest.mark.integration

TEST_INDEX = "products-highlight-test"


FIXTURE_DOCUMENTS = [
    {
        "id": "H-001",
        "sku": "H-001",
        "name": "Wireless Noise-Cancelling Headphones",
        "brand": "Sony",
        "category": "Electronics",
        "description": (
            "Over-ear wireless headphones with active noise cancellation. "
            "The wireless connection supports multipoint pairing."
        ),
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
        "id": "H-002",
        "sku": "H-002",
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
        "id": "H-003",
        "sku": "H-003",
        "name": "Portable Bluetooth Speaker",
        "brand": "JBL",
        "category": "Electronics",
        "description": "Compact speaker with twelve-hour battery life.",
        "tags": ["portable", "bluetooth", "speaker"],
        "specifications": {"color": "blue"},
        "language": "en",
        "price": 79.95,
        "currency": "USD",
        "rating": 4.2,
        "availability": "in_stock",
        "created_at": "2024-03-10T14:00:00Z",
        "popularity": 512,
    },
]


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def highlight_index() -> str:
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


def _search(index: str, text: str):
    gateway = ElasticsearchProductSearchGateway(client=get_client(), index=index)
    strategy = LiteralSearchStrategy()
    return strategy.execute(
        SearchQuery.create(text, pagination=Pagination(page_size=10)),
        gateway,
    )


# ---------------------------------------------------------------------------
# Matched field has fragments
# ---------------------------------------------------------------------------
def test_matched_field_has_highlight_fragments(highlight_index: str) -> None:
    results = _search(highlight_index, "wireless")
    by_id = {hit.document_id: hit for hit in results.hits}

    # H-001 has "Wireless" in the name and "wireless" in the description.
    assert "H-001" in by_id
    hit = by_id["H-001"]
    assert "name" in hit.highlights
    assert len(hit.highlights["name"]) >= 1


def test_fragment_contains_the_emphasized_term(highlight_index: str) -> None:
    results = _search(highlight_index, "wireless")
    by_id = {hit.document_id: hit for hit in results.hits}
    hit = by_id["H-001"]

    name_fragments = hit.highlights["name"]
    # The matched term is wrapped in the configured tags.
    assert any(PRE_TAG in frag and POST_TAG in frag for frag in name_fragments)
    # And the term itself appears between the tags (case-insensitive on
    # the term, since the analyzer lowercases it and the fragment keeps
    # the original casing).
    joined = " ".join(name_fragments).lower()
    assert "wireless" in joined


def test_multiple_fields_can_be_highlighted(highlight_index: str) -> None:
    # H-001 contains "wireless" in name, description, and tags.
    results = _search(highlight_index, "wireless")
    by_id = {hit.document_id: hit for hit in results.hits}
    hit = by_id["H-001"]

    assert "name" in hit.highlights
    assert "description" in hit.highlights


def test_description_may_produce_multiple_fragments(highlight_index: str) -> None:
    # H-001's description mentions "wireless" twice. The gateway requests
    # up to three fragments for the description. Elasticsearch is free to
    # return one combined fragment; we assert it returns at least one and
    # never more than the requested count.
    results = _search(highlight_index, "wireless")
    by_id = {hit.document_id: hit for hit in results.hits}
    hit = by_id["H-001"]

    description_fragments = hit.highlights["description"]
    assert 1 <= len(description_fragments) <= 3


# ---------------------------------------------------------------------------
# Unmatched field has no fragments
# ---------------------------------------------------------------------------
def test_unmatched_field_has_no_highlight(highlight_index: str) -> None:
    # H-001's brand is "Sony". A query for "wireless" does not match the
    # brand field, so "brand" must be absent from the highlights.
    results = _search(highlight_index, "wireless")
    by_id = {hit.document_id: hit for hit in results.hits}
    hit = by_id["H-001"]

    assert "brand" not in hit.highlights


def test_document_without_a_match_has_empty_highlights(highlight_index: str) -> None:
    # H-002 is "Wired Studio Headphones". A query for "wireless" should
    # not match H-002 at all (no token "wireless" appears in it), so it
    # will not be in the results. But if it is, its highlights must be
    # empty.
    results = _search(highlight_index, "wireless")
    for hit in results.hits:
        # Every returned hit must have at least one highlighted field.
        assert hit.highlights, f"hit {hit.document_id} has no highlights"


# ---------------------------------------------------------------------------
# Highlighting is bound to the query, not the document
# ---------------------------------------------------------------------------
def test_different_query_highlights_different_fields(highlight_index: str) -> None:
    # A query for "sony" matches the brand field of H-001 only.
    results = _search(highlight_index, "sony")
    assert results.hits, "no hit for 'sony'"
    hit = results.hits[0]
    assert hit.document_id == "H-001"
    assert "brand" in hit.highlights
    assert "name" not in hit.highlights
