"""
Search result value objects.

The domain describes a result as: the query that produced it, a total
match count, an ordered sequence of hits, and (when cursor-based
pagination was requested) the cursor to fetch the next page. Each hit
carries a document identifier, a relevance score, an opaque source
mapping, and an optional mapping of highlight fragments.

The source mapping is deliberately opaque. Its concrete shape -- the
fields of a product -- is defined in docs/09-product-document-model.md.
Keeping it opaque here means the domain package does not need to be
modified when the document model changes.

The highlight fragments and the cursor are also opaque: they are values
produced by the search engine, passed through unchanged. See
docs/18-highlighting.md and docs/20-sorting-pagination.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from apps.search.domain.search_query import SearchQuery


@dataclass(frozen=True, slots=True)
class SearchHit:
    """
    A single matched document.

    Attributes:
        document_id: Stable identifier of the matched document.
        score: Relevance score assigned by the search engine.
        source: The document's fields, as a read-only mapping.
        highlights: A mapping from field name to a tuple of highlighted
            fragments for that field. Fields that did not match are
            absent from the mapping.
    """

    document_id: str
    score: float
    source: Mapping[str, Any]
    highlights: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchResults:
    """
    The complete answer to a SearchQuery: a page of hits, the total
    number of matches, and (optionally) a cursor for the next page.

    Attributes:
        query: The SearchQuery that produced this result.
        total: The total number of matches across the whole index.
        hits: The page of hits.
        next_cursor: When the search was executed with an explicit
            sort and the result set may continue, this is the sort
            values of the last hit on this page. Passing it to
            ``Pagination.from_cursor`` produces the next page. None
            when no next page is known to exist or when the search was
            not cursor-paginated.
    """

    query: SearchQuery
    total: int
    hits: tuple[SearchHit, ...]
    next_cursor: tuple[Any, ...] | None = None

    @property
    def returned(self) -> int:
        """Number of hits in this page."""
        return len(self.hits)

    @property
    def has_more(self) -> bool:
        """
        True if more hits exist beyond this page.

        For offset-based pagination this is derived from total and
        offset. For cursor-based pagination it is True whenever a
        next_cursor is present.
        """
        if self.next_cursor is not None:
            return True
        pagination = self.query.pagination
        if pagination.is_cursor_based:
            return False
        return pagination.offset + self.returned < self.total
