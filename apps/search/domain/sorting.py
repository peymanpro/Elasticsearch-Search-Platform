"""
Sort order value object.

Expresses the field and direction of a result-set sort. The set of
sortable fields is closed: the enum declares exactly the fields the
product model marks as sortable, and no others. A caller cannot sort
by an arbitrary field, both because some fields would be expensive to
sort on (a high-cardinality keyword, a long text field) and because
the platform's policy is to expose only the sorts it has designed.

The default is ``(SCORE, DESC)`` -- relevance order. See
docs/20-sorting-pagination.md section 5.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SortField(StrEnum):
    """
    Fields a caller may sort by.

    SCORE is a virtual field: it maps to Elasticsearch's ``_score``
    and is only meaningful when a query is present. The other fields
    are the ones the product model marks as ``SORTABLE_FIELDS``.
    """

    SCORE = "score"
    PRICE = "price"
    RATING = "rating"
    POPULARITY = "popularity"
    CREATED_AT = "created_at"


class SortDirection(StrEnum):
    """Direction of a sort."""

    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True, slots=True)
class SortOrder:
    """
    A field and a direction, describing one sort clause.

    Instances are constructed through ``SortOrder.create`` so that the
    field's natural default direction can be applied when the caller
    does not specify one.
    """

    field: SortField
    direction: SortDirection

    @classmethod
    def create(
        cls,
        field: SortField | str = SortField.SCORE,
        direction: SortDirection | str | None = None,
    ) -> SortOrder:
        """
        Build a SortOrder.

        When ``direction`` is omitted, the field's natural default is
        applied:

            SCORE       DESC  (higher score first)
            PRICE       ASC   (cheapest first)
            RATING      DESC  (highest rated first)
            POPULARITY  DESC  (most popular first)
            CREATED_AT  DESC  (newest first)

        These defaults are what a user expects from each field. The
        caller may override with an explicit direction.
        """
        resolved_field = field if isinstance(field, SortField) else SortField(field)
        if direction is None:
            resolved_direction = _DEFAULT_DIRECTIONS[resolved_field]
        else:
            resolved_direction = (
                direction if isinstance(direction, SortDirection) else SortDirection(direction)
            )
        return cls(field=resolved_field, direction=resolved_direction)


_DEFAULT_DIRECTIONS: dict[SortField, SortDirection] = {
    SortField.SCORE: SortDirection.DESC,
    SortField.PRICE: SortDirection.ASC,
    SortField.RATING: SortDirection.DESC,
    SortField.POPULARITY: SortDirection.DESC,
    SortField.CREATED_AT: SortDirection.DESC,
}


DEFAULT_SORT_ORDER = SortOrder(field=SortField.SCORE, direction=SortDirection.DESC)


__all__ = [
    "DEFAULT_SORT_ORDER",
    "SortDirection",
    "SortField",
    "SortOrder",
]
