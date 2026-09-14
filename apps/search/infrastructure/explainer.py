"""
Elasticsearch product explainer.

Adapter from the domain's ``ProductExplainer`` port to Elasticsearch's
``_explain`` API. The API returns a recursive JSON tree describing how
the score for a (query, document) pair was computed. This module
converts that tree into the domain's ``ScoreExplanation`` and
``ExplainResult`` value objects.

See docs/21-explainability.md.
"""

from __future__ import annotations

from typing import Any

from apps.search.domain.explanation import ExplainResult, ScoreExplanation
from elasticsearch import Elasticsearch


class ElasticsearchProductExplainer:
    """
    Adapter from ``ProductExplainer`` to Elasticsearch.

    Args:
        client: An Elasticsearch client.
        index: The index or alias to explain against.
    """

    def __init__(self, client: Elasticsearch, index: str) -> None:
        self._client = client
        self._index = index

    def explain(self, query: dict[str, Any], document_id: str) -> ExplainResult:
        """
        Return the explanation for the given query and document.

        Elasticsearch's response uses ``matched`` to distinguish a
        matching document from a non-matching one. For a matching
        document the ``explanation`` key holds the recursive tree; for
        a non-matching one it is absent. The domain preserves the
        distinction with ``None``.
        """
        response = self._client.explain(
            index=self._index,
            id=document_id,
            query=query,
        )
        matched = bool(response.get("matched", False))
        raw_explanation = response.get("explanation")
        if not matched or not isinstance(raw_explanation, dict):
            return ExplainResult(matched=matched, explanation=None)
        return ExplainResult(
            matched=True,
            explanation=_parse_explanation(raw_explanation),
        )


def _parse_explanation(raw: dict[str, Any]) -> ScoreExplanation:
    """
    Recursively convert one node of the ``_explain`` response.

    The children are converted eagerly so that the returned tree is
    fully materialized. Missing or malformed children are treated as
    an empty tuple: a leaf node has no children, and the adapter does
    not distinguish "missing" from "empty" -- both mean "no children".
    """
    children_raw = raw.get("details")
    children: tuple[ScoreExplanation, ...] = ()
    if isinstance(children_raw, list):
        children = tuple(
            _parse_explanation(child) for child in children_raw if isinstance(child, dict)
        )
    return ScoreExplanation(
        value=float(raw.get("value", 0.0)),
        description=str(raw.get("description", "")),
        details=children,
    )


__all__ = ["ElasticsearchProductExplainer"]
