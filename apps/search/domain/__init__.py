"""
Domain layer.

Contains the domain model and the rules that are true regardless of which
framework, transport, or storage engine is used. Nothing in this package
imports Django, Django REST Framework, or the Elasticsearch client; the
project's Phase 2.5 dependency-rule tests enforce this.

The public surface of the domain layer is re-exported here so that
consumers (the application layer, in particular) can import from a single
stable location.
"""

from apps.search.domain.exceptions import (
    DomainError,
    InvalidPaginationError,
    InvalidSearchQueryError,
)
from apps.search.domain.facets import (
    FacetBucket,
    FacetedSearchResults,
    FacetResults,
)
from apps.search.domain.filters import (
    InvalidFiltersError,
    ProductFilters,
)
from apps.search.domain.pagination import Pagination
from apps.search.domain.ports import ClusterHealthProbe
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchHit, SearchResults
from apps.search.domain.service_status import ServiceState, ServiceStatus
from apps.search.domain.sorting import (
    DEFAULT_SORT_ORDER,
    SortDirection,
    SortField,
    SortOrder,
)
from apps.search.domain.strategies import (
    ProductFacetGateway,
    ProductSearchGateway,
    ProductSuggester,
    SearchExecutionStrategy,
    SearchIntent,
)
from apps.search.domain.suggest_query import (
    InvalidSuggestQueryError,
    SuggestQuery,
)

__all__ = [
    "ClusterHealthProbe",
    "DEFAULT_SORT_ORDER",
    "DomainError",
    "FacetBucket",
    "FacetResults",
    "FacetedSearchResults",
    "InvalidFiltersError",
    "InvalidPaginationError",
    "InvalidSearchQueryError",
    "InvalidSuggestQueryError",
    "Pagination",
    "ProductFilters",
    "ProductFacetGateway",
    "ProductSearchGateway",
    "ProductSuggester",
    "SearchExecutionStrategy",
    "SearchHit",
    "SearchIntent",
    "SearchQuery",
    "SearchResults",
    "SortDirection",
    "SortField",
    "SortOrder",
    "SuggestQuery",
    "ServiceState",
    "ServiceStatus",
]
