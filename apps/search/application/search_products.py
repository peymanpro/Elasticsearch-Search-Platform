"""
Use case: execute a product search.

This is the flow the Strategy Pattern is meant to demonstrate:

    SearchProductsUseCase.execute(query, intent)
        -> select_strategy(intent)
        -> strategy.execute(query, gateway)
        -> SearchResults

The use case depends only on the domain's ``ProductSearchGateway`` port
and the ``SearchExecutionStrategy`` contract. It does not know which
concrete strategy exists, and it does not know which gateway it holds --
both are injected at composition time. This is the Dependency Inversion
Principle of Phase 3.2 applied to the search path.
"""

from __future__ import annotations

from apps.search.application.strategy_selector import select_strategy
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchResults
from apps.search.domain.strategies import (
    ProductSearchGateway,
    SearchIntent,
)


class SearchProductsUseCase:
    """Execute a product search using the selected strategy."""

    def __init__(self, gateway: ProductSearchGateway) -> None:
        self._gateway = gateway

    def execute(
        self,
        query: SearchQuery,
        intent: SearchIntent = SearchIntent.LITERAL,
    ) -> SearchResults:
        """
        Execute ``query`` using the strategy selected by ``intent``.

        The default intent is LITERAL: it is the least surprising choice
        for a caller who does not specify one.
        """
        strategy = select_strategy(intent)
        return strategy.execute(query, self._gateway)


__all__ = ["SearchProductsUseCase"]
