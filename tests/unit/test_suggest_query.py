"""Unit tests for the ``SuggestQuery`` value object."""

from __future__ import annotations

import pytest

from apps.search.domain.suggest_query import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MAX_PREFIX_LENGTH,
    InvalidSuggestQueryError,
    SuggestQuery,
)


def test_default_limit_is_applied() -> None:
    q = SuggestQuery.create("headph")
    assert q.limit == DEFAULT_LIMIT


def test_prefix_is_whitespace_stripped() -> None:
    q = SuggestQuery.create("  headph  ")
    assert q.prefix == "headph"


def test_empty_prefix_is_rejected() -> None:
    with pytest.raises(InvalidSuggestQueryError):
        SuggestQuery.create("")


def test_whitespace_only_prefix_is_rejected() -> None:
    with pytest.raises(InvalidSuggestQueryError):
        SuggestQuery.create("   \t  ")


def test_prefix_at_maximum_length_is_accepted() -> None:
    q = SuggestQuery.create("x" * MAX_PREFIX_LENGTH)
    assert len(q.prefix) == MAX_PREFIX_LENGTH


def test_prefix_beyond_maximum_length_is_rejected() -> None:
    with pytest.raises(InvalidSuggestQueryError):
        SuggestQuery.create("x" * (MAX_PREFIX_LENGTH + 1))


def test_limit_below_minimum_is_rejected() -> None:
    with pytest.raises(InvalidSuggestQueryError):
        SuggestQuery.create("headph", limit=0)


def test_limit_above_maximum_is_rejected() -> None:
    with pytest.raises(InvalidSuggestQueryError):
        SuggestQuery.create("headph", limit=MAX_LIMIT + 1)


def test_suggest_query_is_immutable() -> None:
    from dataclasses import FrozenInstanceError

    q = SuggestQuery.create("headph")
    with pytest.raises(FrozenInstanceError):
        q.prefix = "other"  # type: ignore[misc]
