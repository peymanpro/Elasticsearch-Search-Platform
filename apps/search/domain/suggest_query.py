"""
Suggest query value object.

Captures a caller's autocomplete request: a prefix and a maximum number
of suggestions to return. The invariants (non-empty prefix, bounded
limit) are domain rules: they hold regardless of which search engine
answers the request.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.search.domain.exceptions import DomainError

MIN_PREFIX_LENGTH = 1
MAX_PREFIX_LENGTH = 100
MIN_LIMIT = 1
MAX_LIMIT = 20
DEFAULT_LIMIT = 5


class InvalidSuggestQueryError(DomainError):
    """Raised when a suggest query violates a domain invariant."""


@dataclass(frozen=True, slots=True)
class SuggestQuery:
    """
    A request for autocomplete suggestions.

    Construct through ``SuggestQuery.create`` so that prefix stripping
    and validation are applied once.

    Attributes:
        prefix: The partial input the user has typed.
        limit: The maximum number of suggestions to return.
    """

    prefix: str
    limit: int

    @classmethod
    def create(
        cls,
        prefix: str,
        limit: int = DEFAULT_LIMIT,
    ) -> SuggestQuery:
        """
        Build a validated SuggestQuery.

        Leading and trailing whitespace is stripped from the prefix
        before validation, so a whitespace-only prefix is rejected
        rather than accepted as a one-character string.
        """
        cleaned = prefix.strip()

        if len(cleaned) < MIN_PREFIX_LENGTH:
            raise InvalidSuggestQueryError("prefix must not be empty")
        if len(cleaned) > MAX_PREFIX_LENGTH:
            raise InvalidSuggestQueryError(
                f"prefix must be at most {MAX_PREFIX_LENGTH} characters, got {len(cleaned)}",
            )
        if limit < MIN_LIMIT or limit > MAX_LIMIT:
            raise InvalidSuggestQueryError(
                f"limit must be between {MIN_LIMIT} and {MAX_LIMIT}, got {limit}",
            )

        return cls(prefix=cleaned, limit=limit)


__all__ = [
    "DEFAULT_LIMIT",
    "InvalidSuggestQueryError",
    "MAX_LIMIT",
    "MAX_PREFIX_LENGTH",
    "MIN_LIMIT",
    "MIN_PREFIX_LENGTH",
    "SuggestQuery",
]
