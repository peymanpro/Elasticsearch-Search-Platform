"""
Concrete adapters that satisfy domain gateway ports.

The Adapter Pattern is applied here to the search gateway. Elasticsearch
exposes a low-level ``search(index=..., query=..., from_=..., size=...)``
API whose request shape and response shape are not what the domain wants.
The adapter sits between them and translates in both directions:

    domain call                        Elasticsearch call
    ---------------------------------  ----------------------------------
    SearchQuery                        index + query DSL + from + size
    (opaque, no ES knowledge)          (bool query via QueryBuilder)

    Elasticsearch response             domain result
    ---------------------------------  ----------------------------------
    hits.hits[i]._id / _score / _source  SearchHit(document_id, score, source)
    hits.total.value                    SearchResults.total

The adapter knows about Elasticsearch. Nothing downstream of it does.
The use case ``SearchProductsUseCase`` calls ``gateway.search(text,
pagination)`` and receives ``SearchResults``; it never sees an Elasticsearch
response structure.

The adapter is deliberately narrow at Phase 3.7. It queries a single
field for the ``must`` clause and does not yet do relevance engineering,
fuzzy matching, synonyms, filters, facets, or highlighting. Those are
separate phases with their own design records. What is demonstrated here
is the *adapter shape*: domain contract in, domain result out, with the
query builder (Phase 3.6) and the managed client (Phase 1.4) in between.
"""

from __future__ import annotations

from typing import Any

from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchHit, SearchResults
from elasticsearch import Elasticsearch
from infrastructure.elasticsearch.query.builder import QueryBuilder
from infrastructure.elasticsearch.query.clauses import MatchClause

# The single field searched at Phase 3.7. Phase 6 (mapping) will decide
# which fields exist; Phase 8 will compose multi-field queries; Phase 9
# will assign boosts. For now the adapter queries one field so that the
# request path is exercised end to end.
DEFAULT_SEARCH_FIELD = "name"


class ElasticsearchProductSearchGateway:
    """
    Adapter from the domain's ``ProductSearchGateway`` port to the
    Elasticsearch client's ``search`` API.

    Args:
        client: An Elasticsearch client. Injecting the client (rather
            than calling ``get_client()`` internally) keeps the adapter
            unit-testable without any running cluster and keeps the
            "which client" decision in the composition root.
        index: The index or alias to search. At Phase 3.7 this is a
            plain string; Phase 18 will introduce an alias that points
            at a versioned physical index.
        search_field: The document field matched by the text query.
            Defaults to ``name``. Overridable so that later phases can
            change the field without modifying the adapter.
    """

    def __init__(
        self,
        client: Elasticsearch,
        index: str,
        search_field: str = DEFAULT_SEARCH_FIELD,
    ) -> None:
        self._client = client
        self._index = index
        self._search_field = search_field

    def search(self, text: str, pagination: Pagination) -> SearchResults:
        """
        Search the catalog for ``text`` and return the matching products.

        The adapter builds a ``bool`` query with a single ``must`` clause
        that matches ``text`` against ``search_field``, delegates to the
        client, and translates the response into domain value objects.
        """
        query = QueryBuilder().must(MatchClause(field=self._search_field, value=text)).build()

        response = self._client.search(
            index=self._index,
            query=query,
            from_=pagination.offset,
            size=pagination.page_size,
        )

        return self._to_search_results(text=text, pagination=pagination, response=response)

    # --------------------------------------------------------------
    # Response translation
    # --------------------------------------------------------------
    def _to_search_results(
        self,
        text: str,
        pagination: Pagination,
        response: dict[str, Any],
    ) -> SearchResults:
        """
        Translate an Elasticsearch search response into SearchResults.

        The response structure this method relies on is the Elasticsearch
        8.x form:

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
            query=SearchQuery.create(text, pagination=pagination),
            total=total,
            hits=hits,
        )
