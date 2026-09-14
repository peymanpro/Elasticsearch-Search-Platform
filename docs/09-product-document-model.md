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

**docs/01-business-scenario.md** -- the medical-products domain, the four
search personas (clinician, procurement, biomedical engineer,
Persian-language user), and the fourteen concrete search scenarios S1-S14.

**Master roadmap, Phase 4** -- the dataset requirements: English and
Persian text, realistic synonyms, multiple categories and brands, numeric
and filterable fields, fields suitable for sorting, fields suitable for
aggregation.

## 3. Key Design Decisions

### 3.1 One document per (product, language)

**Problem.** A product catalog must serve users searching in more than
one language. Two structural options exist.

**Options.**

1. **Multi-language fields.** One document per product, with
   language-suffixed subfields (name_en, name_fa, description_en,
   description_fa, ...). Each subfield carries its own language-
   specific analyzer.
2. **One document per language.** Each product is indexed once for
   English and once for Persian. A language keyword field
   distinguishes them. Documents share a sku but have distinct _id
   values (PM-1001-en, PM-1001-fa).

**Chosen approach.** Option 2 -- one document per (product, language).

**Why.** Option 2 demonstrates the multilingual search problem more
directly and keeps the mapping simple. With option 1, every text field
gains a subfield, every query must know which language's subfield to
target, and every analyzer must be attached per-language per-field -- a
combinatorial explosion of configuration that obscures rather than
clarifies. Option 2 makes language a first-class filter: the same query
against the same index returns the correct language's documents when
filtered by language, and analyzers attach to the same field names
across all documents.

**Trade-offs.**

- Redundant storage: numeric, filterable, and structural fields are
  duplicated across both language variants of a product. For a
  demonstration dataset this is negligible.
- Result de-duplication: a query without a language filter returns both
  variants of the same product. The platform treats this as a caller
  responsibility: a default language filter is applied by the API layer
  (Phase 19), not by the index.
- Update complexity: changing a price requires updating two documents.
  Bulk indexing (Phase 17) handles this uniformly.

**How tested.** Multilingual search tests in Phase 21 assert that a
Persian query filtered by language=fa returns only Persian documents,
and an English query filtered by language=en returns only English ones.

### 3.2 Structured specifications: flattened, not object

**Problem.** Products carry structured attributes -- display size,
weight, battery hours -- that vary by product category.

**Options.**

1. **Object field with dynamic: true.** Elasticsearch infers subfield
   types from the first document it sees. Later documents with different
   shapes silently corrupt the mapping.
2. **Object field with dynamic: false.** Unknown subfields are stored
   but not indexed. Searchable only if subfields are declared explicitly.
3. **Explicit subfields.** Declare each specification as a named field
   (weight_kg, battery_hours, display_inches). Rigid: new spec types
   require mapping changes.
4. **Flattened field.** Treat the whole specification subtree as one
   keyword field. Subfields are searchable as
   specifications.weight_kg: "4.2".

**Chosen approach.** Option 4 (flattened) for the specifications
object, plus explicit top-level numeric fields for any spec that
participates in numeric range filtering or sorting.

**Why.** Flattened avoids dynamic-mapping drift and provides a single
uniform way to search arbitrary structured attributes. Explicit
top-level fields are reserved for specs that will actually be filtered,
sorted, or aggregated -- which is where a flattened field's string
coercion becomes a liability.

**Trade-offs.**

- Flattened fields cannot serve numeric range queries. A numeric spec
  that must be filtered (weight, battery hours) is promoted to a
  top-level field.
- Flattened fields index every leaf value as a keyword. Storage cost is
  slightly higher than an unindexed object.

**How tested.** Phase 6 mapping tests assert that specifications is
mapped as a flattened field, and that any promoted numeric spec has a
top-level numeric field.

### 3.3 Currency is explicit

**Problem.** Prices are numeric. A catalog may span multiple currencies.

**Chosen approach.** A currency field, mapped as a keyword, always
present alongside price.

