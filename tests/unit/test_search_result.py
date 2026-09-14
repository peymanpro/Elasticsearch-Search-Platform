"""Unit tests for the domain result value objects."""

from __future__ import annotations

from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchHit, SearchResults


def _hit(doc_id: str, score: float) -> SearchHit:
    return SearchHit(document_id=doc_id, score=score, source={"name": doc_id})


def test_returned_counts_hits_in_this_page() -> None:
    results = SearchResults(
        query=SearchQuery.create("monitor"),
        total=100,
        hits=(_hit("a", 1.0), _hit("b", 0.9)),
    )
    assert results.returned == 2


def test_has_more_is_true_when_total_exceeds_page() -> None:
    results = SearchResults(
        query=SearchQuery.create("monitor", pagination=Pagination(page=1, page_size=2)),
        total=10,
        hits=(_hit("a", 1.0), _hit("b", 0.9)),
    )
    assert results.has_more is True


def test_has_more_is_false_on_last_page() -> None:
    results = SearchResults(
        query=SearchQuery.create("monitor", pagination=Pagination(page=2, page_size=5)),
        total=8,
        hits=tuple(_hit(f"d{i}", 0.5) for i in range(3)),
    )
    assert results.has_more is False


def test_has_more_is_false_when_total_is_zero() -> None:
    results = SearchResults(
        query=SearchQuery.create("nonexistent"),
        total=0,
        hits=(),
    )
    assert results.has_more is False
    assert results.returned == 0
