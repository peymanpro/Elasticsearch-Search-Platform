"""
Domain contracts for search execution strategies.

The Strategy Pattern is applied here to one specific axis: how a
``SearchQuery`` is prepared before it is handed to the search backend.

    SearchIntent  -> a coarse description of what the caller is doing
    SearchExecutionStrategy
                  -> a policy that turns a SearchQuery plus a gateway
                     into SearchResults
    ProductSearchGateway
                  -> the port through which the catalog is actually
                     searched

Both ``SearchExecutionStrategy`` and ``ProductSearchGateway`` are
``typing.Protocol`` definitions, so implementations satisfy them by shape
and do not inherit from anything. This is the same convention used for
``ClusterHealthProbe`` in ``apps.search.domain.ports``.

The initial implementations (Phase 3.5) are ``LiteralSearchStrategy`` and
``NormalizedSearchStrategy``. Later phases extend the family: Phase 10
adds fuzzy strategies, Phase 11 adds synonym-aware strategies, Phase 12
adds autocomplete strategies, Phase 9 adds relevance-weighted strategies.
None of those phases will need to modify the contracts defined here.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from apps.search.domain.pagination import Pagination
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.search_result import SearchResults


class SearchIntent(StrEnum):
    """
    Coarse classification of what the caller is trying to accomplish.

    The intent is what drives strategy selection. It is a domain concept:
    it is true regardless of which search engine executes the request.
    """

    LITERAL = "literal"
    NORMALIZED = "normalized"


@runtime_checkable
class ProductSearchGateway(Protocol):
    """
    Contract for executing a prepared search against the product catalog.

    The gateway receives already-prepared text (whitespace, casing, and
    any other transformations having been decided by the strategy) and a
    ``Pagination``. It is responsible for returning ``SearchResults``.

    Implementations of this port live in the infrastructure layer. They
    are the only place that talks to Elasticsearch for search operations.
    """

    def search(self, text: str, pagination: Pagination) -> SearchResults:
        """Execute a prepared search and return the matching products."""
        ...


@runtime_checkable
class SearchExecutionStrategy(Protocol):
    """
    Contract for preparing and executing a search query.

    A strategy receives the user's original ``SearchQuery`` and a
    ``ProductSearchGateway``, prepares the query text according to its
    policy, delegates to the gateway, and returns the gateway's results.

    The strategy does not build Elasticsearch Query DSL (that is the
    QueryBuilder of Phase 3.6) and does not call Elasticsearch directly
    (that is the gateway's job, Phase 3.7).
    """

    name: str

    def execute(
        self,
        query: SearchQuery,
        gateway: ProductSearchGateway,
    ) -> SearchResults:
        """Prepare and execute a search query, returning the results."""
        ...
