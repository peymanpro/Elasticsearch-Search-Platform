# Filtering and Faceted Search

## 1. Purpose

This document specifies how the platform narrows and summarizes
search results. It covers the roadmap sub-phases:

    * 14.1 -- Category filtering
    * 14.2 -- Brand filtering
    * 14.3 -- Price range
    * 14.4 -- Rating range
    * 14.5 -- Availability
    * 14.6 -- Terms aggregation
    * 14.7 -- Range aggregation
    * 14.8 -- Combined facets

## 2. The Problem

A shopper who has typed "wireless headphones" into a search box does
not want every wireless headphone ever indexed. They want to narrow
the list to the ones they would actually buy: the ones in their
budget, in stock, from a brand they recognize, with the rating they
require. They want to see *how many* results match each further
narrowing, so they can decide which narrowing to apply.

Two distinct mechanisms serve this:

* **Filtering** reduces the result set. A filter is a predicate:
  "only documents whose brand is Sony".
* **Faceting** counts the result set by dimension: "of the current
  results, 12 are Sony, 8 are JBL, 5 are Anker".

The two interact: facets are computed over the filtered results, so
the counts reflect the current filters. Section 3 covers filtering;
Section 4 covers faceting; Section 5 covers their interaction.

## 3. Filtering (14.1-14.5)

### 3.1 The five dimensions

| Dimension | Field | Query type | Reason |
|---|---|---|---|
| Category | category.keyword | term | Exact category name; no analysis |
| Brand | brand.keyword | term | Exact brand name; no analysis |
| Availability | availability | term | Enum value; no analysis |
| Price range | price | range | Numeric bounds |
| Rating range | rating | range | Numeric bounds |

### 3.2 Why filter clauses, not must clauses

Elasticsearch distinguishes two kinds of clause inside a `bool`:

* `must` -- required, contributes to score.
* `filter` -- required, does not contribute to score.

A filter that does not change the score is the correct choice for a
narrowing predicate. Three reasons:

1. **Relevance should be about text.** A user who filters by
   category=Electronics is not asking the platform to rank Sony
   higher than JBL; they are asking it to exclude everything else.
   Scoring should reflect the text query alone.
2. **Filter clauses are cacheable.** Elasticsearch caches filter
   results in a bitset. A term filter that many queries share (a
   popular category) is computed once and reused. Must clauses are
   not cacheable in the same way because their score contribution
   is per-query.
3. **Symmetry with faceting.** A facet is a filter applied with an
   extra aggregation. Using the same clause type for both keeps the
   composition consistent.

### 3.3 The filter value object

Filters are represented by a frozen `ProductFilters` value object in
the domain layer. Its fields are all optional:

    category:     str | None
    brand:        str | None
    availability: str | None
    price_min:    float | None
    price_max:    float | None
    rating_min:   float | None
    rating_max:   float | None

A filter with all fields None is equivalent to "no filters". This
is expressed through ``has_any()`` rather than through a separate
"empty filters" type.

### 3.4 Why a value object, not a dictionary

A dictionary of filter criteria would work. It is rejected for the
same reason as the other value objects in this domain:

* It documents the supported dimensions in one place.
* It rejects typos: `filters["catagory"]` would silently do nothing;
  `filters.category` fails at import time.
* It is testable in isolation, without a cluster.
* It keeps the set of filter dimensions a closed vocabulary, as the
  product model already does.

### 3.5 Range validation

The value object rejects:

* A price_min greater than a price_max
* A rating_min greater than a rating_max
* A rating outside [0.0, 5.0]
* A negative price

The rejection happens at construction time, so an invalid filter can
never reach the gateway. This mirrors the pattern established for
`Pagination`, `SearchQuery`, and `SuggestQuery`.

## 4. Faceting (14.6-14.8)

### 4.1 What a facet is

A facet is a summary of a result set along one dimension. For a
category facet, the summary is a list of categories with a count
for each:

    Category:
      Electronics        47
      Home and Kitchen   18
      Office              9

Each line is a **bucket** -- a value and the number of documents
that carry that value. The UI renders the buckets as clickable
checkboxes or links, and the count tells the user what they would
get by clicking.

### 4.2 The three facets

| Facet | Field | Aggregation type | Reason |
|---|---|---|---|
| Brands | brand.keyword | terms | Low-cardinality keyword; top-N by count |
| Categories | category.keyword | terms | Low-cardinality keyword; top-N by count |
| Availability | availability | terms | Small closed set |
| Price | price | range (fixed bands) | Continuous; bands are more useful than distinct values |

### 4.3 Terms aggregation details

