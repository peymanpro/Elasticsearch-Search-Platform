"""
Filter clause builder.

Translates a domain ``ProductFilters`` value object into a list of
Elasticsearch filter clauses. The clauses are meant to be added to a
``bool`` query's ``filter`` slot, where they narrow the result set
without contributing to the score.

This module is shared by every query composer (relevance, fuzzy) so that
the mapping from filter dimension to DSL is defined once. See
docs/19-filtering-facets.md section 3.
"""

from __future__ import annotations

from typing import Any

from apps.search.domain.filters import ProductFilters

# Field names used for filtering. These are the exact keyword-typed
# fields the mapping declares. Filtering on a text field would match
# analyzed terms, which is not what a filter means.
FIELD_CATEGORY = "category.keyword"
FIELD_BRAND = "brand.keyword"
FIELD_AVAILABILITY = "availability"
FIELD_PRICE = "price"
FIELD_RATING = "rating"


def build_filter_clauses(filters: ProductFilters) -> list[dict[str, Any]]:
    """
    Return the Elasticsearch filter clauses for a ProductFilters.

    The result is a list of clause dictionaries in a stable order
    (category, brand, availability, price, rating). An empty filter set
    produces an empty list. Each non-None field of the filter set
    produces exactly one clause.
    """
    clauses: list[dict[str, Any]] = []

    if filters.category is not None:
        clauses.append({"term": {FIELD_CATEGORY: filters.category}})

    if filters.brand is not None:
        clauses.append({"term": {FIELD_BRAND: filters.brand}})

    if filters.availability is not None:
        clauses.append({"term": {FIELD_AVAILABILITY: filters.availability}})

    price_body: dict[str, float] = {}
    if filters.price_min is not None:
        price_body["gte"] = filters.price_min
    if filters.price_max is not None:
        price_body["lte"] = filters.price_max
    if price_body:
        clauses.append({"range": {FIELD_PRICE: price_body}})

    rating_body: dict[str, float] = {}
    if filters.rating_min is not None:
        rating_body["gte"] = filters.rating_min
    if filters.rating_max is not None:
        rating_body["lte"] = filters.rating_max
    if rating_body:
        clauses.append({"range": {FIELD_RATING: rating_body}})

    return clauses


__all__ = [
    "FIELD_AVAILABILITY",
    "FIELD_BRAND",
    "FIELD_CATEGORY",
    "FIELD_PRICE",
    "FIELD_RATING",
    "build_filter_clauses",
]
