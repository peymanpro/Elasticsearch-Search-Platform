"""
Unit tests for Elasticsearch query clauses.

Each clause renders a self-contained fragment of Elasticsearch's query
language. The tests assert the exact dictionary shape Elasticsearch
expects. No Elasticsearch is contacted.
"""

from __future__ import annotations

from infrastructure.elasticsearch.query.clauses import (
    MatchClause,
    RangeClause,
    TermClause,
)


# ---------------------------------------------------------------------------
# MatchClause
# ---------------------------------------------------------------------------
def test_match_clause_without_boost() -> None:
    assert MatchClause(field="name", value="monitor").to_dsl() == {"match": {"name": "monitor"}}


def test_match_clause_with_boost() -> None:
    assert MatchClause(field="name", value="monitor", boost=2.0).to_dsl() == {
        "match": {"name": {"query": "monitor", "boost": 2.0}}
    }


# ---------------------------------------------------------------------------
# TermClause
# ---------------------------------------------------------------------------
def test_term_clause_shape() -> None:
    assert TermClause(field="brand", value="Mindray").to_dsl() == {"term": {"brand": "Mindray"}}


# ---------------------------------------------------------------------------
# RangeClause
# ---------------------------------------------------------------------------
def test_range_clause_with_both_bounds() -> None:
    clause = RangeClause(field="price", gte=100.0, lte=500.0)
    assert clause.to_dsl() == {"range": {"price": {"gte": 100.0, "lte": 500.0}}}


def test_range_clause_with_exclusive_lower_bound() -> None:
    clause = RangeClause(field="rating", gt=4.0)
    assert clause.to_dsl() == {"range": {"rating": {"gt": 4.0}}}


def test_range_clause_with_only_upper_bound() -> None:
    clause = RangeClause(field="price", lt=1000)
    assert clause.to_dsl() == {"range": {"price": {"lt": 1000}}}


def test_range_clause_with_no_bounds_produces_empty_body() -> None:
    # Unusual but well-formed: an unbounded range has no bounds. The
    # builder renders this faithfully; whether it is meaningful is the
    # caller's decision.
    clause = RangeClause(field="price")
    assert clause.to_dsl() == {"range": {"price": {}}}
