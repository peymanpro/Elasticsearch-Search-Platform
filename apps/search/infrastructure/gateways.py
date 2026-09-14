"""
Concrete adapters that satisfy domain gateway ports.

The Adapter Pattern is applied here to the search gateway. Elasticsearch
exposes a low-level ``search(index=..., query=..., from_=..., size=...)``
API whose request shape and response shape are not what the domain wants.
The adapter sits between them and translates in both directions.

Two entry points, corresponding to the two methods on the domain's
``ProductSearchGateway`` port:

    search(text, pagination)
        Builds a multi_match query from the text and executes it.
        Used by text-preparation strategies (Literal, Normalized).
        The original text is preserved in the returned SearchResults.

    search_query(query, pagination)
        Executes a fully composed query supplied by the caller.
        Used by the relevance strategy (Phase 9). The caller's query
        is not text-based; the SearchResults carries a placeholder
        SearchQuery whose only meaningful field is pagination.

Both entry points share response translation through a private helper.
"""

from __future__ import annotations

from typing import Any

from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchHit, SearchResults
from elasticsearch import Elasticsearch
from infrastructure.elasticsearch.query.builder import QueryBuilder
from infrastructure.elasticsearch.query.clauses import MultiMatchClause

# Fields searched by the default text-based search. Phase 9's relevance
# strategy uses its own boosted field list; this constant applies only
# to the search() method.
DEFAULT_SEARCH_FIELDS: tuple[str, ...] = (
    "name",
    "brand",
    "category",
    "description",
    "tags",
)

# The SearchResults value object carries a SearchQuery. When a caller
# supplies a composed query rather than text, there is no text to
# preserve. This sentinel is used in that case; consumers that care
# about the text read it only from the text-based path.
_COMPOSED_QUERY_TEXT = "<composed-query>"


class ElasticsearchProductSearchGateway:
    """
    Adapter from the domain's ``ProductSearchGateway`` port to the
    Elasticsearch client's ``search`` API.

    Args:
        client: An Elasticsearch client. Injecting the client (rather
            than calling ``get_client()`` internally) keeps the adapter
            unit-testable without any running cluster and keeps the
            "which client" decision in the composition root.
        index: The index or alias to search.
        search_fields: The document fields matched by the text-based
            ``search`` method. Ignored by ``search_query``.
    """

    def __init__(
        self,
        client: Elasticsearch,
        index: str,
        search_fields: tuple[str, ...] = DEFAULT_SEARCH_FIELDS,
    ) -> None:
        self._client = client
        self._index = index
        self._search_fields = search_fields

    def search(self, text: str, pagination: Pagination) -> SearchResults:
        """
        Search the catalog for ``text`` using a multi_match query.

        The original text is preserved in the returned SearchResults.
        """
        query = (
            QueryBuilder().must(MultiMatchClause(fields=self._search_fields, value=text)).build()
        )
        return self._execute(query=query, pagination=pagination, original_text=text)

    def search_query(self, query: dict[str, Any], pagination: Pagination) -> SearchResults:
        """
        Execute a fully composed query.

        The gateway forwards ``query`` to Elasticsearch without
        modification. It is the caller's responsibility to ensure the
        query is well-formed; the gateway does not validate DSL.

        The returned SearchResults carries a placeholder SearchQuery
        text, because the caller's input was a DSL dict, not text.
        """
        return self._execute(
            query=query,
            pagination=pagination,
            original_text=_COMPOSED_QUERY_TEXT,
        )

    # --------------------------------------------------------------
    # Shared implementation
    # --------------------------------------------------------------
    def _execute(
        self,
        *,
        query: dict[str, Any],
        pagination: Pagination,
        original_text: str,
    ) -> SearchResults:
        """Execute a query and translate the response into SearchResults."""
        response = self._client.search(
            index=self._index,
            query=query,
            from_=pagination.offset,
            size=pagination.page_size,
        )
        return self._to_search_results(
            original_text=original_text,
            pagination=pagination,
            response=response,
        )

    def _to_search_results(
        self,
        *,
        original_text: str,
        pagination: Pagination,
        response: dict[str, Any],
    ) -> SearchResults:
        """
        Translate an Elasticsearch search response into SearchResults.

        The response structure this method relies on is the
        Elasticsearch 8.x form:

            {
              "hits": {
                "total": {"value": <int>, "relation": "eq" | "gte"},
                "hits":  [{"_id": ..., "_score": ..., "_source": {...}}, ...]
              }
            }

        A malformed response raises KeyError, which is intentional: it
        means the client contract has been broken, and the adapter
        should not silently paper over it.
        """
        hits_container = response["hits"]
        total = int(hits_container["total"]["value"])

        hits: tuple[SearchHit, ...] = tuple(
            SearchHit(
                document_id=str(raw["_id"]),
                score=float(raw.get("_score") or 0.0),
                source=dict(raw.get("_source") or {}),
            )
            for raw in hits_container.get("hits", [])
        )

        return SearchResults(
            query=SearchQuery.create(original_text, pagination=pagination),
            total=total,
            hits=hits,
        )
