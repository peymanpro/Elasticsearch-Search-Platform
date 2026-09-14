"""Unit tests for the ``GetSuggestionsUseCase``."""

from __future__ import annotations

import pytest

from apps.search.application.get_suggestions import GetSuggestionsUseCase
from apps.search.domain.suggest_query import (
    DEFAULT_LIMIT,
    InvalidSuggestQueryError,
)


class _RecordingSuggester:
    def __init__(self, results: tuple[str, ...] = ()) -> None:
        self.calls: list = []
        self._results = results
        self.raise_on_call: Exception | None = None

    def suggest(self, query) -> tuple[str, ...]:
        if self.raise_on_call is not None:
            raise self.raise_on_call
        self.calls.append(query)
        return self._results


def test_use_case_returns_suggester_results() -> None:
    suggester = _RecordingSuggester(results=("Headphones", "Headphone Stand"))
    use_case = GetSuggestionsUseCase(suggester=suggester)

    assert use_case.execute("headph") == ("Headphones", "Headphone Stand")


def test_use_case_uses_default_limit_when_none_given() -> None:
    suggester = _RecordingSuggester()
    use_case = GetSuggestionsUseCase(suggester=suggester)

    use_case.execute("headph")
    assert suggester.calls[0].limit == DEFAULT_LIMIT


def test_use_case_passes_explicit_limit() -> None:
    suggester = _RecordingSuggester()
    use_case = GetSuggestionsUseCase(suggester=suggester)

    use_case.execute("headph", limit=3)
    assert suggester.calls[0].limit == 3


def test_use_case_validates_prefix_before_calling_suggester() -> None:
    suggester = _RecordingSuggester()
    use_case = GetSuggestionsUseCase(suggester=suggester)

    with pytest.raises(InvalidSuggestQueryError):
        use_case.execute("")
    assert suggester.calls == []


def test_use_case_propagates_suggester_errors() -> None:
    suggester = _RecordingSuggester()
    suggester.raise_on_call = RuntimeError("backend unavailable")
    use_case = GetSuggestionsUseCase(suggester=suggester)

    with pytest.raises(RuntimeError):
        use_case.execute("headph")
