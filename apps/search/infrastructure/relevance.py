"""
Relevance query composer (infrastructure layer).

This module originally lived in the application layer and was moved here
during Phase 9 when the project's architecture tests flagged that it
imports Elasticsearch DSL builders. The application layer must not know
about Elasticsearch; the infrastructure layer may. The application's
relevance strategy depends on the domain Protocol ``RelevanceQueryComposer``
and receives this class through the composition root.

The content is otherwise unchanged from the design described in
docs/14-relevance.md.
"""

from __future__ import annotations

from typing import Any

from infrastructure.elasticsearch.query.builder import QueryBuilder
from infrastructure.elasticsearch.query.clauses import (
    MatchPhraseClause,
    MultiMatchClause,
)

# ---------------------------------------------------------------------------
# Relevance policy
# ---------------------------------------------------------------------------
# These constants ARE the policy. They are public (module-level, named)
# so that tests can assert against them and readers can see them
# without reading the builder code.

# Field boosts, in the order they are passed to multi_match.
# The ^N suffix is Elasticsearch's boost convention.
FIELD_BOOSTS: tuple[str, ...] = (
    "name^3.0",
    "brand^2.0",
    "category^1.5",
    "tags^1.5",
    "description^1.0",
)

# Exact-phrase boost on the name field.
EXACT_NAME_PHRASE_BOOST = 5.0

# Business signals: (field, factor, modifier or None).
# ``log1p`` compresses popularity's wide range so it does not dominate.
BUSINESS_SIGNALS: tuple[tuple[str, float, str | None], ...] = (
    ("rating", 1.0, None),
    ("popularity", 0.5, "log1p"),
)


class RelevanceQueryBuilder:
    """
    Build the platform's relevance query for a text.

    The builder is stateless. It can be instantiated once and reused
    for every request. All policy lives in the module-level constants
    above, so the builder itself has no configuration parameters.
    """

    def build(self, text: str) -> dict[str, Any]:
        """
        Return the complete Elasticsearch query for ``text``.

        The query is a function_score wrapping the text-relevance
        bool query. It can be passed directly to the search API's
        ``query`` parameter.
        """
        text_query = self._build_text_query(text)
        return self._wrap_with_business_signals(text_query)

    def _build_text_query(self, text: str) -> dict[str, Any]:
        """
        The text-relevance part: multi_match over boosted fields plus
        an optional exact-phrase match on the name.
        """
        return (
            QueryBuilder()
            .must(MultiMatchClause(fields=FIELD_BOOSTS, value=text))
            .should(MatchPhraseClause(field="name", value=text, boost=EXACT_NAME_PHRASE_BOOST))
            .minimum_should_match(0)
            .build()
        )

    def _wrap_with_business_signals(self, text_query: dict[str, Any]) -> dict[str, Any]:
        """
        Wrap a text query in a function_score that adds business
        signals.

        The output shape is the Elasticsearch function_score DSL:

            {
              "function_score": {
                "query": <text_query>,
                "functions": [{"field_value_factor": {...}}, ...],
                "score_mode": "sum",
                "boost_mode": "sum"
              }
            }
        """
        functions = [
            self._signal_to_function(field, factor, modifier)
            for field, factor, modifier in BUSINESS_SIGNALS
        ]
        return {
            "function_score": {
                "query": text_query,
                "functions": functions,
                "score_mode": "sum",
                "boost_mode": "sum",
            }
        }

    @staticmethod
    def _signal_to_function(
        field: str,
        factor: float,
        modifier: str | None,
    ) -> dict[str, Any]:
        """
        Convert one (field, factor, modifier) tuple into a
        function_score function. A missing modifier is omitted rather
        than passed as null, which Elasticsearch rejects.
        """
        body: dict[str, Any] = {"field": field, "factor": factor}
        if modifier is not None:
            body["modifier"] = modifier
        return {"field_value_factor": body}


__all__ = [
    "BUSINESS_SIGNALS",
    "EXACT_NAME_PHRASE_BOOST",
    "FIELD_BOOSTS",
    "RelevanceQueryBuilder",
]
