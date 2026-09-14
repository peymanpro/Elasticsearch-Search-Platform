"""Sanity tests for the benchmark workload definition."""

from __future__ import annotations

from benchmarks.workload import AUTOCOMPLETE_PREFIX, WORKLOAD


def test_workload_is_not_empty() -> None:
    assert len(WORKLOAD) >= 4


def test_every_query_has_a_unique_name() -> None:
    names = [q.name for q in WORKLOAD]
    assert len(names) == len(set(names))


def test_every_query_has_a_body() -> None:
    for q in WORKLOAD:
        assert isinstance(q.body, dict), f"{q.name} has no body"
        assert q.body, f"{q.name} has an empty body"


def test_workload_covers_all_required_query_types() -> None:
    names = {q.name for q in WORKLOAD}
    expected = {"exact_match", "phrase_match", "fuzzy_match", "faceted_search"}
    assert expected.issubset(names), f"missing: {expected - names}"


def test_autocomplete_prefix_is_non_empty() -> None:
    assert AUTOCOMPLETE_PREFIX.strip()
