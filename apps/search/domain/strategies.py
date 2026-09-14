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
from apps.search.domain.suggest_query import SuggestQuery


class SearchIntent(StrEnum):
    """
    Coarse classification of what the caller is trying to accomplish.

    The intent is what drives strategy selection. It is a domain concept:
    it is true regardless of which search engine executes the request.
    """

    LITERAL = "literal"
    NORMALIZED = "normalized"
    RELEVANT = "relevant"
    FUZZY = "fuzzy"


@runtime_checkable
class ProductSearchGateway(Protocol):
    """
    Contract for executing a search against the product catalog.

    Two entry points exist because two kinds of strategy exist:

    * ``search`` -- a text-based call for strategies that decide only
      how the *text* is prepared (Literal, Normalized). The gateway
      builds the query itself.
    * ``search_query`` -- a query-based call for strategies that need
      control over the full query composition (Relevant). The caller
      supplies a complete query dictionary; the gateway executes it.

    Both methods return ``SearchResults``. Implementations live in the
    infrastructure layer and are the only place that talks to
    Elasticsearch for search operations.
    """

    def search(self, text: str, pagination: Pagination) -> SearchResults:
        """Execute a text search and return the matching products."""
        ...

    def search_query(self, query: dict, pagination: Pagination) -> SearchResults:
        """
        Execute a pre-built query and return the matching products.

        The query is expected to be a complete Elasticsearch query
        dictionary (a ``bool`` or ``function_score`` wrapper). The
        gateway forwards it to Elasticsearch without modification; the
        caller is responsible for its correctness.
        """
        ...


@runtime_checkable
class RelevanceQueryComposer(Protocol):
    """
    Contract for composing a relevance query from a text.

    The application layer's relevance strategy depends on this Protocol,
    not on any concrete composer. The composer that emits Elasticsearch
    DSL lives in the infrastructure layer; the composition root wires
    the concrete implementation into the strategy.

    Returns a complete Elasticsearch query dictionary -- bool,
    function_score, or any composition the policy requires.
    """

    def build(self, text: str) -> dict:
        """Return the complete Elasticsearch query for ``text``."""
        ...


@runtime_checkable
class FuzzyQueryComposer(Protocol):
    """
    Contract for composing a fuzzy search query from a text.

    Distinct from ``RelevanceQueryComposer`` even though the shape is
    identical: the two produce different queries for different purposes
    (fuzzy tolerance vs. relevance weighting). Keeping them separate
    documents the intent and allows either to diverge later without
    silently changing the other.
    """

    def build(self, text: str) -> dict:
        """Return the complete Elasticsearch fuzzy query for ``text``."""
        ...


@runtime_checkable
class ProductSuggester(Protocol):
    """
    Contract for returning autocomplete suggestions.

    A suggester takes a SuggestQuery (a prefix and a limit) and returns
    a tuple of suggestion strings. Each string is a complete product
    name that matches the prefix; the caller presents them to the user.

    Implementations live in the infrastructure layer. The domain does
    not know which search engine answers.
    """

    def suggest(self, query: SuggestQuery) -> tuple[str, ...]:
        """Return suggestions for a SuggestQuery."""
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
