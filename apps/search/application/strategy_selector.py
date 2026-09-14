"""
Strategy selection.

The selector maps a ``SearchIntent`` to a concrete
``SearchExecutionStrategy``. It is the one place in the codebase that
knows the full set of strategies, which means extending the family
consists of adding one entry -- no caller changes, no use-case changes,
no contract changes.

Two categories of strategy exist:

    * Stateless strategies (Literal, Normalized) are instantiated once
      at import time and shared across requests.
    * Strategies that need a collaborator (Relevant) are instantiated
      per selection, with the collaborator supplied by the caller.

The distinction matters for the Dependency Inversion Principle: the
relevance strategy cannot be constructed without a
``RelevanceQueryComposer``, and the selector must not choose a concrete
implementation of that Protocol. The caller (the composition root) does.
"""

from __future__ import annotations

from apps.search.application.strategies import (
    LiteralSearchStrategy,
    NormalizedSearchStrategy,
    RelevantSearchStrategy,
)
from apps.search.domain.strategies import (
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
) -> SearchExecutionStrategy:
    """
    Return the strategy that corresponds to ``intent``.

    Args:
        intent: The intent the caller is asking about.
        relevance_composer: Required when ``intent`` is ``RELEVANT``.
            Ignored for other intents. Supplying it is how the caller
            injects the concrete composer; the selector itself never
            chooses an implementation.

    Raises:
        ValueError: ``intent`` is RELEVANT and no composer was supplied.
        KeyError: ``intent`` is not a recognised value.
    """
    if intent is SearchIntent.RELEVANT:
        if relevance_composer is None:
            raise ValueError(
                "RELEVANT intent requires a relevance_composer; the "
                "selector does not choose a concrete implementation."
            )
        return RelevantSearchStrategy(composer=relevance_composer)

    try:
        return _STATELESS_REGISTRY[intent]
    except KeyError as exc:
        raise KeyError(
            f"no search strategy registered for intent {intent!r}; "
            f"registered intents: "
            f"{sorted(i.value for i in _STATELESS_REGISTRY) + ['relevant']}"
        ) from exc


__all__ = ["select_strategy"]
