# Product Document Model

## 1. Purpose

This document defines the shape of a product document in the platform's
catalog. It is the authoritative specification for:

- the JSONL dataset produced in Phase 4.5,
- the Elasticsearch mapping defined in Phase 6,
- the analyzers chosen in Phase 7,
- the query composition of Phase 8,
- the relevance weights of Phase 9,
- the filtering, sorting, and aggregation behavior of Phases 14 and 15.

Any later phase that changes the shape of a document updates this
document first.

## 2. Inputs

The model is derived from two sources:

**docs/01-business-scenario.md** -- the general e-commerce domain, the
search personas (casual shopper, bargain hunter, power user), and the
fourteen concrete search scenarios S1-S14.

**Master roadmap, Phase 4** -- the dataset requirements: text in a
single supported language, realistic synonyms, multiple categories and
brands, numeric and filterable fields, fields suitable for sorting,
fields suitable for aggregation.

The catalog is a general e-commerce assortment spanning multiple
product categories (Electronics, Home and Kitchen, Office, Sports,
Books). It is not tied to a specific vertical: the search engineering
concerns are identical regardless of what is sold, and a general
catalog makes the demonstrations broadly applicable.

## 3. Key Design Decisions

### 3.1 One document per product

**Problem.** A product catalog must decide whether a single logical
product is represented by one index document or by several. Multiple
documents per product arise from two sources: language variants (the
same product described in more than one natural language) and channel
variants (the same product listed on different storefronts).

**Options.**

1. **One document per (product, language).** Duplicate every product
   for each supported language, with a language keyword field
   distinguishing them. Enables per-language analyzers.
2. **One document per product.** A single document per product,
   regardless of language. Requires multi-language field subfields if
   more than one language is supported.
3. **One document per (product, channel).** Duplicate every product
   per sales channel. Out of scope for this project -- there is no
   channel concept.

**Chosen approach.** Option 2 -- one document per product, in a single
supported language (English).

**Why.** The demonstration catalog is English-only by design. Modeling
multilingual search is a distinct engineering problem that deserves
its own dataset and its own analyzers; mixing it into a general
e-commerce dataset adds configuration complexity without adding
demonstration value. With a single language, one document per product
is the simplest correct model: identifiers are unambiguous, updates
touch exactly one document, and queries need no language filter.

If multilingual support is ever added, this decision is revisited as
a new sub-phase under Section 9's change rule -- it is not a small
incremental edit.

**Trade-offs.**

- Adding a second language later requires a reindex. This is
  acceptable: the design doc anticipates it and Phase 18 exists
  precisely to make this migration safe.
- A future multilingual design would need to decide whether to use
  one-per-language or multi-language fields. That decision is
  deferred until it is needed, per the project's rule against
  speculative abstraction.

**How tested.** Document identity tests in Phase 21 assert that the
document _id is exactly the SKU, and that ingesting the same product
twice does not create two documents (idempotency, Phase 17.6).

### 3.2 Structured specifications: flattened, not object

**Problem.** Products carry structured attributes (screen size, weight,
page count, color, size) that vary by category. An Electronics item has
different specs than a Book, which has different specs than a pair of
Shoes.

**Options.**

1. **Object field with dynamic: true.** Elasticsearch infers subfield
   types from the first document it sees. Later documents with
   different shapes silently corrupt the mapping.
2. **Object field with dynamic: false.** Unknown subfields are stored
   but not indexed. Searchable only if subfields are declared
   explicitly.
3. **Explicit subfields.** Declare each specification as a named field
   (weight_kg, screen_inches, page_count). Rigid: new spec types
   require mapping changes.
4. **Flattened field.** Treat the whole specification subtree as one
   keyword field. Subfields are searchable as
   specifications.color: "black".

**Chosen approach.** Option 4 (flattened) for the specifications
object, plus explicit top-level numeric fields for any spec that
participates in numeric range filtering or sorting.

**Why.** A general catalog spans categories with disjoint attribute
sets. Declaring every possible specification as a top-level field
would produce a sparse, rigid schema. Flattened avoids
dynamic-mapping drift (Option 1) while keeping arbitrary attributes
searchable (Option 4). Attributes that genuinely need range queries
-- such as price, rating, and popularity -- are already top-level and
not part of the specifications object.

**Trade-offs.**

- Flattened fields cannot serve numeric range queries. If a future
  requirement needs range queries on a specification attribute, that
  attribute is promoted to a top-level numeric field.
- Flattened fields index every leaf value as a keyword. Storage cost
  is slightly higher than an unindexed object.

