"""
Search query value object.

Captures what the caller is asking for: the text, the page, and an
optional set of filters. The value object is a pure domain concept --
no Elasticsearch, no HTTP. Sorting is a Phase 15 concern and is not
part of this object.

Filters are represented by the ``ProductFilters`` value object. A
SearchQuery without filters matches everything the text matches; a
SearchQuery with filters matches the intersection. The two are stored
together so that the whole request -- text, page, and narrowing --
travels as one unit through the application layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.search.domain.exceptions import InvalidSearchQueryError
from apps.search.domain.filters import ProductFilters
from apps.search.domain.pagination import Pagination

MIN_QUERY_LENGTH = 1
MAX_QUERY_LENGTH = 500


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """
    A user's textual search request, the page they want, and their
    filters.

    Construction rules:
        * Use ``SearchQuery.create`` rather than the constructor, so that
          whitespace normalization and validation are applied once.
        * ``filters`` defaults to an empty ``ProductFilters``. An empty
          filter set is stored as a real instance rather than as None,
          so consumers never need to distinguish "no filters" from
          "filters object that happens to be empty".
    """

    text: str
    pagination: Pagination
    filters: ProductFilters

    @classmethod
    def create(
        cls,
        text: str,
        pagination: Pagination | None = None,
        filters: ProductFilters | None = None,
    ) -> SearchQuery:
        """
        Build a validated SearchQuery.

        Leading and trailing whitespace is stripped before validation,
        so that a query consisting only of spaces is rejected rather
        than accepted as a one-character string. Filters are stored as
        given, or as a default empty filter set when omitted.
        """
        cleaned = text.strip()

        if len(cleaned) < MIN_QUERY_LENGTH:
            raise InvalidSearchQueryError("search text must not be empty")
        if len(cleaned) > MAX_QUERY_LENGTH:
            raise InvalidSearchQueryError(
                f"search text must be at most {MAX_QUERY_LENGTH} characters, got {len(cleaned)}",
            )

        return cls(
            text=cleaned,
            pagination=pagination or Pagination(),
            filters=filters or ProductFilters.create(),
        )
