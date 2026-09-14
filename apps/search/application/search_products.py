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

The use case measures its own duration and emits a structured log
line at the end of every execution. The correlation ID attached to
that line comes from the logging filter, not from this module: the
use case does not read the correlation ID. See
docs/29-observability.md sections 3 and 4.
"""

from __future__ import annotations

import logging
import time

from apps.search.application.strategy_selector import select_strategy
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchResults
from apps.search.domain.strategies import (
    FuzzyQueryComposer,
    ProductSearchGateway,
    RelevanceQueryComposer,
    SearchIntent,
)

logger = logging.getLogger(__name__)

# A search slower than this threshold is logged at WARNING in addition
# to INFO. See docs/29-observability.md section 4.3.
SLOW_SEARCH_THRESHOLD_MS = 500.0


class SearchProductsUseCase:
    """Execute a product search using the selected strategy."""

    def __init__(
        self,
        gateway: ProductSearchGateway,
        *,
        relevance_composer: RelevanceQueryComposer | None = None,
        fuzzy_composer: FuzzyQueryComposer | None = None,
    ) -> None:
        self._gateway = gateway
        self._relevance_composer = relevance_composer
        self._fuzzy_composer = fuzzy_composer

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
        started = time.perf_counter()

        strategy = select_strategy(
            intent,
            relevance_composer=self._relevance_composer,
            fuzzy_composer=self._fuzzy_composer,
        )
        results = strategy.execute(query, self._gateway)

        duration_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "search.executed query_len=%d total=%d returned=%d duration_ms=%.2f",
            len(query.text),
            results.total,
            results.returned,
            duration_ms,
        )
        if duration_ms >= SLOW_SEARCH_THRESHOLD_MS:
            logger.warning(
                "search.slow duration_ms=%.2f threshold_ms=%.2f",
                duration_ms,
                SLOW_SEARCH_THRESHOLD_MS,
            )

        return results


__all__ = ["SearchProductsUseCase", "SLOW_SEARCH_THRESHOLD_MS"]
