"""
Search result value objects.

The domain describes a result as: the query that produced it, a total
match count, and an ordered sequence of hits. Each hit carries a document
identifier, a relevance score, and an opaque source mapping.

The source mapping is deliberately opaque at this phase. Its concrete
shape -- the fields of a medical product -- is defined in Phase 4 when the
dataset document model is established. Keeping it opaque here means the
domain package does not need to be modified when that happens.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from apps.search.domain.search_query import SearchQuery


@dataclass(frozen=True, slots=True)
class SearchHit:
    """
    A single matched document.

    Attributes:
        document_id: Stable identifier of the matched document. It is the
            same identifier the document was indexed under, so that later
            phases (explain, highlighting) can refer back to it.
        score: Relevance score assigned by the search engine. The domain
            does not care how it was computed; it only records it.
        source: The document's fields, as a read-only mapping. The domain
            treats this as opaque.
    """

    document_id: str
    score: float
    source: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SearchResults:
    """
    The complete answer to a SearchQuery: a page of hits and the total
    number of matches the query had across the entire index.
    """

    query: SearchQuery
    total: int
    hits: tuple[SearchHit, ...]

    @property
    def returned(self) -> int:
        """Number of hits in this page."""
        return len(self.hits)

    @property
    def has_more(self) -> bool:
        """True if the caller asked for less than the full result set."""
        pagination = self.query.pagination
        return pagination.offset + self.returned < self.total
