"""
Unit tests for search execution strategies and strategy selection.

No Elasticsearch is contacted. The gateway is a test double that records
the text and pagination it was called with, so each strategy's
preparation policy can be asserted directly.
"""

from __future__ import annotations

import pytest

from apps.search.application.strategies import (
    LiteralSearchStrategy,
    NormalizedSearchStrategy,
)
from apps.search.application.strategy_selector import select_strategy
from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchResults
from apps.search.domain.strategies import (
    ProductSearchGateway,
    SearchExecutionStrategy,
    SearchIntent,
)


class _RecordingGateway:
    """Test double for ProductSearchGateway that records each call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Pagination]] = []
        self.query_calls: list[tuple[dict, Pagination]] = []
        self._result = SearchResults(
            query=SearchQuery.create("recorded"),
            total=0,
            hits=(),
        )

    def search(
        self,
        text: str,
        pagination: Pagination,
        filters: object | None = None,
    ) -> SearchResults:
        self.calls.append((text, pagination))
        return self._result

    def search_query(self, query: dict, pagination: Pagination) -> SearchResults:
        self.query_calls.append((query, pagination))
        return self._result


# ---------------------------------------------------------------------------
# Contract conformance
# ---------------------------------------------------------------------------
def test_literal_strategy_satisfies_protocol() -> None:
    assert isinstance(LiteralSearchStrategy(), SearchExecutionStrategy)


def test_normalized_strategy_satisfies_protocol() -> None:
    assert isinstance(NormalizedSearchStrategy(), SearchExecutionStrategy)


def test_recording_gateway_satisfies_protocol() -> None:
    assert isinstance(_RecordingGateway(), ProductSearchGateway)


# ---------------------------------------------------------------------------
# Literal strategy behaviour
# ---------------------------------------------------------------------------
def test_literal_strategy_preserves_text_verbatim() -> None:
    gateway = _RecordingGateway()
    query = SearchQuery.create("  Mindray uMEC 12  ")
    # SearchQuery.create strips outer whitespace, so the text reaching
    # the gateway is "Mindray uMEC 12" exactly.
    LiteralSearchStrategy().execute(query, gateway)
    assert gateway.calls[0][0] == "Mindray uMEC 12"


def test_literal_strategy_passes_pagination_through() -> None:
    gateway = _RecordingGateway()
    pagination = Pagination(page=3, page_size=7)
    query = SearchQuery.create("monitor", pagination=pagination)
    LiteralSearchStrategy().execute(query, gateway)
    assert gateway.calls[0][1] is pagination


def test_literal_strategy_returns_gateway_result() -> None:
    gateway = _RecordingGateway()
    result = LiteralSearchStrategy().execute(SearchQuery.create("x"), gateway)
    assert result is gateway._result


# ---------------------------------------------------------------------------
# Normalized strategy behaviour
# ---------------------------------------------------------------------------
def test_normalized_strategy_lowercases_text() -> None:
    gateway = _RecordingGateway()
    query = SearchQuery.create("Patient Monitor")
    NormalizedSearchStrategy().execute(query, gateway)
    assert gateway.calls[0][0] == "patient monitor"


def test_normalized_strategy_collapses_internal_whitespace() -> None:
    gateway = _RecordingGateway()
    query = SearchQuery.create("patient    monitor\tECG")
    NormalizedSearchStrategy().execute(query, gateway)
    assert gateway.calls[0][0] == "patient monitor ecg"


def test_normalized_strategy_is_idempotent_on_already_normalized_text() -> None:
    gateway = _RecordingGateway()
    query = SearchQuery.create("patient monitor")
    NormalizedSearchStrategy().execute(query, gateway)
    assert gateway.calls[0][0] == "patient monitor"


def test_normalized_strategy_passes_pagination_through() -> None:
    gateway = _RecordingGateway()
    pagination = Pagination(page=2, page_size=15)
    query = SearchQuery.create("monitor", pagination=pagination)
    NormalizedSearchStrategy().execute(query, gateway)
    assert gateway.calls[0][1] is pagination


# ---------------------------------------------------------------------------
# Strategy selection
# ---------------------------------------------------------------------------
def test_selector_returns_literal_strategy_for_literal_intent() -> None:
    strategy = select_strategy(SearchIntent.LITERAL)
    assert isinstance(strategy, LiteralSearchStrategy)


def test_selector_returns_normalized_strategy_for_normalized_intent() -> None:
    strategy = select_strategy(SearchIntent.NORMALIZED)
    assert isinstance(strategy, NormalizedSearchStrategy)


def test_selector_raises_for_unregistered_intent() -> None:
    # An enum member that exists but has no registered strategy would only
    # occur if the enum and the registry were out of sync. Simulate it by
    # passing a bare string that is not a member of SearchIntent.
    with pytest.raises(KeyError):
        select_strategy("nonexistent-intent")  # type: ignore[arg-type]