**How tested.** Phase 6 mapping tests assert that specifications is
mapped as a flattened field, and that any promoted numeric spec has a
top-level numeric field.

### 3.3 Currency is explicit

**Problem.** Prices are numeric. A catalog may span multiple
currencies, and a price without a currency is ambiguous.

**Options.**

1. **Single currency assumed.** Store price alone. Simple, but wrong
   the moment a second currency appears.
2. **Currency field alongside price.** Store price and currency
   together. Every consumer that reads price must also read currency.
3. **Normalize to a base currency at ingest.** Convert every price to
   one currency. Loses the original price, and requires exchange-rate
   logic that belongs to a different system.

**Chosen approach.** Option 2 -- a currency field, mapped as a
keyword, always present alongside price.

**Why.** A currency enum makes the ambiguity impossible: every
document declares its own currency, and price filters must be paired
with a currency filter to be meaningful. The demonstration dataset
uses USD, EUR, and GBP so that a currency filter is exercised by real
data. Normalization is rejected because it changes what the store is
actually selling.

**Trade-offs.** Adds one field to every document. Trivial.

**How tested.** Phase 21 integration tests assert that a price range
filter combined with a currency filter returns only the intended
documents, and that omitting the currency filter returns the union of
all currencies matching the numeric range.

### 3.4 Document identifiers

**Problem.** Elasticsearch requires a document `_id`. The dataset must
choose identifiers that make bulk indexing idempotent and make
references (from the API, from `_explain`, from highlighting) stable
across re-indexes.

**Options.**

1. **Let Elasticsearch generate the _id.** Autogenerated IDs change
   on every ingest. Re-running the loader duplicates documents.
2. **Use the SKU as _id.** The SKU is a stable business identifier
   that a store already assigns to every product.
3. **Use a composite key.** Any (attribute, attribute) tuple that is
   unique per product -- for example `{sku}-{channel}`. Meaningful
   only when the catalog actually spans the composed dimensions.

**Chosen approach.** Option 2 -- `_id` is the SKU.

**Why.** The demonstration catalog has one document per product in one
language for one storefront. The SKU is exactly the identity of that
document: unique by definition, present in the source data, and
independent of any Elasticsearch-assigned value. Option 1 is rejected
because it forfeits idempotency. Option 3 is rejected because the
catalog has no dimension that a composite would add -- the composite
would be the SKU plus nothing.

The `id` field inside `_source` carries the same string as `_id`. This
is deliberate: it keeps the response shape identical to the request
shape, and lets clients consume the document without needing to read
the transport-level `_id`.

**Trade-offs.** A product's identity changes if its SKU changes.
This is correct: changing a SKU means the store has decided the
product is a different item. Section 3.1's earlier decision to drop
the `{sku}-{language}` composite makes this identity clean.

**How tested.** Phase 17.6 idempotency tests assert that ingesting the
same dataset twice leaves the index with the same document count.
Phase 21 integration tests assert that the `_id` and the `id` field
in `_source` are identical strings.

## 4. Field Reference

| Field | Domain type | Purpose | Notes |
|---|---|---|---|
| id | string | Document identity | Equal to _id; here for response symmetry |
| sku | string | Keyword filter, display | Product code; stable business identifier |
| name | text | Primary search, display | Product name |
| brand | text | Search, filter, aggregate | Brand name |
| category | text | Search, filter, aggregate | Top-level product category |
| description | text | Search, highlight | Long text |
| tags | list[text] | Search, filter | Free-form tags |
| specifications | dict | Structured search | Flattened in Elasticsearch |
| language | enum | Filter | Language of the product text; en only today |
| price | decimal | Range filter, sort | Numeric |
| currency | enum | Filter | USD, EUR, or GBP |
| rating | float | Range filter, sort | 0.0 to 5.0 |
| availability | enum | Filter | Fixed set |
| created_at | datetime | Sort (recency) | ISO 8601 |
| popularity | integer | Sort (business signal) | Non-negative |

The `language` field is present even though the demonstration catalog
is English-only. It exists as an explicit filter and as a mapping
placeholder for a possible future expansion. Today it is always `en`.

## 5. Purpose Groups

These groups are defined in code (apps/search/domain/product_schema.py)
so that later phases can reason about field purpose without re-reading
this document.

### Searchable text fields

name, brand, category, description, tags

These participate in full-text search. Phase 9 assigns weights: name
highest, then brand, then category and tags, then description. The
relative order reflects what a shopper is most likely to type: the
product name carries more intent than a description fragment.

### Filterable keyword fields

sku, brand, category, language, availability, currency

