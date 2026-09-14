"""
Concrete search execution strategies.

Three strategies are provided as of Phase 9:

    LiteralSearchStrategy
        Passes the user's query text to the gateway verbatim. Correct when
        the user's text is meaningful as-is: brand names, model numbers,
        SKUs, quoted phrases.

    NormalizedSearchStrategy
        Lowercases and collapses internal whitespace before handing the
        text to the gateway. Correct for free-text exploration where
        casing and extra spaces should not affect matching.

    RelevantSearchStrategy
        Composes a relevance query (multi_match with boosts, exact-phrase
        should clause, business-signal function_score) and hands it to the
        gateway's query-based method. Correct for general search-box
        behavior.

Later phases add further strategies in this module (Phase 10 fuzzy,
Phase 11 synonym, Phase 12 autocomplete). Adding a strategy does not
require modifying the use case, the selector, the domain contracts, or
any existing strategy.

The relevance strategy depends on the domain Protocol
``RelevanceQueryComposer``, not on the concrete infrastructure class that
implements it. The composition root wires the concrete implementation.
"""

from __future__ import annotations

from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchResults
from apps.search.domain.strategies import (
    ProductSearchGateway,
    RelevanceQueryComposer,
)


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


class RelevantSearchStrategy:
    """
    Execute a search using the platform's relevance policy.

    Unlike the text-preparation strategies, this strategy does not
    decide how the *text* is prepared. It asks a ``RelevanceQueryComposer``
    to compose a full Elasticsearch query and hands it to the gateway's
    ``search_query`` method.

    All the policy lives behind the ``RelevanceQueryComposer`` Protocol.
    This strategy is only the mechanism that selects that policy; it
    holds no policy itself.
    """

    name = "relevant"

    def __init__(self, composer: RelevanceQueryComposer) -> None:
        self._composer = composer

    def execute(
        self,
        query: SearchQuery,
        gateway: ProductSearchGateway,
    ) -> SearchResults:
        composed = self._composer.build(query.text)
        return gateway.search_query(composed, query.pagination)


def _normalize_text(text: str) -> str:
    """Lowercase and collapse internal whitespace to single spaces."""
    return " ".join(text.lower().split())


__all__ = [
    "LiteralSearchStrategy",
    "NormalizedSearchStrategy",
    "RelevantSearchStrategy",
]
