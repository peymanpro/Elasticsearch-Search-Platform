"""Unit tests for the domain value object ``Pagination``."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from apps.search.domain.exceptions import InvalidPaginationError
from apps.search.domain.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Pagination,
)


def test_defaults_are_valid() -> None:
    p = Pagination()
    assert p.page == 1
    assert p.page_size == DEFAULT_PAGE_SIZE


def test_offset_is_zero_for_first_page() -> None:
    assert Pagination(page=1, page_size=20).offset == 0


def test_offset_accumulates_across_pages() -> None:
    assert Pagination(page=1, page_size=10).offset == 0
    assert Pagination(page=2, page_size=10).offset == 10
    assert Pagination(page=5, page_size=20).offset == 80


def test_page_below_minimum_is_rejected() -> None:
    with pytest.raises(InvalidPaginationError):
        Pagination(page=0)


def test_page_size_below_minimum_is_rejected() -> None:
    with pytest.raises(InvalidPaginationError):
        Pagination(page_size=0)


def test_page_size_above_maximum_is_rejected() -> None:
    with pytest.raises(InvalidPaginationError):
        Pagination(page_size=MAX_PAGE_SIZE + 1)


def test_pagination_is_immutable() -> None:
    p = Pagination()
    with pytest.raises(FrozenInstanceError):
        p.page = 2  # type: ignore[misc]
