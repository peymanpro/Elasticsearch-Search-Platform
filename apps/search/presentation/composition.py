"""
Composition root for the presentation layer.

This module is the single place where concrete infrastructure adapters
are chosen and injected into application use cases. Views ask the
composition root for a ready-to-use use case; they do not construct use
cases or adapters themselves.

Two properties make this the right place for wiring:

    * Dependency Inversion. The use cases depend on domain Protocols.
      This module is the only place where concrete implementations of
      those Protocols are chosen.
    * Test injection. Every builder accepts an optional override for
      its adapter. Production callers use no arguments and get the
      real Elasticsearch-backed adapter; tests supply a fake.

Which index the search adapters target
--------------------------------------
Every search adapter is constructed with the alias ``products``, not
with a physical index name. The alias resolves at request time to
whichever physical index the lifecycle operations (Phase 18) currently
have pointed it at. Reindexing never requires a code change here, only
an alias switch.

Which Elasticsearch client is used
----------------------------------
Every adapter that talks to Elasticsearch obtains its client from
``infrastructure.elasticsearch.client.get_client``. The client is a
process-wide singleton with a shared connection pool. Test injection
overrides this at the builder level, not by patching the client
package.
"""

from __future__ import annotations

from apps.search.application.bulk_index import BulkIndexProductsUseCase
from apps.search.application.explain_score import ExplainScoreUseCase
from apps.search.application.get_service_status import GetServiceStatusUseCase
from apps.search.application.get_suggestions import GetSuggestionsUseCase
from apps.search.application.search_products import SearchProductsUseCase
from apps.search.application.search_with_facets import SearchWithFacetsUseCase
from apps.search.domain.ports import ClusterHealthProbe
from apps.search.domain.strategies import (
    FuzzyQueryComposer,
    ProductExplainer,
    ProductFacetGateway,
    ProductIndexer,
    ProductSearchGateway,
    ProductSuggester,
    RelevanceQueryComposer,
)
from apps.search.infrastructure.bulk_indexer import ElasticsearchBulkIndexer
from apps.search.infrastructure.explainer import ElasticsearchProductExplainer
from apps.search.infrastructure.fuzzy import ElasticsearchFuzzyQueryComposer
from apps.search.infrastructure.gateways import (
    ElasticsearchFacetGateway,
    ElasticsearchProductSearchGateway,
)
from apps.search.infrastructure.probes import ElasticsearchClusterHealthProbe
from apps.search.infrastructure.relevance import FIELD_BOOSTS, RelevanceQueryBuilder
from apps.search.infrastructure.suggester import ElasticsearchProductSuggester
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.indices import INDEX_ALIAS

# The alias every search adapter targets. It is not a physical index
# name; it resolves at request time to the current version. See
# docs/23-index-lifecycle.md section 4.
SEARCH_INDEX = INDEX_ALIAS


# ---------------------------------------------------------------------------
# Service status (Phase 2.4)
# ---------------------------------------------------------------------------
def build_get_service_status_use_case(
    probe: ClusterHealthProbe | None = None,
) -> GetServiceStatusUseCase:
    """Build the use case the service-root endpoint depends on."""
    adapter: ClusterHealthProbe = probe if probe is not None else ElasticsearchClusterHealthProbe()
    return GetServiceStatusUseCase(cluster_health_probe=adapter)


# ---------------------------------------------------------------------------
# Search (Phase 19.1, 19.3)
# ---------------------------------------------------------------------------
def build_search_products_use_case(
    gateway: ProductSearchGateway | None = None,
    relevance_composer: RelevanceQueryComposer | None = None,
    fuzzy_composer: FuzzyQueryComposer | None = None,
) -> SearchProductsUseCase:
    """
    Build the use case the search endpoint depends on.

    All three collaborators are optional and default to concrete
    Elasticsearch-backed implementations. A test can supply a fake
    gateway to exercise the search flow without a cluster.
    """
    resolved_gateway: ProductSearchGateway = (
        gateway
        if gateway is not None
        else ElasticsearchProductSearchGateway(client=get_client(), index=SEARCH_INDEX)
    )
    resolved_relevance: RelevanceQueryComposer = (
        relevance_composer if relevance_composer is not None else RelevanceQueryBuilder()
    )
    resolved_fuzzy: FuzzyQueryComposer = (
        fuzzy_composer
        if fuzzy_composer is not None
        else ElasticsearchFuzzyQueryComposer(fields=FIELD_BOOSTS)
    )
    return SearchProductsUseCase(
        gateway=resolved_gateway,
        relevance_composer=resolved_relevance,
        fuzzy_composer=resolved_fuzzy,
    )


