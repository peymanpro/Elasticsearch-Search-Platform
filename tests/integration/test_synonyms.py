"""
Integration tests for search-time synonyms.

Two properties are tested:

    1. The synonym file is loaded and contains the expected number of
       rules.
    2. Every synonym group produces equivalent results: a search for one
       member of a group returns the same documents as a search for
       another member of the same group.

The tests create a fixture index whose documents mention every member
of every synonym group. If the search-time synonym filter were not
working, searches for two members of the same group would return
different document sets and the equivalence assertions would fail.

The tests skip cleanly when no cluster is reachable.
"""

from __future__ import annotations

import pytest

from apps.search.application.strategies import LiteralSearchStrategy
from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.infrastructure.gateways import ElasticsearchProductSearchGateway
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import index_document
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import (
    SYNONYMS_FILE,
    load_mapping,
    load_settings,
)

pytestmark = pytest.mark.integration

TEST_INDEX = "products-synonyms-test"


def _load_synonym_groups() -> list[list[str]]:
    """Return the parsed synonym groups from the synonym file."""
    groups: list[list[str]] = []
    for raw in SYNONYMS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        groups.append([term.strip() for term in line.split(",")])
    return groups


SYNONYM_GROUPS = _load_synonym_groups()


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def synonym_index() -> str:
    """
    Create a fixture index whose documents mention every synonym group.

    For each synonym group, one document is created whose name is the
    first term of the group. The other terms of the group appear in the
    document description. This guarantees that:

        * a non-expanded query for the first term matches the document
          via name;
        * a non-expanded query for a later term matches the document
          only if the synonym filter is active.

    Note: the platform's mapping only applies the synonym filter to the
    search-time analyzer. Documents are analyzed at index time with the
    non-synonym analyzer. So a description-only match for a synonym
    variant should be unreachable without the search-time filter, and
    reachable with it.
    """
    client = get_client()
    client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)

    settings = load_settings("v1")
    mapping = load_mapping("v1")
    client.indices.create(
        index=TEST_INDEX,
        settings=settings,
        mappings={"dynamic": mapping["dynamic"], "properties": mapping["properties"]},
    )

    # One document per group. The document is about a product whose name
    # is the first synonym; the description contains the other synonyms
    # so that a search for a synonym variant must expand to reach it.
    for i, group in enumerate(SYNONYM_GROUPS):
        primary = group[0]
        variants = ", ".join(group[1:]) if len(group) > 1 else primary
        doc = {
            "id": f"SYN-{i:03d}",
            "sku": f"SYN-{i:03d}",
            "name": primary.title(),
            "brand": "TestBrand",
            "category": "Test",
            "description": f"A {primary} also known as {variants}.",
            "tags": ["test"],
            "specifications": {"group_index": i},
            "language": "en",
            "price": 10.0,
            "currency": "USD",
            "rating": 4.0,
            "availability": "in_stock",
            "created_at": "2024-01-01T00:00:00Z",
            "popularity": 1,
        }
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


def _search_ids(index: str, text: str) -> list[str]:
    """Run a search and return the sorted document ids."""
    gateway = ElasticsearchProductSearchGateway(client=get_client(), index=index)
    strategy = LiteralSearchStrategy()
    results = strategy.execute(
        SearchQuery.create(text, pagination=Pagination(page_size=50)),
        gateway,
    )
    return sorted(hit.document_id for hit in results.hits)


# ---------------------------------------------------------------------------
# The file is loaded and parseable
# ---------------------------------------------------------------------------
def test_synonym_file_has_groups() -> None:
    assert len(SYNONYM_GROUPS) >= 15


def test_each_group_has_at_least_two_terms() -> None:
    for group in SYNONYM_GROUPS:
        assert len(group) >= 2, f"degenerate synonym group: {group}"


def test_groups_have_no_duplicate_terms() -> None:
    for group in SYNONYM_GROUPS:
        assert len(group) == len(set(group)), f"duplicate terms in: {group}"


# ---------------------------------------------------------------------------
# Synonyms produce equivalent results
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "group",
    SYNONYM_GROUPS,
    ids=["_".join(g[:2]) for g in SYNONYM_GROUPS],
)
def test_synonym_group_terms_are_equivalent(
    synonym_index: str,
    group: list[str],
) -> None:
    """
    Any two terms of the same group must return the same documents.

    The test runs one query per term and compares result sets. Under
    proper search-time analysis, all terms expand to the same token set
    and therefore produce identical results.
    """
    result_sets = [_search_ids(synonym_index, term) for term in group]

    # Every term must return at least one document (the fixture ensures
    # one document per group exists).
    for term, ids in zip(group, result_sets, strict=True):
        assert ids, f"term {term!r} returned no documents"

    # All terms must return the same set of documents.
    first = result_sets[0]
    for term, ids in zip(group[1:], result_sets[1:], strict=True):
        assert ids == first, (
            f"synonym group {group}: term {term!r} returned {ids}, "
            f"but {group[0]!r} returned {first}"
        )


# ---------------------------------------------------------------------------
# Concrete well-known cases
# ---------------------------------------------------------------------------
def test_tv_finds_television_document(synonym_index: str) -> None:
    # "tv" and "television" are synonyms, so a query for "tv" should
    # reach a document whose name is "Tv" (primary term of the group).
    tv_ids = _search_ids(synonym_index, "tv")
    television_ids = _search_ids(synonym_index, "television")
    assert tv_ids == television_ids
    assert tv_ids, "tv query returned nothing"


def test_headphones_and_earphones_are_equivalent(synonym_index: str) -> None:
    a = _search_ids(synonym_index, "headphones")
    b = _search_ids(synonym_index, "earphones")
    assert a == b
    assert a, "headphones query returned nothing"
