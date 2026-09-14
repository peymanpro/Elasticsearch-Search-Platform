"""
Strategy selection.

The selector maps a ``SearchIntent`` to a concrete
``SearchExecutionStrategy``. It is the one place in the codebase that
knows the full set of strategies.

Two categories of strategy exist:

    * Stateless strategies (Literal, Normalized) are instantiated once
      at import time and shared across requests.
    * Strategies that need a collaborator (Relevant, Fuzzy) are
      instantiated per selection, with the collaborator supplied by the
      caller. The selector does not choose concrete implementations of
      the composer Protocols; the composition root does.
"""

from __future__ import annotations

from apps.search.application.strategies import (
    FuzzySearchStrategy,
    LiteralSearchStrategy,
    NormalizedSearchStrategy,
    RelevantSearchStrategy,
)
from apps.search.domain.strategies import (
    FuzzyQueryComposer,
    RelevanceQueryComposer,
    SearchExecutionStrategy,
    SearchIntent,
)

_STATELESS_REGISTRY: dict[SearchIntent, SearchExecutionStrategy] = {
    SearchIntent.LITERAL: LiteralSearchStrategy(),
    SearchIntent.NORMALIZED: NormalizedSearchStrategy(),
}


def select_strategy(
    intent: SearchIntent,
    *,
    relevance_composer: RelevanceQueryComposer | None = None,
    fuzzy_composer: FuzzyQueryComposer | None = None,
) -> SearchExecutionStrategy:
    """
    Return the strategy that corresponds to ``intent``.

    Args:
        intent: The intent the caller is asking about.
        relevance_composer: Required when ``intent`` is RELEVANT.
        fuzzy_composer: Required when ``intent`` is FUZZY.

    Raises:
        ValueError: the required composer for the intent is missing.
        KeyError: ``intent`` is not a recognised value.
    """
    if intent is SearchIntent.RELEVANT:
        if relevance_composer is None:
            raise ValueError(
                "RELEVANT intent requires a relevance_composer; the "
                "selector does not choose a concrete implementation."
            )
        return RelevantSearchStrategy(composer=relevance_composer)

    if intent is SearchIntent.FUZZY:
        if fuzzy_composer is None:
            raise ValueError(
                "FUZZY intent requires a fuzzy_composer; the selector "
                "does not choose a concrete implementation."
            )
        return FuzzySearchStrategy(composer=fuzzy_composer)

    try:
        return _STATELESS_REGISTRY[intent]
    except KeyError as exc:
        raise KeyError(
            f"no search strategy registered for intent {intent!r}; "
            f"registered intents: "
            f"{sorted(i.value for i in _STATELESS_REGISTRY) + ['relevant', 'fuzzy']}"
        ) from exc


__all__ = ["select_strategy"]
