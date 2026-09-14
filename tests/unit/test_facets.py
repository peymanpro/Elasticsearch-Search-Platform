"""Unit tests for the facet value objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from apps.search.domain.facets import (
    FacetBucket,
    FacetedSearchResults,
    FacetResults,
)
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchHit, SearchResults


def _empty_search() -> SearchResults:
    return SearchResults(query=SearchQuery.create("test"), total=0, hits=())


def _empty_facets() -> FacetResults:
    return FacetResults(categories=(), brands=(), availability=(), price_ranges=())


# ---------------------------------------------------------------------------
# FacetBucket
# ---------------------------------------------------------------------------
def test_facet_bucket_holds_value_and_count() -> None:
    b = FacetBucket(value="Sony", count=12)
    assert b.value == "Sony"
    assert b.count == 12


def test_facet_bucket_is_immutable() -> None:
    b = FacetBucket(value="Sony", count=12)
    with pytest.raises(FrozenInstanceError):
        b.count = 20  # type: ignore[misc]


def test_facet_buckets_are_hashable() -> None:
    b1 = FacetBucket(value="Sony", count=12)
    b2 = FacetBucket(value="Sony", count=12)
    # Equal values are the same hash and can be used in sets.
    assert hash(b1) == hash(b2)
    assert {b1, b2} == {b1}


# ---------------------------------------------------------------------------
# FacetResults
# ---------------------------------------------------------------------------
def test_empty_facet_results_is_empty() -> None:
    assert _empty_facets().is_empty is True


def test_non_empty_facet_results_is_not_empty() -> None:
    f = FacetResults(
        categories=(FacetBucket("Electronics", 5),),
        brands=(),
        availability=(),
        price_ranges=(),
    )
    assert f.is_empty is False


def test_facet_buckets_preserve_declared_order() -> None:
    buckets = (
        FacetBucket("Sony", 12),
        FacetBucket("JBL", 8),
        FacetBucket("Anker", 5),
    )
    f = FacetResults(categories=(), brands=buckets, availability=(), price_ranges=())
    # The tuple preserves the order it was given, which is the order
    # Elasticsearch returned (by count descending).
    assert f.brands == buckets


# ---------------------------------------------------------------------------
# FacetedSearchResults
# ---------------------------------------------------------------------------
def test_faceted_search_results_carries_both_parts() -> None:
    search = _empty_search()
    facets = _empty_facets()
    combined = FacetedSearchResults(search=search, facets=facets)
    assert combined.search is search
    assert combined.facets is facets


def test_faceted_search_results_is_immutable() -> None:
    combined = FacetedSearchResults(search=_empty_search(), facets=_empty_facets())
    with pytest.raises(FrozenInstanceError):
        combined.search = _empty_search()  # type: ignore[misc]


def test_faceted_search_results_carries_search_hits() -> None:
    hit = SearchHit(document_id="X", score=1.0, source={"name": "Widget"})
    search = SearchResults(
        query=SearchQuery.create("widget"),
        total=1,
        hits=(hit,),
    )
    facets = FacetResults(
        categories=(FacetBucket("Widgets", 1),),
        brands=(),
        availability=(),
        price_ranges=(),
    )
    combined = FacetedSearchResults(search=search, facets=facets)
    assert combined.search.returned == 1
    assert combined.search.hits[0].document_id == "X"
    assert combined.facets.categories[0].value == "Widgets"


def test_facet_results_with_only_zero_count_buckets_is_empty() -> None:
    """
    A range aggregation returns all declared bands even when no document
    matches. FacetResults with only zero-count buckets is effectively
    empty for display purposes.
    """
    f = FacetResults(
        categories=(),
        brands=(),
        availability=(),
        price_ranges=(
            FacetBucket("0-50", 0),
            FacetBucket("50-100", 0),
            FacetBucket("100-250", 0),
        ),
    )
    assert f.is_empty is True


def test_facet_results_with_any_positive_count_is_not_empty() -> None:
    f = FacetResults(
        categories=(),
        brands=(),
        availability=(),
        price_ranges=(
            FacetBucket("0-50", 0),
            FacetBucket("50-100", 3),
            FacetBucket("100-250", 0),
        ),
    )
    assert f.is_empty is False
