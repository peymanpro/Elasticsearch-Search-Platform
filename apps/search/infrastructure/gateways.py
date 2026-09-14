"""
Concrete adapters that satisfy domain gateway ports.

The Adapter Pattern is applied here to the search gateway. Elasticsearch
exposes a low-level ``search(index=..., query=..., from_=..., size=...)``
API whose request shape and response shape are not what the domain wants.
The adapter sits between them and translates in both directions.

Two entry points, corresponding to the two methods on the domain's
``ProductSearchGateway`` port:

    search(text, pagination, filters, sort)
        Builds a multi_match query from the text and executes it.

    search_query(query, pagination, sort)
        Executes a fully composed query supplied by the caller.

Every request includes a ``highlight`` block and an explicit ``sort``
clause. The sort clause always ends with a tie-breaker on
``sku.keyword`` so that pagination is deterministic across ties. When
the caller supplies a cursor-based Pagination, the gateway sends
``search_after`` instead of ``from_`` and populates the response's
``next_cursor`` from the sort values of the last hit. See
docs/18-highlighting.md and docs/20-sorting-pagination.md.
"""

from __future__ import annotations

from typing import Any

from apps.search.domain.facets import (
    FacetBucket,
    FacetedSearchResults,
    FacetResults,
)
from apps.search.domain.filters import ProductFilters
from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchHit, SearchResults
from apps.search.domain.sorting import DEFAULT_SORT_ORDER, SortOrder
from apps.search.infrastructure.filter_clauses import build_filter_clauses
from apps.search.infrastructure.sort_clauses import build_sort_clauses
from elasticsearch import Elasticsearch
from infrastructure.elasticsearch.query.builder import QueryBuilder
from infrastructure.elasticsearch.query.clauses import MultiMatchClause

DEFAULT_SEARCH_FIELDS: tuple[str, ...] = (
    "name",
    "brand",
    "category",
    "description",
    "tags",
)

HIGHLIGHT_FIELDS: tuple[str, ...] = (
    "name",
    "brand",
    "category",
    "description",
    "tags",
)

DESCRIPTION_FRAGMENT_COUNT = 3

PRE_TAG = "<em>"
POST_TAG = "</em>"

_COMPOSED_QUERY_TEXT = "<composed-query>"


class ElasticsearchProductSearchGateway:
    """
    Adapter from the domain's ``ProductSearchGateway`` port to the
    Elasticsearch client's ``search`` API.

    Args:
        client: An Elasticsearch client.
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

    def search(
        self,
        text: str,
        pagination: Pagination,
        filters: ProductFilters | None = None,
        sort: SortOrder | None = None,
    ) -> SearchResults:
        """
        Search the catalog for ``text`` using a multi_match query,
        optionally narrowed by filters and ordered by ``sort``.

        The original text is preserved in the returned SearchResults.
        """
        builder = QueryBuilder().must(MultiMatchClause(fields=self._search_fields, value=text))
        if filters is not None:
            for clause in build_filter_clauses(filters):
                builder = builder.filter_raw(clause)
        return self._execute(
            query=builder.build(),
            pagination=pagination,
            original_text=text,
            sort=sort,
        )

    def search_query(
        self,
        query: dict[str, Any],
        pagination: Pagination,
        sort: SortOrder | None = None,
    ) -> SearchResults:
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
            sort=sort,
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
        sort: SortOrder | None,
    ) -> SearchResults:
        """
        Execute a query with highlighting and a stable sort, then
        translate the response.
        """
        resolved_sort = sort or DEFAULT_SORT_ORDER

        request: dict[str, Any] = {
            "index": self._index,
            "query": query,
            "size": pagination.page_size,
            "sort": build_sort_clauses(resolved_sort),
            "highlight": self._build_highlight_block(),
        }
        if pagination.is_cursor_based:
            request["search_after"] = list(pagination.cursor or ())
        else:
            request["from_"] = pagination.offset

        response = self._client.search(**request)
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
        Elasticsearch 8.x form. Each hit may carry a ``sort`` array
        whose values match the request's sort clause; that array is
        what becomes the next_cursor.
        """
        hits_container = response["hits"]
        total = int(hits_container["total"]["value"])
        raw_hits = hits_container.get("hits", [])

        hits: tuple[SearchHit, ...] = tuple(
            SearchHit(
                document_id=str(raw["_id"]),
                score=float(raw.get("_score") or 0.0),
                source=dict(raw.get("_source") or {}),
                highlights=_extract_highlights(raw.get("highlight")),
            )
            for raw in raw_hits
        )

        next_cursor = _extract_next_cursor(
            raw_hits=raw_hits,
            returned=len(hits),
            page_size=pagination.page_size,
        )

        return SearchResults(
            query=SearchQuery.create(original_text, pagination=pagination),
            total=total,
            hits=hits,
            next_cursor=next_cursor,
        )


