# Index Design ? Consolidated

## 1. Purpose

This document is the consolidated reference for the products index.
It supersedes `docs/12-index-design.md` as the authoritative
statement of the mapping and settings, and it references the
individual design documents that established each decision.

It covers Phase 25.2 of the master roadmap.

## 2. Physical Index and Alias

| Name | Purpose |
|---|---|
| `products-v1` | Physical index, first version (no `name_suggest`) |
| `products-v2` | Physical index, current version (with `name_suggest`) |
| `products` | Alias; resolves at query time to the current physical index |

The alias is the only name any query code uses. The physical name is
referenced only by lifecycle operations (create, reindex, delete).
See `docs/23-index-lifecycle.md`.

## 3. Index Settings

| Setting | Value | Reason |
|---|---|---|
| `number_of_shards` | 1 | Single-node cluster; more shards add overhead without value |
| `number_of_replicas` | 0 | Single node; a replica would be unassigned |
| `refresh_interval` | `1s` | Default; near-real-time visibility without per-write cost |
| `analysis` | two custom analyzers plus their search-time variants | See Section 5 |

## 4. Field Mapping

| Field | Type | Multi-field | Purpose |
|---|---|---|---|
| `id` | keyword | no | Document identity |
| `sku` | keyword | no | Product code; keyword filter, tie-breaker |
| `name` | text | yes (`.keyword`) | Primary search; `.keyword` for sorting/filtering |
| `name_suggest` | search_as_you_type | auto-subfields | Autocomplete (`v2` only) |
| `brand` | text | yes (`.keyword`) | Search, filter, aggregation |
| `category` | text | yes (`.keyword`) | Search, filter, aggregation |
| `description` | text | no | Search and highlight |
| `tags` | text | yes (`.keyword`) | Search; `.keyword` for exact tag filter |
| `specifications` | flattened | no | Open-ended attribute bag |
| `language` | keyword | no | Filter |
| `price` | double | no | Range filter, sort, aggregation |
| `currency` | keyword | no | Filter |
| `rating` | double | no | Range filter, sort |
| `availability` | keyword | no | Filter |
| `created_at` | date | no | Sort by recency |
| `popularity` | long | no | Sort by business signal |

`dynamic: strict` at the top level. A document with an unknown field
is rejected; the mapping is a closed contract. See
`docs/12-index-design.md` section 4.

## 5. Analyzers

Two custom analyzers plus their search-time variants.

| Analyzer | Tokenizer | Filters | Used by |
|---|---|---|---|
| `product_text_analyzer` | standard | lowercase, asciifolding, stop, porter_stem | index-time for `name`, `description`, `name_suggest` |
| `product_text_search_analyzer` | standard | lowercase, asciifolding, synonym, stop, porter_stem | search-time for the same fields |
| `product_keyword_analyzer` | standard | lowercase, asciifolding | index-time for `brand`, `category`, `tags` |
| `product_keyword_search_analyzer` | standard | lowercase, asciifolding, synonym | search-time for the same fields |

The distinction between index-time and search-time analyzers is what
makes the synonym list changeable without a reindex. See
`docs/13-text-analysis.md` and `docs/16-synonyms.md`.

## 6. What Is Deliberately Not in the Index

* **Persian language.** The catalog is English-only per `docs/09`
  section 3.1 and Phase 4.3 (recorded as out of scope).
* **Full specification sheet.** The `specifications` object is a
  summary; the flattened field indexes whatever is there.
* **Images, manufacturer distinction, country of origin.** No search
  scenario requires them (`docs/09` section 7).
* **Stock quantity.** Availability is a coarse enum; quantity is an
  inventory concern (`docs/02-non-goals.md`).

## 7. Version History

| Version | Change | Phase |
|---|---|---|
| `v1` | Initial index: all fields except `name_suggest` | 5.3?5.6 |
| `v2` | Added `name_suggest` (search_as_you_type) | 12 |

Adding a field to an index with documents requires a new version. The
reindex workflow (`docs/23-index-lifecycle.md`) is the mechanism by
which a new version becomes live.

## 8. Related Documents

* `docs/09-product-document-model.md` ? the domain-level field reference.
* `docs/12-index-design.md` ? the design rationale for every mapping decision.
* `docs/13-text-analysis.md` ? the analysis chain in detail.
* `docs/16-synonyms.md` ? the synonym list and its rationale.
* `docs/23-index-lifecycle.md` ? how the index evolves.
