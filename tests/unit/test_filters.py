"""Unit tests for the ``ProductFilters`` value object."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from apps.search.domain.filters import (
    MAX_RATING,
    InvalidFiltersError,
    ProductFilters,
)


def test_empty_filters_have_no_predicates() -> None:
    f = ProductFilters.create()
    assert f.has_any() is False


def test_single_filter_has_predicate() -> None:
    f = ProductFilters.create(category="Electronics")
    assert f.has_any() is True
    assert f.category == "Electronics"


def test_string_fields_are_whitespace_stripped() -> None:
    f = ProductFilters.create(category="  Electronics  ", brand=" Sony ")
    assert f.category == "Electronics"
    assert f.brand == "Sony"


def test_whitespace_only_string_becomes_none() -> None:
    f = ProductFilters.create(category="   ")
    assert f.category is None
    assert f.has_any() is False


def test_price_range_is_accepted() -> None:
    f = ProductFilters.create(price_min=10.0, price_max=100.0)
    assert f.price_min == 10.0
    assert f.price_max == 100.0


def test_negative_price_is_rejected() -> None:
    with pytest.raises(InvalidFiltersError):
        ProductFilters.create(price_min=-1.0)


def test_price_min_greater_than_max_is_rejected() -> None:
    with pytest.raises(InvalidFiltersError):
        ProductFilters.create(price_min=100.0, price_max=10.0)


def test_rating_range_is_accepted() -> None:
    f = ProductFilters.create(rating_min=3.5, rating_max=4.5)
    assert f.rating_min == 3.5
    assert f.rating_max == 4.5


def test_rating_below_minimum_is_rejected() -> None:
    with pytest.raises(InvalidFiltersError):
        ProductFilters.create(rating_min=-0.5)


def test_rating_above_maximum_is_rejected() -> None:
    with pytest.raises(InvalidFiltersError):
        ProductFilters.create(rating_max=MAX_RATING + 0.5)


def test_rating_min_greater_than_max_is_rejected() -> None:
    with pytest.raises(InvalidFiltersError):
        ProductFilters.create(rating_min=4.0, rating_max=3.0)


def test_filters_are_immutable() -> None:
    f = ProductFilters.create(category="Electronics")
    with pytest.raises(FrozenInstanceError):
        f.category = "Books"  # type: ignore[misc]


def test_all_dimensions_can_be_set_together() -> None:
    f = ProductFilters.create(
        category="Electronics",
        brand="Sony",
        availability="in_stock",
        price_min=100.0,
        price_max=500.0,
        rating_min=4.0,
        rating_max=5.0,
    )
    assert f.has_any()
    assert f.category == "Electronics"
    assert f.brand == "Sony"
    assert f.availability == "in_stock"
