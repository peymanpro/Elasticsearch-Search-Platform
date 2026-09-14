# Index Design -- products-v1

## 1. Purpose

This document specifies the settings and mapping of the products
index. It covers four roadmap sub-phases:

    * 5.3 -- index settings
    * 5.4 -- explicit mapping
    * 5.5 -- dynamic versus explicit mapping
    * 5.6 -- field type selection

The design is the authoritative specification for the index that
Phase 7 (analyzers), Phase 8 (queries), Phase 9 (relevance), and
Phase 14 (aggregations) operate on.

## 2. Index Settings (Phase 5.3)

### 2.1 The four settings that matter

| Setting | Value | Why |
|---|---|---|
| number_of_shards | 1 | Single-node development cluster. More shards would add overhead without value at this scale. |
| number_of_replicas | 0 | Single node -- a replica would be unassigned and leave the cluster yellow. |
| refresh_interval | "1s" (default) | Appropriate for a search index; near-real-time visibility without per-write cost. |
| max_result_window | 10000 (default) | Deep pagination beyond this window uses search_after (Phase 15.6), not from/size. |

### 2.2 Alternatives considered

**Two shards instead of one.** Rejected. A single shard is faster for
a demonstration dataset; two would demonstrate shard concepts but at
a cost in query time and without added correctness. If a future phase
needs to demonstrate shard routing, it does so on a separate index.

**Replicas.** Not configurable on a single-node cluster. Documented
here so the choice is explicit: the value is a consequence of the
topology (docs/11 section 2.2), not a design preference.

**Longer refresh interval.** A 30-second refresh would reduce write
cost, which matters for bulk ingestion. But the platform's tests
index a document and immediately search for it; a long interval would
force explicit refresh calls everywhere. The default keeps the
testing story simple.

### 2.3 Settings the index does NOT set

The following settings are deliberately left at their defaults:

* `analysis` -- analyzers are the subject of Phase 7.
* `similarity` -- BM25 default is used; relevance engineering is
  Phase 9.
* `routing` -- no custom routing is needed at this scale.
* `codec` -- default compression is appropriate.

## 3. Explicit Mapping (Phase 5.4)

### 3.1 Why explicit

A dynamic mapping is Elasticsearch inferring field types from the
first document it indexes. It is convenient and it is dangerous:

* The first document determines the type for every field. A price
  that arrives as `349.99` becomes a `float`; the same field arriving
  later as `"349.99"` would be rejected or, in a permissive mapping,
  coerced.
* A field that never appears in the first document is mapped as the
  union of its later occurrences, which produces types that no
  designer chose.
* A typo in a document key -- `discription` instead of `description`
  -- silently creates a second field of the same shape, and every
  query that targets the intended field misses the document with the
  typo.

The platform defines an explicit mapping for every field in
`ProductField` and forbids unmapped fields at index time. See Section
4.

### 3.2 Mapping overview

The mapping is derived directly from the field vocabulary in
`apps/search/domain/product_schema.py`. Each field's mapping type is
determined by its purpose group. The full table is in Section 5.

## 4. Dynamic Mapping Policy (Phase 5.5)

### 4.1 The policy

The index uses `dynamic: strict` at the top level.

**What `strict` means.** Any document whose `_source` contains a key
not present in the mapping is rejected outright. The error names the
unknown field and the document id.

**Why strict rather than false or true.**

* `true` (the default) auto-adds unknown fields with inferred types.
  That is the failure mode described in Section 3.1.
* `false` ignores unknown fields. The document indexes, the unknown
  key is stored in `_source`, but no query can find it. Silent.
* `strict` rejects the document. Loud.

Loud is the correct choice. A dataset that violates the mapping is a
bug in the dataset or in the mapping, not a runtime condition to be
tolerated. The bulk indexer (Phase 17) surfaces these failures
through its partial-failure reporting.

### 4.2 Handling the `specifications` sub-tree

The `specifications` field is `dynamic: true` *inside itself*. Its
leaf keys (color, battery_hours, screen_inches) are not fixed: an
Electronics item and a Book have different specifications, and
declaring every possible leaf would defeat the flattened design.

The trade-off: an unexpected key inside `specifications` is silently
indexed as a keyword; an unexpected key at the top level is rejected.
That is the right split. Top-level fields are stable facts about the
catalog; specifications are free-form product attributes.

## 5. Field Type Selection (Phase 5.6)

### 5.1 The four Elasticsearch field types used

| ES type | Purpose | When chosen |
|---|---|---|
| text | Full-text search; the field is analyzed | The field is in TEXT_SEARCH_FIELDS |
| keyword | Exact match, filter, sort, aggregation | The field is in KEYWORD_FILTER_FIELDS or AGGREGATABLE_FIELDS |
| long / double | Numeric range, sort | The field is in NUMERIC_RANGE_FIELDS |
| date | Range, sort by recency | The field is a datetime |

### 5.2 The mapping decision table

