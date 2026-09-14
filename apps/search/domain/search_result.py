"""
Search result value objects.

The domain describes a result as: the query that produced it, a total
match count, and an ordered sequence of hits. Each hit carries a
document identifier, a relevance score, an opaque source mapping, and
an optional mapping of highlight fragments.

The source mapping is deliberately opaque. Its concrete shape -- the
fields of a product -- is defined in docs/09-product-document-model.md.
Keeping it opaque here means the domain package does not need to be
modified when the document model changes.

The highlight fragments are also opaque: they are strings produced by
the search engine, with pre-tags and post-tags already inserted. The
domain does not parse them. See docs/18-highlighting.md.
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
        document_id: Stable identifier of the matched document. It is
            the same identifier the document was indexed under, so that
            later phases (explain, highlighting) can refer back to it.
        score: Relevance score assigned by the search engine. The domain
            does not care how it was computed; it only records it.
        source: The document's fields, as a read-only mapping. The domain
            treats this as opaque.
        highlights: A mapping from field name to a tuple of highlighted
            fragments for that field. Fields that did not match are
            absent from the mapping (not present with an empty tuple).
            An empty mapping means the search returned no highlights at
            all -- which is the case when the gateway did not request
            them or when the query matched nothing for which fragments
            are meaningful. The default is an empty mapping so that
            existing constructions of SearchHit continue to work.
    """

    document_id: str
    score: float
    source: Mapping[str, Any]
    highlights: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


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