def _extract_next_cursor(
    *,
    raw_hits: list[dict[str, Any]],
    returned: int,
    page_size: int,
) -> tuple[Any, ...] | None:
    """
    Return the sort values of the last hit on the page, or None.

    None is returned when:

    * The page is empty (there is nothing to continue from).
    * Fewer hits were returned than requested (the end of the result
      set has been reached).
    * The last hit has no ``sort`` array (should not happen when a
      sort clause was sent, but the check keeps the contract honest).
    """
    if not raw_hits or returned < page_size:
        return None
    last = raw_hits[-1]
    sort_values = last.get("sort")
    if not isinstance(sort_values, list) or not sort_values:
        return None
    return tuple(sort_values)


def _extract_highlights(raw: Any) -> dict[str, tuple[str, ...]]:
    """
    Convert the ``highlight`` field of a raw hit into a mapping.

    The mapping is from field name to a tuple of fragments. Fields
    absent from the raw highlight are absent from the returned mapping.
    A None or non-mapping raw value yields an empty mapping.
    """
    if not isinstance(raw, dict):
        return {}
    result: dict[str, tuple[str, ...]] = {}
    for field_name, fragments in raw.items():
        if not isinstance(fragments, list):
            continue
        result[field_name] = tuple(str(f) for f in fragments)
    return result


# ---------------------------------------------------------------------------
# Facet policy
# ---------------------------------------------------------------------------
FACET_CATEGORIES_KEY = "categories"
FACET_BRANDS_KEY = "brands"
FACET_AVAILABILITY_KEY = "availability"
FACET_PRICE_RANGES_KEY = "price_ranges"

FACET_CATEGORY_FIELD = "category.keyword"
FACET_BRAND_FIELD = "brand.keyword"
FACET_AVAILABILITY_FIELD = "availability"
FACET_PRICE_FIELD = "price"

FACET_TERMS_SIZE = 20

PRICE_RANGES: tuple[dict, ...] = (
    {"key": "0-50", "to": 50.0},
    {"key": "50-100", "from": 50.0, "to": 100.0},
    {"key": "100-250", "from": 100.0, "to": 250.0},
    {"key": "250-500", "from": 250.0, "to": 500.0},
    {"key": "500+", "from": 500.0},
)


