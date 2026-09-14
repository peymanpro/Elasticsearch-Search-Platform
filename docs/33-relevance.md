# Relevance ? Consolidated Reference

## 1. Purpose

This document is the consolidated reference for how the platform ranks
search results. It supersedes `docs/14-relevance.md` as the
authoritative summary and references that document for the design
rationale.

It covers Phase 25.4 of the master roadmap.

## 2. The Baseline: BM25

The platform uses Elasticsearch's default BM25 similarity. It is not
overridden. BM25's score for a term in a field is derived from:

* term frequency, with saturation (parameter `k1`),
* inverse document frequency,
* field length normalization (parameter `b`).

Default parameters (`k1 = 1.2`, `b = 0.75`) are used. They are not
tuned, because the platform has no labeled relevance corpus against
which to tune them. Adjusting them without data would be guessing.

## 3. The Ranking Composition

A search's final score is composed in three tiers.

### 3.1 The text-relevance layer

A `bool` query with two clauses:

* **must**: `multi_match` over five fields with per-field boosts.
* **should** (optional): `match_phrase` on `name` with a high boost.

The `must` clause is what a user typed. The `should` clause is what
makes an exact name match outrank a same-term-in-different-words match.

### 3.2 Field boosts (the `must` clause)

| Field | Boost | Reason |
|---|---|---|
| `name` | 3.0 | Product name is the strongest signal |
| `brand` | 2.0 | Brand matches are high-intent |
| `category` | 1.5 | Category narrows intent |
| `tags` | 1.5 | Curated vocabulary applied by the catalog |
| `description` | 1.0 | A description match is weaker |

The ratios matter, not the absolute values. `name^3.0` means a match
in `name` is worth three times a match in `description`.

### 3.3 The exact-phrase boost (the `should` clause)

A `match_phrase` on `name` with boost 5.0. When the user's query
phrases matches the product's name (same words, same order), the
document gets an additional 5 BM25 units of score. This is what makes
"Wireless Noise-Cancelling Headphones" rank above "Wireless Earbuds"
for the query "wireless noise cancelling headphones".

### 3.4 The business-signal layer

The whole `bool` query is wrapped in a `function_score` that adds:

| Signal | Factor | Modifier | Reason |
|---|---|---|---|
| `rating` | 1.0 | (none) | Higher-rated products should be preferred |
| `popularity` | 0.5 | `log1p` | Popular products should be preferred, but popularity's wide range must be compressed so it does not dominate |

`score_mode: sum` adds the two field contributions. `boost_mode: sum`
adds that sum to the text-relevance score.

## 4. What Is Not Done

* **Phrase boost on description (9.4)** is documented as an option
  but not enabled. With a 12-document fixture, a description phrase
  boost does not produce a measurably different ranking, and adding
  an untestable clause would be configuration without a verifiable
  effect. The decision is recorded in `docs/14-relevance.md` section
  5.
* **Prefix relevance (9.5)** is not a separate concept. Prefix
  matching is provided by autocomplete
  (`docs/17-autocomplete.md`), which is a distinct endpoint.
* **Fuzzy relevance (9.6)** is covered by Phase 10's fuzzy search.
  The fuzzy strategy does not add business signals; ranking among
  fuzzy candidates is a subtler problem than this phase attempts to
  solve.
* **Learning to rank, embeddings, or neural reranking.** Out of
  scope per `docs/02-non-goals.md` section 5.1.

## 5. Relevance Strategy Pattern

The ranking policy is composed by a `RelevanceQueryBuilder` that
implements the domain's `RelevanceQueryComposer` Protocol. A
`RelevantSearchStrategy` invokes it and hands the composed query to
the gateway. The policy (all weights, all clauses) lives in the
builder; the strategy is only the mechanism that selects it.

This separation is deliberate: a change to a field boost is a change
to one class, not to every consumer of the policy.

## 6. Verification

Relevance is tested at the level of ranking order, not absolute
scores.

* `tests/integration/test_relevance.py` ? a fixture catalog designed
  to isolate each mechanism (exact name match, name-only match,
  description-only match, non-match). The tests assert that the
  expected document ranks first, that a name match outranks a
  description match, and that the exact-phrase boost increases the
  score.
* `tests/integration/test_query_dsl.py` ? the score of a document
  that matches a `should` clause is higher than the score of a
  document that matches only the `must` clause, all else equal.

The tests do not assert a specific score value. Elasticsearch's score
for a given query and document is a fact about the cluster's state at
a moment in time, not a stable contract the platform can depend on.
What is stable is the order.

## 7. Related Documents

* `docs/14-relevance.md` ? the design rationale for every weight.
* `docs/06-strategy-pattern.md` ? the strategy used to select the
  relevance policy.
* `docs/17-autocomplete.md` ? the distinct mechanism used for prefix
  matching.
