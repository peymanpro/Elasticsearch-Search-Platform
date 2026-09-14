"""
Use case: explain why a document matched a search query.

The caller supplies the search text and a document id. The use case
composes the platform's relevance query for that text, asks the
``ProductExplainer`` for the explanation, and returns it.

The composed query is the same one a relevance search would issue, so
the explanation describes the actual ranking the platform would
produce, not a hypothetical one.
"""

from __future__ import annotations

from apps.search.domain.explanation import ExplainResult
from apps.search.domain.strategies import (
    ProductExplainer,
    RelevanceQueryComposer,
)


class ExplainScoreUseCase:
    """Explain why a specific document matched a specific text query."""

    def __init__(
        self,
        explainer: ProductExplainer,
        composer: RelevanceQueryComposer,
    ) -> None:
        self._explainer = explainer
        self._composer = composer

    def execute(self, text: str, document_id: str) -> ExplainResult:
        """
        Compose the relevance query for ``text`` and explain it against
        ``document_id``.

        The composer receives no filters: the platform's ranking for an
        explanation is the ranking without narrowing, so that the
        explanation reflects why the document would appear in an
        unfiltered search.
        """
        composed = self._composer.build(text)
        return self._explainer.explain(composed, document_id)


__all__ = ["ExplainScoreUseCase"]