class ElasticsearchFacetGateway:
    """
    Adapter from the domain's ``ProductFacetGateway`` port to
    Elasticsearch's aggregation API.

    Shares the client and index configuration with the search gateway
    but issues a distinct request that includes an ``aggs`` block. The
    aggregations run over the same filtered result set as the query, so
    the facet counts and the returned hits describe the same documents.
    """

    def __init__(
        self,
        client: Elasticsearch,
        index: str,
    ) -> None:
        self._client = client
        self._index = index

    def search_with_facets(
        self,
        query: dict[str, Any],
        pagination: Pagination,
        sort: SortOrder | None = None,
    ) -> FacetedSearchResults:
        """Execute a query and return both a page and the facet summary."""
        resolved_sort = sort or DEFAULT_SORT_ORDER

        request: dict[str, Any] = {
            "index": self._index,
            "query": query,
            "size": pagination.page_size,
            "sort": build_sort_clauses(resolved_sort),
            "aggs": self._build_facets_block(),
            "highlight": _default_highlight_block(),
        }
        if pagination.is_cursor_based:
            request["search_after"] = list(pagination.cursor or ())
        else:
            request["from_"] = pagination.offset

        response = self._client.search(**request)
        search = self._to_search_results(pagination=pagination, response=response)
        facets = _parse_facets(response.get("aggregations") or {})
        return FacetedSearchResults(search=search, facets=facets)

    @staticmethod
    def _build_facets_block() -> dict[str, Any]:
        """Return the ``aggs`` block sent with every faceted request."""
        return {
            FACET_CATEGORIES_KEY: {
                "terms": {"field": FACET_CATEGORY_FIELD, "size": FACET_TERMS_SIZE}
            },
            FACET_BRANDS_KEY: {"terms": {"field": FACET_BRAND_FIELD, "size": FACET_TERMS_SIZE}},
            FACET_AVAILABILITY_KEY: {
                "terms": {"field": FACET_AVAILABILITY_FIELD, "size": FACET_TERMS_SIZE}
            },
            FACET_PRICE_RANGES_KEY: {
                "range": {"field": FACET_PRICE_FIELD, "ranges": list(PRICE_RANGES)}
            },
        }

    def _to_search_results(
        self,
        *,
        pagination: Pagination,
        response: dict[str, Any],
    ) -> SearchResults:
        """Translate the hits portion of a faceted response."""
        hits_container = response["hits"]
        total = int(hits_container["total"]["value"])
        raw_hits = hits_container.get("hits", [])
        hits: tuple[SearchHit, ...] = tuple(
            SearchHit(
                document_id=str(raw["_id"]),
                score=float(raw.get("_score") or 0.0),
                source=dict(raw.get("_source") or {}),
                highlights=_extract_highlights(raw.get("highlight")),
            )
            for raw in raw_hits
        )
        next_cursor = _extract_next_cursor(
            raw_hits=raw_hits,
            returned=len(hits),
            page_size=pagination.page_size,
        )
        return SearchResults(
            query=SearchQuery.create(_COMPOSED_QUERY_TEXT, pagination=pagination),
            total=total,
            hits=hits,
            next_cursor=next_cursor,
        )


def _default_highlight_block() -> dict[str, Any]:
    """Return the shared highlight block used by both gateways."""
    return ElasticsearchProductSearchGateway._build_highlight_block()


def _parse_facets(aggregations: dict[str, Any]) -> FacetResults:
    """Convert the ``aggregations`` portion of a response into FacetResults."""
    return FacetResults(
        categories=_parse_terms_buckets(aggregations.get(FACET_CATEGORIES_KEY)),
        brands=_parse_terms_buckets(aggregations.get(FACET_BRANDS_KEY)),
        availability=_parse_terms_buckets(aggregations.get(FACET_AVAILABILITY_KEY)),
        price_ranges=_parse_range_buckets(aggregations.get(FACET_PRICE_RANGES_KEY)),
    )


def _parse_terms_buckets(raw: Any) -> tuple[FacetBucket, ...]:
    """Return a tuple of FacetBucket from a terms aggregation response."""
    if not isinstance(raw, dict):
        return ()
    buckets = raw.get("buckets")
    if not isinstance(buckets, list):
        return ()
    return tuple(
        FacetBucket(value=str(b.get("key", "")), count=int(b.get("doc_count", 0)))
        for b in buckets
        if isinstance(b, dict)
    )


def _parse_range_buckets(raw: Any) -> tuple[FacetBucket, ...]:
    """Return a tuple of FacetBucket from a range aggregation response."""
    if not isinstance(raw, dict):
        return ()
    buckets = raw.get("buckets")
    if not isinstance(buckets, list):
        return ()
    result: list[FacetBucket] = []
    for b in buckets:
        if not isinstance(b, dict):
            continue
        key = b.get("key")
        if key is None:
            from_v = b.get("from")
            to_v = b.get("to")
            key = f"{from_v or 0}-{to_v if to_v is not None else '+'}"
        result.append(FacetBucket(value=str(key), count=int(b.get("doc_count", 0))))
    return tuple(result)
