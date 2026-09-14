"""
Use case: execute a search that also returns a facet summary.

The caller supplies a SearchQuery (which carries text, pagination, and
filters). The use case composes a relevance query through the domain's
``RelevanceQueryComposer`` Protocol, executes it through the domain's
``ProductFacetGateway`` Protocol, and returns a FacetedSearchResults.

The use case depends on two Protocols, both defined in the domain. It
does not know which concrete composer or which concrete gateway it is
given; the composition root wires those.
"""

from __future__ import annotations

from apps.search.domain.facets import FacetedSearchResults
from apps.search.domain.search_query import SearchQuery
from apps.search.domain.strategies import (
    ProductFacetGateway,
    RelevanceQueryComposer,
)


class SearchWithFacetsUseCase:
    """Execute a search and return both a page and a facet summary."""

    def __init__(
        self,
        gateway: ProductFacetGateway,
        composer: RelevanceQueryComposer,
    ) -> None:
        self._gateway = gateway
        self._composer = composer

    def execute(self, query: SearchQuery) -> FacetedSearchResults:
        """
        Execute the query and return hits plus facets.

        The relevance composer produces the query; the gateway runs it
        and returns both a page of hits and the aggregation result over
        the same result set.
        """
        composed = self._composer.build(query.text, query.filters)
        return self._gateway.search_with_facets(
            composed,
            query.pagination,
            sort=query.sort,
        )


__all__ = ["SearchWithFacetsUseCase"]
