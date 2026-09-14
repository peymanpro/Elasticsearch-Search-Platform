"""
Search query value object.

Captures what the caller is asking for. Filters, sorting, and other
refinements are intentionally absent at Phase 2.3: they will be added in
the phases that introduce them (filters in Phase 14, sorting in Phase 15).
The value object is a pure domain concept -- no Elasticsearch, no HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.search.domain.exceptions import InvalidSearchQueryError
from apps.search.domain.pagination import Pagination

MIN_QUERY_LENGTH = 1
MAX_QUERY_LENGTH = 500


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """
    A user's textual search request plus the page they want.

    Construction rules:
        * Use ``SearchQuery.create`` rather than the constructor, so that
          whitespace normalization and validation are applied once.
    """

    text: str
    pagination: Pagination

    @classmethod
    def create(
        cls,
        text: str,
        pagination: Pagination | None = None,
    ) -> SearchQuery:
        """
        Build a validated SearchQuery.

        Leading and trailing whitespace is stripped before validation, so
        that a query consisting only of spaces is rejected rather than
        accepted as a one-character string.
        """
        cleaned = text.strip()

        if len(cleaned) < MIN_QUERY_LENGTH:
            raise InvalidSearchQueryError("search text must not be empty")
        if len(cleaned) > MAX_QUERY_LENGTH:
            raise InvalidSearchQueryError(
                f"search text must be at most {MAX_QUERY_LENGTH} characters, got {len(cleaned)}",
            )

        return cls(text=cleaned, pagination=pagination or Pagination())
