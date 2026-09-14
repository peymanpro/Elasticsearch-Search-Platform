"""Unit tests for the domain value object ``SearchQuery``."""

from __future__ import annotations

import pytest

from apps.search.domain.exceptions import InvalidSearchQueryError
from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import MAX_QUERY_LENGTH, SearchQuery


def test_create_strips_surrounding_whitespace() -> None:
    q = SearchQuery.create("  patient monitor  ")
    assert q.text == "patient monitor"


def test_create_uses_default_pagination_when_none_supplied() -> None:
    q = SearchQuery.create("monitor")
    assert q.pagination.page == 1
    assert q.pagination.page_size == Pagination().page_size


def test_create_accepts_explicit_pagination() -> None:
    q = SearchQuery.create("monitor", pagination=Pagination(page=3, page_size=5))
    assert q.pagination.page == 3
    assert q.pagination.page_size == 5


def test_empty_text_is_rejected() -> None:
    with pytest.raises(InvalidSearchQueryError):
        SearchQuery.create("")


def test_whitespace_only_text_is_rejected() -> None:
    with pytest.raises(InvalidSearchQueryError):
        SearchQuery.create("   \t\n  ")


def test_text_at_maximum_length_is_accepted() -> None:
    q = SearchQuery.create("a" * MAX_QUERY_LENGTH)
    assert len(q.text) == MAX_QUERY_LENGTH


def test_text_beyond_maximum_length_is_rejected() -> None:
    with pytest.raises(InvalidSearchQueryError):
        SearchQuery.create("a" * (MAX_QUERY_LENGTH + 1))
