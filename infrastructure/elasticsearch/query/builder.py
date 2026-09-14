"""
Fluent builder for Elasticsearch ``bool`` queries.

The builder collects clauses into the four slots that Elasticsearch's
``bool`` query recognizes -- ``must``, ``filter``, ``should``,
``must_not`` -- and renders them as a single query dictionary.

Why a builder, rather than a function that takes a dict of lists:

    * The ``bool`` structure has rules: only four slots, and no valid
      empty ``bool``. A builder makes the structure explicit and enforces
      the rules at build time, rather than at call time.
    * Callers compose queries incrementally. A fluent API reads as the
      query they are describing.
    * Later phases will extend the *set of clauses* (Phases 8-12), not
      the set of slots. The builder therefore has a stable surface even
      as the clause vocabulary grows.

The builder is deliberately independent of any domain-specific concept.
It does not know about products, fields, relevance, or analyzers. Those
belong to the phase that composes queries for this platform's domain.
"""

from __future__ import annotations

from typing import Any

from infrastructure.elasticsearch.query.clauses import Clause


class QueryBuilder:
    """
    Construct an Elasticsearch ``bool`` query.

    Usage:

        query = (
            QueryBuilder()
            .must(MatchClause(field="name", value="monitor", boost=2.0))
            .filter(TermClause(field="brand", value="Mindray"))
            .build()
        )

    The result is a dictionary ready to be passed to the ``query``
    parameter of a search request.
    """

    def __init__(self) -> None:
        self._must: list[Clause] = []
        self._filter: list[Clause] = []
        self._should: list[Clause] = []
        self._must_not: list[Clause] = []
        self._minimum_should_match: int | None = None

    # --------------------------------------------------------------
    # Slot mutators
    # --------------------------------------------------------------
    def must(self, clause: Clause) -> QueryBuilder:
        """Add a clause that must match; contributes to the score."""
        self._must.append(clause)
        return self

    def filter(self, clause: Clause) -> QueryBuilder:
        """Add a clause that must match; does not contribute to the score."""
        self._filter.append(clause)
        return self

    def should(self, clause: Clause) -> QueryBuilder:
        """Add a clause that may match; contributes to the score."""
        self._should.append(clause)
        return self

    def must_not(self, clause: Clause) -> QueryBuilder:
        """Add a clause that must not match."""
        self._must_not.append(clause)
        return self

    def minimum_should_match(self, value: int) -> QueryBuilder:
        """
        Set the minimum number of ``should`` clauses that must match.

        ``minimum_should_match`` is a modifier on the ``bool`` query, not
        a clause. Setting it does not by itself constitute a valid query;
        at least one clause must also be present (see ``build``). When
        omitted, Elasticsearch's default applies: if the ``bool``
        contains ``must`` or ``filter``, the default is 0; otherwise 1.
        The builder does not override the default by guessing -- it
        leaves the decision to the caller.
        """
        if value < 0:
            raise ValueError("minimum_should_match must be >= 0")
        self._minimum_should_match = value
        return self

    # --------------------------------------------------------------
    # Introspection
    # --------------------------------------------------------------
    def _has_any_clause(self) -> bool:
        """
        True if at least one clause has been added to any slot.

        ``minimum_should_match`` is deliberately not part of this check:
        it modifies the behaviour of ``should`` clauses, and without any
        clause it produces a query that Elasticsearch rejects.
        """
        return bool(self._must or self._filter or self._should or self._must_not)

    # --------------------------------------------------------------
    # Rendering
    # --------------------------------------------------------------
    def build(self) -> dict[str, Any]:
        """
        Render the accumulated clauses as an Elasticsearch query mapping.

        The result is always a ``bool`` query, because that is the only
        container whose slots this builder manages.

        Raises:
            ValueError: when no clause has been added to any slot. An
                empty ``bool`` query -- or one that carries only a
                ``minimum_should_match`` modifier without clauses -- is
                not valid in Elasticsearch. The builder fails loudly at
                construction time rather than deferring the error to the
                server.
        """
        if not self._has_any_clause():
            raise ValueError(
                "cannot build a query without clauses: add at least one "
                "clause via must(), filter(), should(), or must_not(). "
                "minimum_should_match alone is not a clause."
            )

        bool_body: dict[str, Any] = {}

        if self._must:
            bool_body["must"] = [clause.to_dsl() for clause in self._must]
        if self._filter:
            bool_body["filter"] = [clause.to_dsl() for clause in self._filter]
        if self._should:
            bool_body["should"] = [clause.to_dsl() for clause in self._should]
        if self._must_not:
            bool_body["must_not"] = [clause.to_dsl() for clause in self._must_not]

        if self._minimum_should_match is not None:
            bool_body["minimum_should_match"] = self._minimum_should_match

        return {"bool": bool_body}