These are used in filter clauses (no scoring impact) and are mapped
as keyword fields or as keyword subfields of text fields. The
distinction from "searchable" is deliberate: filtering on brand must
be an exact match, not an analyzed one, or "Panasonic" and "Panason"
would both match a brand filter.

### Numeric range fields

price, rating, popularity

These accept range filters and appear in numeric aggregations.
Range filtering on these fields is what powers the "under $50" and
"4 stars and up" facets of a shopping experience.

### Sortable fields

price, rating, created_at, popularity

These are used in sort clauses. Text fields are not sortable without
a keyword subfield; the sortable set is deliberately restricted to
numeric and temporal fields where a total order is unambiguous.

### Aggregatable fields

brand, category, availability

These produce terms aggregations for faceted navigation (Phase 14).
They are all low-cardinality keyword fields: a facet is only useful
when the set of possible values is small enough to display.

## 6. Example Document

An English-language product from the Electronics category.

```json
{
  "id": "SKU-1001",
  "sku": "SKU-1001",
  "name": "Wireless Noise-Cancelling Headphones",
  "brand": "Sony",
  "category": "Electronics",
  "description": "Over-ear wireless headphones with active noise cancellation and 30-hour battery life.",
  "tags": ["wireless", "bluetooth", "noise-cancelling", "over-ear"],
  "specifications": {
    "color": "black",
    "battery_hours": 30,
    "weight_grams": 254,
    "connectivity": "bluetooth 5.2"
  },
  "language": "en",
  "price": 349.99,
  "currency": "USD",
  "rating": 4.6,
  "availability": "in_stock",
  "created_at": "2024-09-15T10:30:00Z",
  "popularity": 842
}
```

A second example, from a different category, to illustrate the
flatness of specifications across categories.

```json
{
  "id": "SKU-2001",
  "sku": "SKU-2001",
  "name": "Stainless Steel Chef Knife 8-inch",
  "brand": "Wusthof",
  "category": "Home and Kitchen",
  "description": "Forged 8-inch chef knife with full tang and ergonomic handle.",
  "tags": ["kitchen", "knife", "cooking", "chef"],
  "specifications": {
    "blade_length_inches": 8,
    "steel": "high-carbon stainless",
    "weight_grams": 260
  },
  "language": "en",
  "price": 149.95,
  "currency": "USD",
  "rating": 4.8,
  "availability": "in_stock",
  "created_at": "2024-08-02T14:00:00Z",
  "popularity": 315
}
```

## 7. Out of Scope

The following fields are deliberately excluded from the initial model:

- **image_url** -- display-only, no search relevance. Image search is
  a distinct problem that this project does not attempt.
- **Full specification sheet** -- the specifications object is a
  summary, not a datasheet. Very long attribute lists would swamp
  the flattened field without adding search demonstrations.
- **manufacturer** -- treated as identical to brand for simplicity.
  If the catalog needs a distinction, a later iteration adds it.
- **country_of_origin** -- no current search scenario requires it.
- **stock_quantity** -- availability is a coarse enum; quantity is an
  inventory concern (see docs/02-non-goals.md).
- **seller / vendor** -- a marketplace feature, not a search feature.
- **shipping options** -- operational, not search-related.
- **Multilingual datasets** -- the catalog is English-only. The
  multilingual-analysis work scoped for Phase 4.3 is not applicable. See
  Section 3.1.

## 8. Consumers of This Model

| Phase | Consumes the model by... |
|---|---|
| 4.5 Dataset Generator | Producing documents matching the field reference |
| 6.1 Product Index | Mapping each field per its purpose group |
| 7.4 Custom Analyzer | Choosing analyzers per searchable text field |
| 8.x Query DSL | Selecting fields for match, term, range |
| 9.2 Field Boosting | Assigning weights per searchable field |
| 14.6 Terms Aggregation | Aggregating over aggregatable fields |
| 15.2 Business Sorting | Sorting on sortable fields |
| 17.1 Bulk Indexing | Constructing _id from the SKU |
| 21.x Tests | Asserting shape and behavior |

## 9. Rule for Changing This Model

A change to the product document model must:

1. Be justified by a concrete search scenario (docs/01) or a roadmap
   requirement.
2. Record the change in this document, using the same
   problem/options/choice/trade-offs format applied above.
3. Update apps/search/domain/product_schema.py in the same commit.
4. Consider the index-lifecycle impact (Phase 18): a mapping change
   requires a new index version and a reindex.

Changes that require a new index version -- adding a field, changing
a field type, changing an analyzer -- are the ones Phase 18 exists to
handle safely. Changes that do not -- updating the design rationale,
renaming an internal constant -- are ordinary edits.

