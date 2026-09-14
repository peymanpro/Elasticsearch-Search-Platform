"""
Concrete search execution strategies.

Four strategies exist as of Phase 10:

    LiteralSearchStrategy       -- text passed verbatim
    NormalizedSearchStrategy    -- text lowercased and whitespace-collapsed
    RelevantSearchStrategy      -- relevance-weighted query, composed by a
                                   RelevanceQueryComposer
    FuzzySearchStrategy         -- typo-tolerant query, composed by a
                                   FuzzyQueryComposer

Later phases add further strategies in this module (Phase 11 synonym,
Phase 12 autocomplete). Adding a strategy does not require modifying the
use case, the selector, the domain contracts, or any existing strategy.

The relevance and fuzzy strategies depend on domain Protocols, not on
concrete composers. The composition root wires the concrete
implementations.
"""

from __future__ import annotations

from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchResults
from apps.search.domain.strategies import (
    FuzzyQueryComposer,
    ProductSearchGateway,
    RelevanceQueryComposer,
)


class LiteralSearchStrategy:
    """
    Pass the query text to the gateway without transformation.

    The user's own casing and internal whitespace are preserved.
    """

    name = "literal"

    def execute(
        self,
        query: SearchQuery,
        gateway: ProductSearchGateway,
    ) -> SearchResults:
        return gateway.search(
            text=query.text,
            pagination=query.pagination,
            filters=query.filters,
        )


class NormalizedSearchStrategy:
    """
    Normalize the query text before passing it to the gateway.

    Normalization here is deliberately conservative: lowercase, split on
    any run of whitespace, join with single spaces.
    """

    name = "normalized"

    def execute(
        self,
        query: SearchQuery,
        gateway: ProductSearchGateway,
    ) -> SearchResults:
        return gateway.search(
            text=_normalize_text(query.text),
            pagination=query.pagination,
            filters=query.filters,
        )


class RelevantSearchStrategy:
    """
    Execute a search using the platform's relevance policy.

    The strategy asks a ``RelevanceQueryComposer`` to compose a full
    Elasticsearch query and hands it to the gateway's ``search_query``
    method. All the policy lives behind the composer.
    """

    name = "relevant"

    def __init__(self, composer: RelevanceQueryComposer) -> None:
        self._composer = composer

    def execute(
        self,
        query: SearchQuery,
        gateway: ProductSearchGateway,
    ) -> SearchResults:
        composed = self._composer.build(query.text, query.filters)
        return gateway.search_query(composed, query.pagination)


class FuzzySearchStrategy:
    """
    Execute a fuzzy search that tolerates per-token typing errors.

    The strategy asks a ``FuzzyQueryComposer`` to compose a fuzzy
    multi_match query and hands it to the gateway's ``search_query``
    method. See docs/15-fuzzy-search.md.
    """

    name = "fuzzy"

    def __init__(self, composer: FuzzyQueryComposer) -> None:
        self._composer = composer

    def execute(
        self,
        query: SearchQuery,
        gateway: ProductSearchGateway,
    ) -> SearchResults:
        composed = self._composer.build(query.text, query.filters)
        return gateway.search_query(composed, query.pagination)


def _normalize_text(text: str) -> str:
    """Lowercase and collapse internal whitespace to single spaces."""
    return " ".join(text.lower().split())


__all__ = [
    "FuzzySearchStrategy",
    "LiteralSearchStrategy",
    "NormalizedSearchStrategy",
    "RelevantSearchStrategy",
]
