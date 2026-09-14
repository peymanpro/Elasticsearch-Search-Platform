"""Unit tests for the SortOrder value object."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from apps.search.domain.sorting import (
    DEFAULT_SORT_ORDER,
    SortDirection,
    SortField,
    SortOrder,
)


def test_default_sort_order_is_score_desc() -> None:
    assert DEFAULT_SORT_ORDER.field is SortField.SCORE
    assert DEFAULT_SORT_ORDER.direction is SortDirection.DESC


def test_score_defaults_to_desc() -> None:
    s = SortOrder.create(SortField.SCORE)
    assert s.direction is SortDirection.DESC


def test_price_defaults_to_asc() -> None:
    s = SortOrder.create(SortField.PRICE)
    assert s.direction is SortDirection.ASC


def test_rating_defaults_to_desc() -> None:
    s = SortOrder.create(SortField.RATING)
    assert s.direction is SortDirection.DESC


def test_created_at_defaults_to_desc() -> None:
    s = SortOrder.create(SortField.CREATED_AT)
    assert s.direction is SortDirection.DESC


def test_explicit_direction_overrides_default() -> None:
    s = SortOrder.create(SortField.PRICE, SortDirection.DESC)
    assert s.direction is SortDirection.DESC


def test_string_field_name_is_accepted() -> None:
    s = SortOrder.create("price", "desc")
    assert s.field is SortField.PRICE
    assert s.direction is SortDirection.DESC


def test_invalid_field_is_rejected() -> None:
    with pytest.raises(ValueError):
        SortOrder.create("description")


def test_invalid_direction_is_rejected() -> None:
    with pytest.raises(ValueError):
        SortOrder.create(SortField.PRICE, "sideways")


def test_sort_order_is_immutable() -> None:
    s = SortOrder.create(SortField.PRICE)
    with pytest.raises(FrozenInstanceError):
        s.direction = SortDirection.DESC  # type: ignore[misc]
