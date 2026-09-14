"""
Facet value objects.

A facet summarizes a result set along one dimension. A bucket is one
value of that dimension together with the number of documents that
carry it. The four facets the platform exposes are:

    categories    -- one bucket per category
    brands        -- one bucket per brand (top N by count)
    availability  -- one bucket per availability state
    price_ranges  -- one bucket per fixed price band

A FacetResults carries all four. A FacetedSearchResults carries a
FacetResults together with the SearchResults it was computed from --
they come from the same Elasticsearch request and are consistent with
each other. See docs/19-filtering-facets.md section 4.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.search.domain.search_result import SearchResults


@dataclass(frozen=True, slots=True)
class FacetBucket:
    """
    A single value of a facet, with the count of documents that carry it.

    Attributes:
        value: The bucket's label. For a terms facet it is the field
            value ("Sony"); for a range facet it is the human-readable
            band ("100-250").
        count: The number of documents in the current result set that
            fall in this bucket.
    """

    value: str
    count: int


@dataclass(frozen=True, slots=True)
class FacetResults:
    """
    The four facets computed over a single search.

    Each facet is a tuple of buckets in the order Elasticsearch
    returned them (by count descending for terms facets; by the
    declared band order for the range facet).
    """

    categories: tuple[FacetBucket, ...]
    brands: tuple[FacetBucket, ...]
    availability: tuple[FacetBucket, ...]
    price_ranges: tuple[FacetBucket, ...]

    @property
    def is_empty(self) -> bool:
        """
        True if no bucket in any facet has a positive count.

        This is different from "every facet tuple is empty". A range
        aggregation returns every declared band regardless of whether
        any document falls in it, so a search with zero matches still
        produces range buckets -- all with count 0. Those are not
        meaningful facet data; the result is effectively empty. A
        consumer that wants to render the declared bands reads the
        buckets directly; a consumer that wants to know whether
        there is anything to show reads is_empty.
        """
        return not any(
            bucket.count > 0
            for buckets in (
                self.categories,
                self.brands,
                self.availability,
                self.price_ranges,
            )
            for bucket in buckets
        )


@dataclass(frozen=True, slots=True)
class FacetedSearchResults:
    """
    A search page together with the facets computed over the same query.

    Both parts come from one Elasticsearch request. They describe the
    same result set: the hits are a page of it; the facets summarize it.
    """

    search: SearchResults
    facets: FacetResults


__all__ = [
    "FacetBucket",
    "FacetResults",
    "FacetedSearchResults",
]
