"""
Use case: return autocomplete suggestions.

The use case depends only on the domain's ``ProductSuggester`` port. It
validates the incoming request (which happens implicitly through
``SuggestQuery.create``) and delegates to the suggester. No caching, no
ranking adjustment, no augmentation: the suggester's output is what the
caller sees.
"""

from __future__ import annotations

from apps.search.domain.strategies import ProductSuggester
from apps.search.domain.suggest_query import SuggestQuery


class GetSuggestionsUseCase:
    """Return autocomplete suggestions for a partial input."""

    def __init__(self, suggester: ProductSuggester) -> None:
        self._suggester = suggester

    def execute(
        self,
        prefix: str,
        limit: int | None = None,
    ) -> tuple[str, ...]:
        """
        Validate the request and return suggestions.

        Raises ``InvalidSuggestQueryError`` when the prefix is empty or
        the limit is out of range. Whatever the suggester raises is
        propagated unchanged.
        """
        kwargs = {} if limit is None else {"limit": limit}
        query = SuggestQuery.create(prefix, **kwargs)
        return self._suggester.suggest(query)


__all__ = ["GetSuggestionsUseCase"]
