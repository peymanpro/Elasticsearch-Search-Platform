"""
Elasticsearch query DSL clause types.

A clause represents one leaf of the query language: a match, a term
filter, a range filter. Each clause knows how to render itself as a
plain dictionary that Elasticsearch will accept.

Clauses are deliberately dumb. They carry no policy -- which clause to
use, when to boost, which field to weight -- because that policy belongs
to the search strategies and relevance work of later phases. A clause's
only job is to produce a correctly-shaped fragment of the DSL.

The set of clause types will grow in later phases:

    Phase 8   match_phrase, multi_match
    Phase 10  fuzzy variations of match
    Phase 11  synonym-aware match
    Phase 12  search_as_you_type

Adding a new clause type is a matter of adding a new class in this
module. The ``QueryBuilder`` does not change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class Clause(ABC):
    """
    Base class for all query clauses.

    A clause produces a mapping of exactly one key to the value
    Elasticsearch expects for that key. For example, a match clause
    produces ``{"match": {"name": {"query": "monitor", "boost": 2.0}}}``.
    """

    @abstractmethod
    def to_dsl(self) -> dict[str, Any]:
        """Return this clause as an Elasticsearch query-language mapping."""


@dataclass(frozen=True, slots=True)
class MatchClause(Clause):
    """
    Full-text search clause.

    The canonical clause for user-facing text. Elasticsearch analyzes
    both the query and the field and scores the result.
    """

    field: str
    value: str
    boost: float | None = None

    def to_dsl(self) -> dict[str, Any]:
        if self.boost is None:
            return {"match": {self.field: self.value}}
        return {"match": {self.field: {"query": self.value, "boost": self.boost}}}


@dataclass(frozen=True, slots=True)
class TermClause(Clause):
    """
    Exact-value filter clause.

    Use for fields that are mapped as ``keyword``: brand names, categories,
    SKUs, status values. Term queries do not analyze the input and are
    therefore suited to filtering and aggregation.
    """

    field: str
    value: str

    def to_dsl(self) -> dict[str, Any]:
        return {"term": {self.field: self.value}}


@dataclass(frozen=True, slots=True)
class RangeClause(Clause):
    """
    Numeric or date range clause.

    Bounds are optional. When none is supplied, Elasticsearch treats the
    range as unbounded on that side.
    """

    field: str
    gte: float | int | None = None
    gt: float | int | None = None
    lte: float | int | None = None
    lt: float | int | None = None

    def to_dsl(self) -> dict[str, Any]:
        body: dict[str, float | int] = {}
        if self.gte is not None:
            body["gte"] = self.gte
        if self.gt is not None:
            body["gt"] = self.gt
        if self.lte is not None:
            body["lte"] = self.lte
        if self.lt is not None:
            body["lt"] = self.lt
        return {"range": {self.field: body}}