def build_search_with_facets_use_case(
    gateway: ProductFacetGateway | None = None,
    composer: RelevanceQueryComposer | None = None,
) -> SearchWithFacetsUseCase:
    """
    Build the use case the faceted search path of the search endpoint
    depends on. Called when the request sets ``include_facets``.
    """
    resolved_gateway: ProductFacetGateway = (
        gateway
        if gateway is not None
        else ElasticsearchFacetGateway(client=get_client(), index=SEARCH_INDEX)
    )
    resolved_composer: RelevanceQueryComposer = (
        composer if composer is not None else RelevanceQueryBuilder()
    )
    return SearchWithFacetsUseCase(gateway=resolved_gateway, composer=resolved_composer)


# ---------------------------------------------------------------------------
# Autocomplete (Phase 19.2)
# ---------------------------------------------------------------------------
def build_get_suggestions_use_case(
    suggester: ProductSuggester | None = None,
) -> GetSuggestionsUseCase:
    """Build the use case the suggest endpoint depends on."""
    resolved: ProductSuggester = (
        suggester
        if suggester is not None
        else ElasticsearchProductSuggester(client=get_client(), index=SEARCH_INDEX)
    )
    return GetSuggestionsUseCase(suggester=resolved)


# ---------------------------------------------------------------------------
# Explain (Phase 19.4)
# ---------------------------------------------------------------------------
def build_explain_score_use_case(
    explainer: ProductExplainer | None = None,
    composer: RelevanceQueryComposer | None = None,
) -> ExplainScoreUseCase:
    """Build the use case the explain endpoint depends on."""
    resolved_explainer: ProductExplainer = (
        explainer
        if explainer is not None
        else ElasticsearchProductExplainer(client=get_client(), index=SEARCH_INDEX)
    )
    resolved_composer: RelevanceQueryComposer = (
        composer if composer is not None else RelevanceQueryBuilder()
    )
    return ExplainScoreUseCase(explainer=resolved_explainer, composer=resolved_composer)


# ---------------------------------------------------------------------------
# Bulk index (used by the reindex management command, not by HTTP)
# ---------------------------------------------------------------------------
def build_bulk_index_use_case(
    indexer: ProductIndexer | None = None,
    index: str | None = None,
) -> BulkIndexProductsUseCase:
    """
    Build the use case the reindex command depends on.

    Unlike the search adapters, this one targets a specific physical
    index name rather than the alias: bulk indexing needs to write
    into a known destination, and the destination during a reindex is
    the new version, not the live one.
    """
    resolved_index = index or SEARCH_INDEX
    resolved: ProductIndexer = (
        indexer
        if indexer is not None
        else ElasticsearchBulkIndexer(client=get_client(), index=resolved_index)
    )
    return BulkIndexProductsUseCase(indexer=resolved)


# ---------------------------------------------------------------------------
# Health summary (used by GET /api/health/)
# ---------------------------------------------------------------------------
def build_health_summary() -> dict:
    """
    Assemble the health response payload.

    This function lives in the composition root rather than the view
    because it must consult the top-level Elasticsearch client package
    (``get_client``, ``cluster_health``, ``INDEX_ALIAS``) and the
    index lifecycle manager. The presentation layer's views are not
    permitted to import those modules directly; the composition root
    is the one sanctioned place where that knowledge lives.

    The returned dict is the shape the response serializer validates.
    Failures are captured as "degraded" or "unhealthy" rather than
    raised: the endpoint exists to report them.
    """
    from apps.search.presentation.composition import (  # local import breaks a cycle
        SEARCH_INDEX,
    )
    from infrastructure.elasticsearch.health import cluster_health
    from infrastructure.elasticsearch.indices.manager import get_alias_target

    # --- Cluster ---
    try:
        cluster = cluster_health()
        cluster_payload = {
            "name": str(cluster.get("cluster_name", "")),
            "status": str(cluster.get("status", "unknown")),
            "number_of_nodes": int(cluster.get("number_of_nodes", 0)),
        }
        reachable = True
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        cluster_payload = {
            "name": "",
            "status": "unreachable",
            "number_of_nodes": 0,
        }
        reachable = False
        _ = exc  # retain for potential logging in a later phase

    # --- Alias and count ---
    points_at = None
    document_count = 0
    if reachable:
        points_at = get_alias_target(SEARCH_INDEX)
        if points_at is not None:
            try:
                get_client().indices.refresh(index=SEARCH_INDEX)
                count_response = get_client().count(index=SEARCH_INDEX)
                document_count = int(count_response["count"])
            except Exception:  # noqa: BLE001 - degraded, not failed
                document_count = 0

    # --- Overall classification ---
    if not reachable:
        overall = "unhealthy"
    elif (
        cluster_payload["status"] not in {"green", "yellow"}
        or points_at is None
        or document_count == 0
    ):
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "cluster": cluster_payload,
        "index": {
            "alias": SEARCH_INDEX,
            "points_at": points_at,
            "document_count": document_count,
        },
    }


__all__ = [
    "SEARCH_INDEX",
    "build_bulk_index_use_case",
    "build_explain_score_use_case",
    "build_get_service_status_use_case",
    "build_get_suggestions_use_case",
    "build_health_summary",
    "build_search_products_use_case",
    "build_search_with_facets_use_case",
]
