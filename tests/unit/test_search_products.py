"""
Unit tests for the ``SearchProductsUseCase``.

The use case is exercised against a recording gateway. It must not
contact Elasticsearch and must not depend on which strategy it selects
beyond the strategy's observable effect on the text reaching the gateway.
"""

from __future__ import annotations

from apps.search.application.search_products import SearchProductsUseCase
from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchResults
from apps.search.domain.strategies import SearchIntent


class _RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Pagination]] = []
        self.result = SearchResults(
            query=SearchQuery.create("recorded"),
            total=0,
            hits=(),
        )
        self.raise_on_call: Exception | None = None

    def search(
        self,
        text: str,
        pagination: Pagination,
        filters: object | None = None,
        sort: object | None = None,
    ) -> SearchResults:
        if self.raise_on_call is not None:
            raise self.raise_on_call
        self.calls.append((text, pagination))
        return self.result


def test_use_case_uses_literal_strategy_by_default() -> None:
    gateway = _RecordingGateway()
    use_case = SearchProductsUseCase(gateway=gateway)

    use_case.execute(SearchQuery.create("Patient Monitor"))

    # Literal preserves case.
    assert gateway.calls[0][0] == "Patient Monitor"


def test_use_case_uses_the_selected_strategy() -> None:
    gateway = _RecordingGateway()
    use_case = SearchProductsUseCase(gateway=gateway)

    use_case.execute(SearchQuery.create("Patient Monitor"), intent=SearchIntent.NORMALIZED)

    assert gateway.calls[0][0] == "patient monitor"


def test_use_case_returns_gateway_results_verbatim() -> None:
    gateway = _RecordingGateway()
    use_case = SearchProductsUseCase(gateway=gateway)

    results = use_case.execute(SearchQuery.create("x"))

    assert results is gateway.result


def test_use_case_propagates_gateway_errors() -> None:
    gateway = _RecordingGateway()
    gateway.raise_on_call = RuntimeError("backend unavailable")
    use_case = SearchProductsUseCase(gateway=gateway)

    try:
        use_case.execute(SearchQuery.create("x"))
    except RuntimeError:
        return
    raise AssertionError("use case should propagate the gateway's error")
