"""
Elasticsearch query-language helpers.

This package contains the parts of the platform that construct query
language from Python objects:

    clauses   -- leaf clause types (match, term, range)
    builder   -- the fluent ``bool`` query builder

The package is deliberately independent of any domain-specific concept.
Domain-aware query composition (which fields, which boosts, which
relevance strategy) belongs to later phases:

    Phase 8   query composition for the products catalog
    Phase 9   relevance strategies
    Phase 10  fuzzy clauses
    Phase 11  synonym-aware clauses
    Phase 12  search_as_you_type
"""

from infrastructure.elasticsearch.query.builder import QueryBuilder
from infrastructure.elasticsearch.query.clauses import (
    Clause,
    MatchClause,
    RangeClause,
    TermClause,
)

__all__ = [
    "Clause",
    "MatchClause",
    "QueryBuilder",
    "RangeClause",
    "TermClause",
]
