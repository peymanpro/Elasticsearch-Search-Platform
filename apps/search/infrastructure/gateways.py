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

    search_query(query, pagination)
        Executes a fully composed query supplied by the caller.
        Used by the relevance, fuzzy, and other strategies that build
        their own queries.

Every request includes a ``highlight`` block. The gateway does not
expose a "search without highlights" method: highlighting is cheap for
the small result pages the platform returns, and having one code path
keeps the adapter simple. See docs/18-highlighting.md section 5.3.
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

# Fields highlighted in every response. Same set as the text-searchable
# fields. Filterable and numeric fields are not highlighted: a filter
# match produces no fragment, and a number cannot be emphasized usefully.
HIGHLIGHT_FIELDS: tuple[str, ...] = (
    "name",
    "brand",
    "category",
    "description",
    "tags",
)

# How many fragments to request for the description field. The
# description is the longest field and the one where a term can appear
# in several places. Other fields default to a single fragment (which
# for a short field is the whole field).
DESCRIPTION_FRAGMENT_COUNT = 3

# Pre- and post-tags wrap the matched terms in each fragment. The
# platform uses <em> for conservative HTML-shaped output; a caller that
# renders in a non-HTML context strips or transforms them. Declared
# explicitly so a future change is one edit in one place.
PRE_TAG = "<em>"
POST_TAG = "</em>"

# The SearchResults value object carries a SearchQuery. When a caller
# supplies a composed query rather than text, there is no text to
# preserve. This sentinel is used in that case.
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
        """Execute a query with highlighting and translate the response."""
        response = self._client.search(
            index=self._index,
            query=query,
            from_=pagination.offset,
            size=pagination.page_size,
            highlight=self._build_highlight_block(),
        )
        return self._to_search_results(
            original_text=original_text,
            pagination=pagination,
            response=response,
        )

    @staticmethod
    def _build_highlight_block() -> dict[str, Any]:
        """
        Return the ``highlight`` block sent with every request.

        Every searchable field is named. The description field requests
        multiple fragments; the other fields use the default (one
        fragment, which for a short field is the whole field).
        """
        fields: dict[str, dict[str, Any]] = {}
        for field_name in HIGHLIGHT_FIELDS:
            if field_name == "description":
                fields[field_name] = {"number_of_fragments": DESCRIPTION_FRAGMENT_COUNT}
            else:
                fields[field_name] = {}
        return {
            "fields": fields,
            "pre_tags": [PRE_TAG],
            "post_tags": [POST_TAG],
        }

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
                "hits":  [
                  {
                    "_id": ..., "_score": ..., "_source": {...},
                    "highlight": {"field": ["fragment", ...], ...}
                  },
                  ...
                ]
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
                highlights=_extract_highlights(raw.get("highlight")),
            )
            for raw in hits_container.get("hits", [])
        )

        return SearchResults(
            query=SearchQuery.create(original_text, pagination=pagination),
            total=total,
            hits=hits,
        )


def _extract_highlights(raw: Any) -> dict[str, tuple[str, ...]]:
    """
    Convert the ``highlight`` field of a raw hit into a mapping.

    The mapping is from field name to a tuple of fragments. Fields
    absent from the raw highlight are absent from the returned mapping,
    not present with an empty tuple. A None or non-mapping raw value
    yields an empty mapping.
    """
    if not isinstance(raw, dict):
        return {}
    result: dict[str, tuple[str, ...]] = {}
    for field_name, fragments in raw.items():
        if not isinstance(fragments, list):
            continue
        result[field_name] = tuple(str(f) for f in fragments)
    return result
