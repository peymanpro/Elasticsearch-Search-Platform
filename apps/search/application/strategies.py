"""
Concrete search execution strategies.

Two strategies are provided at Phase 3.5:

    LiteralSearchStrategy
        Passes the user's query text to the gateway verbatim. Correct when
        the user's text is meaningful as-is: brand names, model numbers,
        SKUs, quoted phrases.

    NormalizedSearchStrategy
        Lowercases and collapses internal whitespace before handing the
        text to the gateway. Correct for free-text exploration where
        casing and extra spaces should not affect matching.

Later phases add further strategies in this module (Phase 9 relevance
strategies, Phase 10 fuzzy, Phase 11 synonym, Phase 12 autocomplete).
Adding a strategy does not require modifying the use case, the selector,
the domain contracts, or any existing strategy.
"""

from __future__ import annotations

from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchResults
from apps.search.domain.strategies import ProductSearchGateway


class LiteralSearchStrategy:
    """
    Pass the query text to the gateway without transformation.

    The user's own casing and internal whitespace are preserved. This is
    the default strategy and the safest default for a search platform:
    it never surprises the caller by silently changing what was asked for.
    """

    name = "literal"

    def execute(
        self,
        query: SearchQuery,
        gateway: ProductSearchGateway,
    ) -> SearchResults:
        return gateway.search(text=query.text, pagination=query.pagination)


class NormalizedSearchStrategy:
    """
    Normalize the query text before passing it to the gateway.

    Normalization here is deliberately conservative: lowercase, split on
    any run of whitespace, join with single spaces. It does not stem,
    lemmatize, remove accents, or otherwise alter tokens -- those concerns
    belong to Elasticsearch analyzers (Phase 7), not to the platform's
    application layer.

    The point of the strategy is to guarantee that the *shape* of the
    text reaching the gateway is stable, regardless of how the user typed
    it.
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
        )


def _normalize_text(text: str) -> str:
    """Lowercase and collapse internal whitespace to single spaces."""
    return " ".join(text.lower().split())


__all__ = [
    "LiteralSearchStrategy",
    "NormalizedSearchStrategy",
]


# ---------------------------------------------------------------------------
# Re-exported here so the selector and tests import from one place.
# ---------------------------------------------------------------------------
_ = Pagination  # keep the import meaningful for future use; explicit no-op