A `terms` aggregation counts documents per distinct value of a
field. Two parameters matter:

**`size`.** The number of buckets to return. A brand facet might
have hundreds of distinct values; only the top 20 by count are
useful to display. The default is 10; the platform uses 20 to give
the UI a fuller picture without overwhelming it.

**`order`.** How buckets are sorted. The default is by count
descending, which is what a user expects ("show me the biggest
brands first"). No override is applied.

A `terms` aggregation over a text field would produce one bucket
per analyzed token -- a mess. The facet fields are keyword-typed
(`brand.keyword`, `category.keyword`, `availability`), which is the
exact reason those keyword subfields exist in the mapping.

### 4.4 Range aggregation details

Price is continuous. A `terms` aggregation over price would produce
one bucket per distinct price -- potentially thousands. A `range`
aggregation defines fixed bands:

    0-50, 50-100, 100-250, 250-500, 500+

The bands are chosen to be meaningful for the catalog. They are not
derived algorithmically. If a future catalog has a very different
price distribution, the bands are re-chosen by editing one place in
the code, with a recorded rationale.

### 4.5 Why not a filter-specific aggregation

A common faceting pattern is: "for each facet, compute counts
excluding the filter on that facet." This lets a user see the count
they would get by switching from "Sony" to "JBL" without losing the
context of the other active filters.

The platform does not implement this refinement at Phase 14. It is
a UX optimization that adds significant complexity: each facet
requires its own filtered query, so the number of queries grows
with the number of facets. The platform returns counts under the
current full filter set, which is the standard behavior of most
e-commerce search boxes.

If the platform ever needs the richer behavior, it is a change to
the facet gateway method, not to the domain model. Recorded here as
a known simplification.

## 5. The Interaction (14.8)

### 5.1 Facets reflect the filters

When a user applies a filter, the next search must:

1. Apply the filter to the search query (narrowing the result set).
2. Compute facets over the narrowed result set (so the counts
   reflect what the user sees).

Both happen in the same Elasticsearch request: the query and the
aggregations are separate top-level keys in the request body, and
the aggregations run over the hits the query returned.

    {
      "query": { ... the filtered search ... },
      "aggs": {
        "brands":       { "terms": { "field": "brand.keyword", "size": 20 } },
        "categories":   { "terms": { "field": "category.keyword", "size": 20 } },
        "availability": { "terms": { "field": "availability", "size": 10 } },
        "price_ranges": { "range": { "field": "price", "ranges": [...] } }
      }
    }

### 5.2 Why not a separate request

A single request guarantees consistency: the counts and the hits
reflect the same index state and the same filter set. Two requests
could see the index between two writes and disagree. The single
request is also faster: one round trip and one query plan instead
of two.

### 5.3 The response shape

The platform carries the facets alongside the search page. Two
value objects exist:

* `FacetResults` -- the four facets, each a tuple of buckets.
* `FacetedSearchResults` -- a `SearchResults` plus a `FacetResults`.

Splitting the two is deliberate: most consumers only want the
search page and do not need to know that facets exist. A consumer
that wants both gets a single object that carries both. This
matches the query-side split, where `SearchQuery` is the input and
`ProductFilters` is an optional companion.

### 5.4 A separate port for faceted search

Faceted search is a distinct capability: the input is a query plus
a filter set, and the output is a page plus a facet summary.
Adding it to `ProductSearchGateway` would push that port to three
methods, at the edge of the ISP limit; and it would force every
consumer of search to depend on an aggregation method it does not
use. Instead, a second port:

    ProductFacetGateway
        search_with_facets(query, pagination) -> FacetedSearchResults

Two ports, both narrow. A caller that only wants search depends on
the first; a caller that wants facets depends on both.

## 6. Testing

### 6.1 Filters

Each filter dimension has an integration test: a known query and a
known filter produce a known set of document ids. Combined filters
are tested as well: category=Electronics AND price <= 100 must
produce the intersection, not the union.

### 6.2 Facets

Each facet has an integration test: a known query produces a facet
with the expected buckets. The test does not assert the counts are
a specific number if the fixture is small; it asserts the set of
bucket values and their relative order.

Combined facets are tested in one integration test: the same query
returns all four facets with consistent counts across them.

### 6.3 Filters and facets together

One integration test asserts that a filter changes the facet
counts: without the filter, the category facet counts all matches;
with the filter, the category facet counts only the matching
category.

## 7. Rule for Changing Filters or Facets

A change to the filter dimensions, the facet fields, the facet
sizes, or the price bands is a change to this document and to the
code, in the same commit. The rule mirrors the one for the product
model: the document is the specification, the code is the
implementation, and they do not diverge.

