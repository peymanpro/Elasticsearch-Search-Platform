"""
Use case: execute a product search.

Flow:

    SearchProductsUseCase.execute(query, intent)
        -> select_strategy(intent, relevance_composer=...)
        -> strategy.execute(query, gateway)
        -> SearchResults

The use case depends only on the domain's ``ProductSearchGateway`` port
and the ``RelevanceQueryComposer`` Protocol. It does not know which
concrete strategy exists, and it does not know which gateway or composer
it holds -- all three are injected at composition time.
"""

from __future__ import annotations

from apps.search.application.strategy_selector import select_strategy
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchResults
from apps.search.domain.strategies import (
    ProductSearchGateway,
    RelevanceQueryComposer,
    SearchIntent,
)


class SearchProductsUseCase:
    """Execute a product search using the selected strategy."""

    def __init__(
        self,
        gateway: ProductSearchGateway,
        *,
        relevance_composer: RelevanceQueryComposer | None = None,
    ) -> None:
        self._gateway = gateway
        self._relevance_composer = relevance_composer

    def execute(
        self,
        query: SearchQuery,
        intent: SearchIntent = SearchIntent.LITERAL,
    ) -> SearchResults:
        """
        Execute ``query`` using the strategy selected by ``intent``.

        The default intent is LITERAL: the least surprising choice for a
        caller who does not specify one. If ``intent`` is RELEVANT, the
        use case must have been constructed with a
        ``relevance_composer``; otherwise ``select_strategy`` raises.
        """
        strategy = select_strategy(
            intent,
            relevance_composer=self._relevance_composer,
        )
        return strategy.execute(query, self._gateway)


__all__ = ["SearchProductsUseCase"]
