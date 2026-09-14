"""
Sort clause builder.

Translates a domain ``SortOrder`` value object into an Elasticsearch
sort clause list. Every list ends with a deterministic tie-breaker on
``sku.keyword`` ascending, so that pagination is stable across ties.
See docs/20-sorting-pagination.md sections 2 and 4.
"""

from __future__ import annotations

from typing import Any

from apps.search.domain.sorting import SortField, SortOrder

# SortField -> Elasticsearch field name. SCORE maps to the virtual
# ``_score`` field, which exists only when a query is present.
_SORT_FIELD_NAMES: dict[SortField, str] = {
    SortField.SCORE: "_score",
    SortField.PRICE: "price",
    SortField.RATING: "rating",
    SortField.POPULARITY: "popularity",
    SortField.CREATED_AT: "created_at",
}

# The tie-breaker field. It must be unique so that the sort order is
# total and pagination is deterministic. The SKU is the document _id
# and is therefore unique by construction.
TIE_BREAKER_FIELD = "sku"
TIE_BREAKER_DIRECTION = "asc"


def build_sort_clauses(sort: SortOrder) -> list[dict[str, Any]]:
    """
    Return the Elasticsearch ``sort`` list for a SortOrder.

    The primary sort comes from the SortOrder; the tie-breaker on
    ``sku.keyword`` is always appended. The result is never empty.
    """
    primary_field = _SORT_FIELD_NAMES[sort.field]
    return [
        {primary_field: {"order": sort.direction.value}},
        {TIE_BREAKER_FIELD: {"order": TIE_BREAKER_DIRECTION}},
    ]


__all__ = [
    "TIE_BREAKER_DIRECTION",
    "TIE_BREAKER_FIELD",
    "build_sort_clauses",
]
