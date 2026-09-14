# Sorting and Pagination

## 1. Purpose

This document specifies how the platform orders result sets and how
it lets callers walk through them page by page. It covers the
roadmap sub-phases:

    * 15.1 -- Relevance sorting
    * 15.2 -- Business sorting
    * 15.3 -- Stable tie-breaking
    * 15.4 -- Basic pagination
    * 15.5 -- Deep pagination
    * 15.6 -- search_after

## 2. Sorting

### 2.1 The two kinds of order

A search result can be ordered two ways:

* **By relevance.** Documents closest to the query text appear
  first. This is Elasticsearch's default and the natural order
  when the user is exploring.
* **By a business attribute.** Documents appear in a caller-chosen
  order: cheapest first, highest rated first, newest first. This is
  what a user picks when they say "sort by price".

Both must be supported. Neither replaces the other.

### 2.2 Relevance sorting (15.1)

Relevance sorting is the default. When no explicit sort is given,
Elasticsearch orders by `_score` descending. The platform makes
this explicit in the query it sends, so that the request body
documents the contract even when a caller has not asked for a
specific order.

### 2.3 Business sorting (15.2)

The platform supports four sort fields:

| Field | Type | Direction | Notes |
|---|---|---|---|
| price | double | asc or desc | Numeric |
| rating | double | asc or desc | Numeric |
| popularity | long | asc or desc | Integer |
| created_at | date | asc or desc | ISO 8601 |

These are exactly the sortable fields the product model declares
(`SORTABLE_FIELDS` in product_schema.py). The correspondence is
deliberate: the domain defines which fields are sortable, and the
API exposes only those.

`_score` is a fifth option, exposed explicitly so that a caller who
wants "relevance, but a different default direction" can express
it. In practice the default direction is descending, and callers
do not override it.

### 2.4 Stable tie-breaking (15.3)

A sort on a numeric field produces ties: two documents with the
same price, two documents with the same rating. If the sort order
is not deterministic across those ties, pagination becomes
unreliable: page 1 might show document X and page 2 might show X
again or skip it entirely, because Elasticsearch assigned an
arbitrary internal order to the tied documents.

The platform makes every sort stable by appending a tie-breaker:
`sku` ascending. The SKU is unique by definition (it is the
document `_id`), so the tie-break is total.

The sort clause the platform sends therefore always has at least
two entries: the caller-chosen field (or `_score`), followed by
`sku` ascending (the SKU is mapped as a keyword, so the tie-breaker targets the field directly). This is what makes the pagination of
Section 3 correct.

## 3. Pagination

### 3.1 What pagination is

A search returns a page of results, not the whole result set. A
page has a size (how many hits) and a position (which page). The
position can be expressed in two ways:

* **Offset-based.** "Skip the first 100 hits and give me the next
  20." Expressed as `from` and `size` in Elasticsearch.
* **Cursor-based.** "Give me 20 hits that come after this exact
  hit." Expressed as `search_after` in Elasticsearch.

The platform supports both. They are correct for different
situations, and Section 3.4 explains why both exist.

### 3.2 Basic pagination (15.4)

Offset-based pagination is what the `Pagination` value object has
expressed since Phase 2.3. A `Pagination(page=3, page_size=20)`
translates to `from=40, size=20`. This has worked for every phase
so far and continues to be the default.

It is correct for any page depth up to a limit. The limit is
Section 3.4.

### 3.3 The cost of an offset

Elasticsearch does not store results in a pre-sorted array. To
return `from=10000, size=20`, it must:

1. Find every document that matches the query.
2. Score each one.
3. Sort them all.
4. Discard the first 10000.
5. Return the next 20.

Steps 1-3 are the same regardless of the offset. Step 4 costs
nothing on the server side -- the sorted list is already in
memory -- but the sorting has to have happened. As the offset
grows, the sort becomes the dominant cost. This is what makes deep
pagination expensive.

### 3.4 The `max_result_window` limit (15.5)

Elasticsearch refuses any request where `from + size >
max_result_window`. The default is 10000. This is not a bug; it is
a deliberate protection. Without it, a single `from=100000000`
request could exhaust a node's heap.

Three options exist when a caller wants to page past 10000:

1. **Raise `max_result_window`.** Rejected. It moves the limit; it
   does not remove it; and it makes an out-of-memory condition
   possible.
2. **Use `search_after`.** The correct answer. It uses the sort
   order of the last hit on the previous page as a cursor, so the
   server only has to find and sort documents that come after
   that point -- not everything before it.
3. **Refuse the request.** Correct behavior when the caller cannot
   use `search_after` (for example, a UI that wants to jump
   directly to page 500). The platform returns a clear error.

The platform uses option 2 for anything beyond the window and
option 3 as the fallback. Section 4 describes the mechanism.

### 3.5 Why both offset and cursor exist

