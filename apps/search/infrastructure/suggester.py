"""
Elasticsearch product suggester.

Adapter from the domain's ``ProductSuggester`` port to Elasticsearch's
``bool_prefix`` query against a ``search_as_you_type`` field.

The query shape
---------------
A ``bool_prefix`` query matches the input tokens as a prefix against
the base field and its n-gram subfields. The subfields are produced
automatically by the ``search_as_you_type`` field type:

    name_suggest                whole-text tokens
    name_suggest._2gram         adjacent 2-grams
    name_suggest._3gram         adjacent 3-grams
    name_suggest._index_prefix  first 10 characters as a prefix field

The query targets ``name_suggest`` by name; Elasticsearch routes it to
the appropriate subfield based on the input's token count. A single-
token prefix uses the base field; a two-token prefix uses ``._2gram``;
a longer prefix uses ``._3gram``. This is why a ``bool_prefix`` on a
``search_as_you_type`` field is a one-line query that handles the whole
range of user input.

Suggestion deduplication
------------------------
The same product name can match via several subfields. The response
may therefore contain the same ``_source.name`` more than once. The
adapter deduplicates and preserves the ranking order (the first
occurrence wins).

See docs/17-autocomplete.md.
"""

from __future__ import annotations

from typing import Any

from apps.search.domain.suggest_query import SuggestQuery
from elasticsearch import Elasticsearch

DEFAULT_SUGGEST_FIELD = "name_suggest"
DEFAULT_SOURCE_FIELD = "name"


class ElasticsearchProductSuggester:
    """
    Adapter from ``ProductSuggester`` to Elasticsearch.

    Args:
        client: An Elasticsearch client.
        index: The index or alias to query.
        suggest_field: The ``search_as_you_type`` field name. Defaults
            to ``name_suggest``.
        source_field: The ``_source`` field whose value is returned as
            the suggestion string. Defaults to ``name``.
    """

    def __init__(
        self,
        client: Elasticsearch,
        index: str,
        suggest_field: str = DEFAULT_SUGGEST_FIELD,
        source_field: str = DEFAULT_SOURCE_FIELD,
    ) -> None:
        self._client = client
        self._index = index
        self._suggest_field = suggest_field
        self._source_field = source_field

    def suggest(self, query: SuggestQuery) -> tuple[str, ...]:
        """
        Return suggestions for ``query``.

        The result is a tuple of product names, deduplicated and in
        ranking order.
        """
        body = self._build_query(query)
        response = self._client.search(
            index=self._index,
            query=body,
            size=query.limit,
            source=[self._source_field],
        )
        return self._extract_suggestions(response)

    def _build_query(self, query: SuggestQuery) -> dict[str, Any]:
        """Return the bool_prefix query for the given SuggestQuery."""
        return {
            "multi_match": {
                "query": query.prefix,
                "type": "bool_prefix",
                "fields": [
                    self._suggest_field,
                    f"{self._suggest_field}._2gram",
                    f"{self._suggest_field}._3gram",
                ],
            }
        }

    def _extract_suggestions(self, response: dict[str, Any]) -> tuple[str, ...]:
        """
        Extract the source field from each hit, deduplicated.

        Elasticsearch may return the same document via several
        subfields. Deduplication keeps the first occurrence.
        """
        seen: set[str] = set()
        suggestions: list[str] = []
        for hit in response["hits"]["hits"]:
            source = hit.get("_source") or {}
            value = source.get(self._source_field)
            if not isinstance(value, str) or not value:
                continue
            if value in seen:
                continue
            seen.add(value)
            suggestions.append(value)
        return tuple(suggestions)


__all__ = [
    "DEFAULT_SOURCE_FIELD",
    "DEFAULT_SUGGEST_FIELD",
    "ElasticsearchProductSuggester",
]
