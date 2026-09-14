"""
Unit tests for the fluent Elasticsearch query builder.

The builder's output is a dictionary. The tests assert its exact shape,
so that the current contract is documented in executable form.
"""

from __future__ import annotations

import pytest

from infrastructure.elasticsearch.query.builder import QueryBuilder
from infrastructure.elasticsearch.query.clauses import (
    MatchClause,
    RangeClause,
    TermClause,
)


# ---------------------------------------------------------------------------
# Empty builder
# ---------------------------------------------------------------------------
def test_empty_builder_raises() -> None:
    with pytest.raises(ValueError):
        QueryBuilder().build()


def test_builder_with_only_minimum_should_match_still_raises() -> None:
    with pytest.raises(ValueError):
        QueryBuilder().minimum_should_match(2).build()


def test_minimum_should_match_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        QueryBuilder().minimum_should_match(-1)


# ---------------------------------------------------------------------------
# Single slot
# ---------------------------------------------------------------------------
def test_builder_with_one_must_clause() -> None:
    result = QueryBuilder().must(MatchClause(field="name", value="monitor")).build()
    assert result == {"bool": {"must": [{"match": {"name": "monitor"}}]}}


def test_builder_with_one_filter_clause() -> None:
    result = QueryBuilder().filter(TermClause(field="brand", value="Mindray")).build()
    assert result == {"bool": {"filter": [{"term": {"brand": "Mindray"}}]}}


def test_builder_with_one_should_clause() -> None:
    result = QueryBuilder().should(MatchClause(field="description", value="portable")).build()
    assert result == {"bool": {"should": [{"match": {"description": "portable"}}]}}


def test_builder_with_one_must_not_clause() -> None:
    result = QueryBuilder().must_not(TermClause(field="availability", value="discontinued")).build()
    assert result == {"bool": {"must_not": [{"term": {"availability": "discontinued"}}]}}


# ---------------------------------------------------------------------------
# Multiple slots
# ---------------------------------------------------------------------------
def test_builder_with_must_and_filter() -> None:
    result = (
        QueryBuilder()
        .must(MatchClause(field="name", value="monitor"))
        .filter(TermClause(field="brand", value="Mindray"))
        .build()
    )
    assert result == {
        "bool": {
            "must": [{"match": {"name": "monitor"}}],
            "filter": [{"term": {"brand": "Mindray"}}],
        }
    }


def test_builder_with_all_four_slots() -> None:
    result = (
        QueryBuilder()
        .must(MatchClause(field="name", value="monitor"))
        .filter(TermClause(field="category", value="Patient Monitoring"))
        .should(MatchClause(field="tags", value="ECG"))
        .must_not(TermClause(field="availability", value="discontinued"))
        .build()
    )
    assert result == {
        "bool": {
            "must": [{"match": {"name": "monitor"}}],
            "filter": [{"term": {"category": "Patient Monitoring"}}],
            "should": [{"match": {"tags": "ECG"}}],
            "must_not": [{"term": {"availability": "discontinued"}}],
        }
    }


# ---------------------------------------------------------------------------
# Multiple clauses within a slot
# ---------------------------------------------------------------------------
def test_builder_accumulates_multiple_must_clauses_in_order() -> None:
    result = (
        QueryBuilder()
        .must(MatchClause(field="name", value="monitor"))
        .must(MatchClause(field="description", value="portable"))
        .build()
    )
    assert result["bool"]["must"] == [
        {"match": {"name": "monitor"}},
        {"match": {"description": "portable"}},
    ]


# ---------------------------------------------------------------------------
# minimum_should_match
# ---------------------------------------------------------------------------
def test_builder_emits_minimum_should_match_when_set() -> None:
    result = (
        QueryBuilder()
        .should(MatchClause(field="tags", value="ECG"))
        .should(MatchClause(field="tags", value="SpO2"))
        .minimum_should_match(1)
        .build()
    )
    assert result["bool"]["minimum_should_match"] == 1


# ---------------------------------------------------------------------------
# Fluent API shape
# ---------------------------------------------------------------------------
def test_each_slot_mutator_returns_the_same_builder() -> None:
    builder = QueryBuilder()
    assert builder.must(MatchClause(field="a", value="b")) is builder
    assert builder.filter(TermClause(field="a", value="b")) is builder
    assert builder.should(MatchClause(field="a", value="b")) is builder
    assert builder.must_not(TermClause(field="a", value="b")) is builder
    assert builder.minimum_should_match(0) is builder


# ---------------------------------------------------------------------------
# Range clause composition
# ---------------------------------------------------------------------------
def test_builder_with_range_filter() -> None:
    result = QueryBuilder().filter(RangeClause(field="price", gte=500.0, lte=3000.0)).build()
    assert result == {"bool": {"filter": [{"range": {"price": {"gte": 500.0, "lte": 3000.0}}}]}}