| Field | ES type | Multi-field? | Rationale |
|---|---|---|---|
| id | keyword | no | Identity; not analyzed |
| sku | keyword | no | Filter and display; exact match only |
| name | text | yes, .keyword | Search primary; keyword subfield for sort |
| brand | text | yes, .keyword | Search and filter; both representations used |
| category | text | yes, .keyword | Search and aggregate; both representations used |
| description | text | no | Search and highlight only |
| tags | text | yes, .keyword | Array of searchable text values; keyword subfield for exact tag filters |
| specifications | flattened | n/a | Searchable free-form attribute bag |
| language | keyword | no | Filter; single value |
| price | double | no | Range filter, sort, aggregation |
| currency | keyword | no | Filter; enum |
| rating | double | no | Range filter, sort, aggregation |
| availability | keyword | no | Filter; enum |
| created_at | date | no | Sort by recency |
| popularity | long | no | Sort; integer business signal |

### 5.3 Why multi-fields on name, brand, category

These three fields are used both as searchable text and as exact
filters or aggregations. A single `text` mapping cannot serve both:
a filter on a text field matches analyzed terms, so `"Sony"` would
match a brand of `"Sony Corporation"`. A single `keyword` mapping
cannot serve search: only exact matches match.

The multi-field pattern produces one field with two representations.
A query uses the field name for search (`brand: sony`) and the
`.keyword` subfield for filter or aggregation
(`brand.keyword: "Sony"`). This is the canonical Elasticsearch
solution to the dual-purpose-field problem.

### 5.4 Why `description` has no keyword subfield

A long, unaggregatable text. Sorting on a description has no use
case; aggregating on one would produce one bucket per distinct
description. The keyword subfield would double the index size for no
benefit.

### 5.5 Why `specifications` is `flattened`

See docs/09 section 3.2. The short version: it gives uniform keyword
search over an open-ended attribute set without committing to any
one attribute being a named field.

### 5.6 Numeric field types

| Field | Type | Why |
|---|---|---|
| price | double | Prices are fractional; long would lose cents |
| rating | double | Ratings are fractional |
| popularity | long | Integer counter |

The `scaled_float` alternative for price -- storing 349.99 as 34999
scaled by 100 -- is rejected. It saves roughly one byte per document
and loses the ability to write a price with more than two decimal
places. Neither matters at this scale.

### 5.7 Date format

The `created_at` field uses `strict_date_optional_time` (the default)
and accepts the ISO 8601 strings in the dataset. The format is
declared explicitly so that a future change to the writer cannot
silently break parsing.

## 6. Files

The index definition is stored as JSON under
`infrastructure/elasticsearch/indices/`:

* `products_v1.settings.json` -- the settings block from Section 2.
* `products_v1.mapping.json` -- the mapping from Section 5.

The loader in `infrastructure/elasticsearch/indices/__init__.py`
reads these files and exposes them as Python dictionaries. The
manager in `infrastructure/elasticsearch/indices/manager.py` creates
and deletes indices from them.

Files rather than Python constants: the JSON is the artifact
Elasticsearch actually consumes, and keeping it in that form means
the design document, the checked-in file, and the runtime request are
the same bytes.

## 7. Rule for Changing the Mapping

A mapping change -- adding a field, changing a type, changing an
analyzer -- cannot be applied to an existing index. Elasticsearch
forbids it. The only options are:

1. Create a new index with a new version (`products-v2`), reindex,
   switch the alias. This is the subject of Phase 18.
2. Delete and recreate the index. Acceptable only for development
   datasets that can be regenerated.

This document and the JSON files are updated first; the index is
recreated or a new version is created second.


## 8. Index Naming Convention (Phase 6.6)

### 8.1 The convention

Two names exist for each index version, and they have distinct jobs:

| Name | Example | Purpose |
|---|---|---|
| Physical | products-v1 | The actual Elasticsearch index. Versioned. |
| Alias | products | The name the application uses. Unversioned. |

The application never references the physical name directly. It
references the alias. The alias is repointed from v1 to v2 during a
reindex (Phase 18), and the application continues to work without
change.

### 8.2 Rules

1. The physical name always carries the version suffix. `products-`
   is the prefix; `v1`, `v2`, `v3` are the versions. No other
   suffixes are used.
2. The alias is short, unversioned, and never carries a suffix.
3. A new physical index is created when, and only when, the mapping
   or settings change. A document change does not require a new
   index.
4. The physical index is deleted only after the alias has been moved
   away and the new index has been validated.

### 8.3 Where this is implemented

The physical naming convention is enforced by
`infrastructure.elasticsearch.indices.manager.physical_index_name`,
which returns `f"products-{version}"`. The alias constant lives in
`infrastructure.elasticsearch.indices.INDEX_ALIAS`. Phase 18 wires
them together into the reindex workflow.

### 8.4 Why not the alias alone

An alternative would be to create the index directly under the alias
name and drop and recreate it on every schema change. This is
rejected: an alias switch is atomic and reindexable, a drop-and-
recreate is not. The versioned-physical-plus-alias pattern is the
standard Elasticsearch practice and Phase 18 exists to demonstrate
it end to end.