Offset pagination is simpler for the caller. A caller with a
"page 3 of 50" UI knows the page number and does not want to track
a cursor. For pages within the window, offset is correct and cheap.

Cursor pagination is correct for infinite-scroll or "load more"
interfaces, and it is the only mechanism that works past 10000
hits. It requires the caller to hold the cursor between requests.

The platform exposes both. Which one to use is a caller decision;
the platform does not force one.

## 4. `search_after` (15.6)

### 4.1 How it works

The `search_after` parameter is an array of values that must match
the sort keys of some existing hit. Given a previous page whose
last hit has sort values `[3.5, "SKU-1001"]`, the next request is:

    {
      "query": { ... },
      "sort": [
        { "rating": { "order": "desc" } },
        { "sku.keyword": { "order": "asc" } }
      ],
      "search_after": [3.5, "SKU-1001"],
      "size": 20
    }

Elasticsearch returns the 20 hits whose sort key is strictly after
`[3.5, "SKU-1001"]` in the declared sort order. It does not need
to scan the earlier hits, so the cost does not grow with depth.

### 4.2 The requirements

`search_after` requires:

* An explicit `sort` clause. Without one, there is no sort key to
  compare against.
* A total sort order. If two documents have identical sort keys,
  the "after" boundary is ambiguous -- the server may return both,
  or neither, depending on internal ordering. This is exactly why
  the platform always appends the `sku` tie-breaker. The
  full sort key `(rating desc, sku asc)` is total, so the
  boundary is always unambiguous.
* The cursor values must come from a real hit. A caller cannot
  invent a cursor.

### 4.3 The shape of a cursor on the wire

The platform exposes the sort values of the last hit on a page as
an opaque cursor: a list of the primitive values, exactly as
Elasticsearch returned them. The caller passes this list back
unchanged in the next request. The platform does not encode, sign,
or interpret the cursor. It is a pass-through.

    page 1 -> response includes "next_cursor": [3.5, "SKU-1001"]
    page 2 -> request includes "cursor": [3.5, "SKU-1001"]

The response also includes the sort values of every hit, so a
caller that wants finer control can build a cursor from any hit,
not just the last one.

## 5. The Domain Model

### 5.1 `SortOrder`

A `SortOrder` value object expresses a sort field and a direction.
Its shape:

    field: SortField    (an enum: SCORE, PRICE, RATING, POPULARITY, CREATED_AT)
    direction: SortDirection    (ASC or DESC)

The enum is closed: a caller cannot sort by an arbitrary field.
This is deliberate. A caller that could sort by `description`
would hit Elasticsearch's fielddata cost; a caller that could
sort by `brand.keyword` could create a very expensive terms sort
on a high-cardinality field. The platform declares the safe set
and exposes only that set.

The default `SortOrder` is `(SCORE, DESC)` -- relevance order. It
is stored on `SearchQuery` alongside the filters, so the whole
request is one value.

### 5.2 Cursor

A cursor is a tuple of primitive values. The platform carries it
on `Pagination` as an optional field: when set, the pagination is
cursor-based rather than offset-based. The two are mutually
exclusive: a `Pagination` with a cursor ignores `page` and uses
only `page_size`.

### 5.3 A note on cursor representation

The cursor is a list of heterogeneous primitives (a float, then a
string; or a datetime, then a string). Python represents this as
a `tuple[Any, ...]`. The domain does not attempt to type the
individual elements, because the types depend on the sort field,
which is chosen at request time.

## 6. Testing

### 6.1 Sorting

Each sort field has an integration test: a query with a known set
of matching documents, sorted ascending and descending, produces
the expected order. The tie-breaker is tested with a fixture where
two documents share a sort value, so that the `sku.keyword`
ordering is exercised.

### 6.2 Basic pagination

Offset pagination is already tested (Phases 2 and 8). Phase 15
adds a test that walks the first several pages of a small fixture
and asserts that the union of the pages equals the full result set,
with no duplicates.

### 6.3 Cursor pagination

Cursor pagination is tested end to end: fetch page 1, take its
cursor, fetch page 2, take its cursor, and so on until the result
set is exhausted. Assert that:

* Every document appears exactly once.
* The order matches a single-shot query with the same sort.
* A cursor fetched with one sort field is not compatible with a
  different sort field (a mismatch the caller is responsible for
  avoiding; the test documents the requirement).

### 6.4 Deep pagination

A test that requests a page beyond the `max_result_window` asserts
that the platform's offset-based `Pagination` value object rejects
it. The rejection is at the domain level, not the Elasticsearch
level, so the failure is clear and happens before the network.

## 7. Rule for Changing Sorting or Pagination

A change to the sortable fields, the sort directions, the default
sort, or the cursor shape is a change to this document and to the
code, in the same commit. The rule mirrors the other design
documents in this project: the document is the specification, the
code is the implementation, and they do not diverge.

