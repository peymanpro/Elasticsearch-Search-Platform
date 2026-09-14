"""
Search API views.

Every view has the same shape: validate the HTTP request through a
serializer, build the domain value objects the use case needs, call the
use case, and serialize the result. No view contains search logic; no
view talks to Elasticsearch directly.

The health endpoint is the one exception to "no view touches
infrastructure": it calls a single assembler function on the
composition root, which in turn knows about the top-level Elasticsearch
package. The view itself does not.

See docs/24-search-api.md.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.search.domain.facets import FacetedSearchResults
from apps.search.domain.filters import ProductFilters
from apps.search.domain.pagination import DEFAULT_PAGE_SIZE, Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.sorting import SortOrder
from apps.search.domain.strategies import SearchIntent
from apps.search.presentation.composition import (
    build_explain_score_use_case,
    build_get_service_status_use_case,
    build_get_suggestions_use_case,
    build_health_summary,
    build_search_products_use_case,
    build_search_with_facets_use_case,
)
from apps.search.presentation.serializers import (
    ExplainRequestSerializer,
    ExplainResponseSerializer,
    HealthResponseSerializer,
    SearchRequestSerializer,
    SearchResponseSerializer,
    ServiceRootResponseSerializer,
    SuggestRequestSerializer,
    SuggestResponseSerializer,
)


# ---------------------------------------------------------------------------
# Service root
# ---------------------------------------------------------------------------
class ServiceRootView(APIView):
    """
    Return the service identity and a coarse status marker.

    Status is derived from the reachability of the search backend.
    """

    @extend_schema(
        responses=ServiceRootResponseSerializer,
        description=(
            "Return the service identity and a coarse status marker. "
            "Used by smoke tests and by infrastructure health probes."
        ),
        tags=["service"],
    )
    def get(self, request: Request) -> Response:
        status = build_get_service_status_use_case().execute()
        return Response(
            {
                "service": status.service_name,
                "status": status.state.value,
            }
        )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
class SearchView(APIView):
    """Search the catalog with filters, sort, facets, and pagination."""

    @extend_schema(
        request=SearchRequestSerializer,
        responses=SearchResponseSerializer,
        description=(
            "Search the product catalog. Supports filtering, business "
            "sorting, cursor and offset pagination, highlighting, and "
            "(optionally) faceted navigation."
        ),
        tags=["search"],
    )
    def post(self, request: Request) -> Response:
        serializer = SearchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        query = _build_search_query(validated)
        include_facets = validated.get("include_facets", False)

        if include_facets:
            use_case = build_search_with_facets_use_case()
            faceted: FacetedSearchResults = use_case.execute(query)
            payload = _search_response_payload(
                query=query,
                total=faceted.search.total,
                hits=faceted.search.hits,
                next_cursor=faceted.search.next_cursor,
                facets=faceted.facets,
            )
        else:
            use_case = build_search_products_use_case()
            results = use_case.execute(query, intent=SearchIntent.RELEVANT)
            payload = _search_response_payload(
                query=query,
                total=results.total,
                hits=results.hits,
                next_cursor=results.next_cursor,
                facets=None,
            )

        return Response(SearchResponseSerializer(payload).data)


# ---------------------------------------------------------------------------
# Suggest
# ---------------------------------------------------------------------------
class SuggestView(APIView):
    """Return autocomplete suggestions for a prefix."""

    @extend_schema(
        parameters=[SuggestRequestSerializer],
        responses=SuggestResponseSerializer,
        description="Return autocomplete suggestions for a partial query.",
        tags=["search"],
    )
    def get(self, request: Request) -> Response:
        serializer = SuggestRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        prefix = validated["q"]
        limit = validated.get("limit")

        use_case = build_get_suggestions_use_case()
        suggestions = use_case.execute(prefix, limit=limit) if limit else use_case.execute(prefix)

        return Response(
            SuggestResponseSerializer({"prefix": prefix, "suggestions": list(suggestions)}).data
        )


# ---------------------------------------------------------------------------
# Explain
# ---------------------------------------------------------------------------
class ExplainView(APIView):
    """Explain why a document matched a query."""

    @extend_schema(
        request=ExplainRequestSerializer,
        responses=ExplainResponseSerializer,
        description=(
            "Return the scoring breakdown for a (query, document_id) "
            "pair. If the document does not match, matched is false and "
            "explanation is null."
        ),
        tags=["search"],
    )
    def post(self, request: Request) -> Response:
        serializer = ExplainRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        use_case = build_explain_score_use_case()
        result = use_case.execute(validated["query"], validated["document_id"])

        payload = {
            "matched": result.matched,
            "explanation": _explanation_to_dict(result.explanation),
        }
        return Response(ExplainResponseSerializer(payload).data)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class HealthView(APIView):
    """Report cluster and index health. See docs/24 section 6."""

    @extend_schema(
        responses=HealthResponseSerializer,
        description=(
            "Report the platform's ability to serve searches. The "
            "status is healthy when the cluster is reachable, the "
            "alias resolves, and the index has documents; degraded "
            "when one of those is false; unhealthy when the cluster "
            "is unreachable."
        ),
        tags=["service"],
    )
    def get(self, request: Request) -> Response:
        payload = build_health_summary()
        return Response(HealthResponseSerializer(payload).data)


# ---------------------------------------------------------------------------
# Request -> domain construction
# ---------------------------------------------------------------------------
def _build_search_query(validated: dict[str, Any]) -> SearchQuery:
    """
    Build a domain SearchQuery from a validated request body.

    Domain validation runs here, at construction. A domain error
    raised by any of the value objects propagates up and is translated
    to an HTTP 400 by the presentation exception handler.
    """
    pagination = _build_pagination(validated)
    filters = _build_filters(validated.get("filters"))
    sort = _build_sort(validated.get("sort"))
    return SearchQuery.create(
        text=validated["query"],
        pagination=pagination,
        filters=filters,
        sort=sort,
    )


def _build_pagination(validated: dict[str, Any]) -> Pagination:
    cursor = validated.get("cursor")
    page_size = validated.get("page_size") or DEFAULT_PAGE_SIZE
    if cursor is not None:
        return Pagination.from_cursor(cursor=tuple(cursor), page_size=page_size)
    return Pagination(page=validated.get("page", 1), page_size=page_size)


def _build_filters(raw: dict[str, Any] | None) -> ProductFilters:
    if not raw:
        return ProductFilters.create()
    return ProductFilters.create(**raw)


def _build_sort(raw: dict[str, Any] | None) -> SortOrder:
    if not raw:
        return SortOrder.create()
    return SortOrder.create(
        field=raw.get("field"),
        direction=raw.get("direction"),
    )


# ---------------------------------------------------------------------------
# Domain -> response payload construction
# ---------------------------------------------------------------------------
def _search_response_payload(
    *,
    query: SearchQuery,
    total: int,
    hits: tuple[Any, ...],
    next_cursor: tuple[Any, ...] | None,
    facets: Any | None,
) -> dict[str, Any]:
    """Assemble the dict that the response serializer validates."""
    payload: dict[str, Any] = {
        "query": query.text,
        "total": total,
        "page": None if query.pagination.is_cursor_based else query.pagination.page,
        "page_size": query.pagination.page_size,
        "returned": len(hits),
        "has_more": _has_more(query, total, len(hits), next_cursor),
        "next_cursor": list(next_cursor) if next_cursor is not None else None,
        "hits": [_hit_payload(hit) for hit in hits],
    }
    if facets is not None:
        payload["facets"] = {
            "categories": [{"value": b.value, "count": b.count} for b in facets.categories],
            "brands": [{"value": b.value, "count": b.count} for b in facets.brands],
            "availability": [{"value": b.value, "count": b.count} for b in facets.availability],
            "price_ranges": [{"value": b.value, "count": b.count} for b in facets.price_ranges],
        }
    return payload


def _hit_payload(hit: Any) -> dict[str, Any]:
    return {
        "id": hit.document_id,
        "score": hit.score,
        "source": dict(hit.source),
        "highlights": {field: list(frags) for field, frags in hit.highlights.items()},
    }


def _has_more(
    query: SearchQuery,
    total: int,
    returned: int,
    next_cursor: tuple[Any, ...] | None,
) -> bool:
    if next_cursor is not None:
        return True
    if query.pagination.is_cursor_based:
        return False
    return query.pagination.offset + returned < total


def _explanation_to_dict(node: Any | None) -> dict[str, Any] | None:
    """Recursively convert a ScoreExplanation into a JSON-ready dict."""
    if node is None:
        return None
    return {
        "value": node.value,
        "description": node.description,
        "details": [_explanation_to_dict(child) for child in node.details],
    }
