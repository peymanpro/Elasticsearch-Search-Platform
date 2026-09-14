"""
Strategy selection.

The selector maps a ``SearchIntent`` to a concrete
``SearchExecutionStrategy``. It is the one place in the codebase that
knows the full set of strategies, which means extending the family
consists of adding one entry to the registry below -- no caller changes,
no use-case changes, no contract changes.

The registry is a plain dictionary evaluated at import time. The
strategies are stateless, so sharing instances across calls is safe and
avoids per-request allocation. If a future strategy acquires per-request
state, that becomes a design discussion for the phase that introduces it.
"""

from __future__ import annotations

from apps.search.application.strategies import (
    LiteralSearchStrategy,
    NormalizedSearchStrategy,
)
from apps.search.domain.strategies import SearchExecutionStrategy, SearchIntent

_REGISTRY: dict[SearchIntent, SearchExecutionStrategy] = {
    SearchIntent.LITERAL: LiteralSearchStrategy(),
    SearchIntent.NORMALIZED: NormalizedSearchStrategy(),
}


def select_strategy(intent: SearchIntent) -> SearchExecutionStrategy:
    """
    Return the strategy that corresponds to ``intent``.

    Raises:
        KeyError: when the intent is not recognised. This is a
            programming error, not a user error: the intent enum and the
            registry must be kept in sync within the same commit.
    """
    try:
        return _REGISTRY[intent]
    except KeyError as exc:
        raise KeyError(
            f"no search strategy registered for intent {intent!r}; "
            f"registered intents: {sorted(i.value for i in _REGISTRY)}"
        ) from exc


__all__ = ["select_strategy"]
