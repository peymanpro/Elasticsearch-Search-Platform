"""
Product filter value object.

Filters narrow a search result set without changing its text. The
dimensions are the fields that are meaningful to filter on: category,
brand, availability, and the numeric ranges of price and rating.

A ProductFilters with all fields None is equivalent to "no filters";
callers use ``has_any()`` to test whether the filter set is empty
rather than comparing against a sentinel.

Filters are constructed through ``ProductFilters.create`` so that
cross-field invariants (min <= max, rating within range, non-negative
price) are validated once, at construction time. See
docs/19-filtering-facets.md section 3.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.search.domain.exceptions import DomainError

MIN_RATING = 0.0
MAX_RATING = 5.0


class InvalidFiltersError(DomainError):
    """Raised when a filter set violates a domain invariant."""


@dataclass(frozen=True, slots=True)
class ProductFilters:
    """
    A set of optional predicates that narrow a product search.

    Every field is optional. An instance with all fields None is a valid
    filter set that matches everything; callers use ``has_any()`` to
    detect this case rather than constructing a distinct sentinel.

    Attributes:
        category: Exact category name.
        brand: Exact brand name.
        availability: One of the availability enum values.
        price_min: Inclusive lower bound on price.
        price_max: Inclusive upper bound on price.
        rating_min: Inclusive lower bound on rating.
        rating_max: Inclusive upper bound on rating.
    """

    category: str | None = None
    brand: str | None = None
    availability: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    rating_min: float | None = None
    rating_max: float | None = None

    @classmethod
    def create(
        cls,
        *,
        category: str | None = None,
        brand: str | None = None,
        availability: str | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        rating_min: float | None = None,
        rating_max: float | None = None,
    ) -> ProductFilters:
        """
        Build a validated ProductFilters.

        String fields are whitespace-stripped; a field that is empty or
        whitespace-only is treated as absent. Numeric fields are checked
        for internal consistency (min <= max) and for their respective
        domains (non-negative price, rating in [0, 5]).
        """
        category = _clean_str(category)
        brand = _clean_str(brand)
        availability = _clean_str(availability)

        _check_non_negative("price_min", price_min)
        _check_non_negative("price_max", price_max)
        _check_range_consistency("price", price_min, price_max)
        _check_rating("rating_min", rating_min)
        _check_rating("rating_max", rating_max)
        _check_range_consistency("rating", rating_min, rating_max)

        return cls(
            category=category,
            brand=brand,
            availability=availability,
            price_min=price_min,
            price_max=price_max,
            rating_min=rating_min,
            rating_max=rating_max,
        )

    def has_any(self) -> bool:
        """Return True if at least one filter is set."""
        return any(
            value is not None
            for value in (
                self.category,
                self.brand,
                self.availability,
                self.price_min,
                self.price_max,
                self.rating_min,
                self.rating_max,
            )
        )


def _clean_str(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _check_non_negative(name: str, value: float | None) -> None:
    if value is not None and value < 0:
        raise InvalidFiltersError(f"{name} must be >= 0, got {value}")


def _check_rating(name: str, value: float | None) -> None:
    if value is not None and (value < MIN_RATING or value > MAX_RATING):
        raise InvalidFiltersError(
            f"{name} must be between {MIN_RATING} and {MAX_RATING}, got {value}"
        )


def _check_range_consistency(
    name: str,
    low: float | None,
    high: float | None,
) -> None:
    if low is not None and high is not None and low > high:
        raise InvalidFiltersError(f"{name}_min must not exceed {name}_max: {low} > {high}")


__all__ = [
    "MAX_RATING",
    "MIN_RATING",
    "InvalidFiltersError",
    "ProductFilters",
]