**Why.** A numeric price without a currency is ambiguous. Making the
currency explicit now is cheaper than a migration later when the
catalog grows beyond one region. The demonstration dataset uses USD
and IRR to exercise the field.

**Trade-offs.** Adds one field to every document. Trivial.

**How tested.** Phase 21 integration tests assert that a price range
filter combined with a currency filter returns only the intended
documents.

### 3.4 Document identifiers

**Problem.** Elasticsearch requires a document _id. The dataset is
multilingual (per 3.1).

**Chosen approach.** _id is the string {sku}-{language} (for example
PM-1001-en). The id field in _source carries the same string.

**Why.** Deriving _id from (sku, language) makes bulk indexing
idempotent (Phase 17.6): re-running the same dataset produces the same
document identities, and re-indexing overwrites rather than duplicates.
This is the idempotency requirement from the master prompt (Section 1.1).

**Trade-offs.** A product's identity changes if its SKU or language
changes. This is correct: those are the two facts that determine which
document a piece of data belongs to.

**How tested.** Phase 17.6 idempotency tests assert that ingesting the
same dataset twice leaves the index with the same document count.

## 4. Field Reference

| Field | Domain type | Purpose | Notes |
|---|---|---|---|
| id | string | Document identity | {sku}-{language} |
| sku | string | Keyword filter, display | Product code |
| name | text | Primary search, display | Product name |
| brand | text | Search, filter, aggregate | Brand name |
| category | text | Search, filter, aggregate | Category name |
| description | text | Search, highlight | Long text |
| tags | list[text] | Search, filter | Free-form tags |
| specifications | dict | Structured search | Flattened in Elasticsearch |
| language | enum | Filter | en or fa |
| price | decimal | Range filter, sort | Numeric |
| currency | enum | Filter | USD or IRR |
| rating | float | Range filter, sort | 0.0 to 5.0 |
| availability | enum | Filter | Fixed set |
| created_at | datetime | Sort (recency) | ISO 8601 |
| popularity | integer | Sort (business signal) | Non-negative |

## 5. Purpose Groups

These groups are defined in code (apps/search/domain/product_schema.py)
so that later phases can reason about field purpose without re-reading
this document.

### Searchable text fields

name, brand, category, description, tags

These participate in full-text search. Phase 9 assigns weights: name
highest, then brand, then category and tags, then description.

### Filterable keyword fields

sku, brand, category, language, availability, currency

These are used in filter clauses (no scoring impact) and are mapped as
keyword fields or as keyword subfields of text fields.

### Numeric range fields

price, rating, popularity

These accept range filters and appear in numeric aggregations.

### Sortable fields

price, rating, created_at, popularity

These are used in sort clauses. Text fields are not sortable without a
keyword subfield.

### Aggregatable fields

brand, category, availability

These produce terms aggregations for faceted navigation (Phase 14).

## 6. Example Document

```json
{
  "id": "PM-1001-en",
  "sku": "PM-1001",
  "name": "Portable Patient Monitor",
  "brand": "Mindray",
  "category": "Patient Monitoring",
  "description": "Portable multiparameter patient monitor for hospitals and emergency care.",
  "tags": ["patient monitor", "ECG", "SpO2", "NIBP"],
  "specifications": {
    "display": "12 inch",
    "weight_kg": 4.2,
    "battery_hours": 6
  },
  "language": "en",
  "price": 2450.0,
  "currency": "USD",
  "rating": 4.7,
  "availability": "in_stock",
  "created_at": "2024-09-15T10:30:00Z",
  "popularity": 128
}
```

## 7. Out of Scope

The following fields are deliberately excluded from the initial model:

- **image_url** -- display-only, no search relevance.
- **Full specification sheet** -- the specifications object is a
  summary, not a datasheet.
- **manufacturer** -- treated as identical to brand for simplicity.
  If the catalog needs a distinction, a later iteration adds it.
- **country_of_origin** -- no current search scenario requires it.
- **stock_quantity** -- availability is a coarse enum; quantity is an
  inventory concern (see docs/02-non-goals.md).

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
| 17.1 Bulk Indexing | Constructing _id from (sku, language) |
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

