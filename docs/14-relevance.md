# Relevance Engineering

## 1. Purpose

This document specifies how the platform ranks search results. It
covers the roadmap sub-phases:

    * 9.1 -- BM25 (the baseline scoring model)
    * 9.2 -- Field Boosting
    * 9.3 -- Exact Match Boost
    * 9.4 -- Phrase Boost
    * 9.7 -- Business Signals
    * 9.8 -- Relevance Strategy

Prefix relevance (9.5) and fuzzy relevance (9.6) are addressed as
the subject of later phases (12 and 10 respectively) where they can
be designed in context.

## 2. BM25 (9.1)

### 2.1 What BM25 does

Elasticsearch uses BM25 as its default similarity algorithm. For a
given query term and field, BM25 computes a score from three factors:

* **Term frequency (TF)** -- how often the term appears in the
  document. More occurrences raise the score, but with diminishing
  returns (BM25 saturation).
* **Inverse document frequency (IDF)** -- how rare the term is in
  the whole index. A term that appears in every document carries no
  signal; a rare term carries a lot.
* **Field length normalization** -- shorter fields score higher for
  the same term, because the term is a larger fraction of the field.

### 2.2 Why this matters for the platform

BM25 is not a knob the platform sets; it is the baseline the
platform depends on. All relevance engineering in this phase is done
by composing clauses and applying boosts on top of BM25 -- never by
replacing it.

Alternatives such as `boolean` similarity (no TF saturation, no IDF)
or `DFR`/`DFI` (divergence from randomness) exist. None of them
outperform BM25 on a general e-commerce catalog, and switching would
make the platform's behavior harder to explain. BM25 is retained.

### 2.3 BM25 parameters

The default BM25 parameters are:

* `k1 = 1.2` -- term frequency saturation. A higher value gives more
  weight to repeat occurrences.
* `b = 0.75` -- field length normalization. 0 disables it; 1 applies
  it fully.

These defaults are not overridden. Tuning them is a subject for a
dedicated relevance-tuning phase, and doing so without a corpus of
labeled relevance judgments would be guesswork. See Section 7.

## 3. Field Boosting (9.2)

### 3.1 The problem

A user searching for "sony" expects to find Sony products. A
document whose brand is "Sony" is more relevant than a document that
happens to mention Sony in its description. The default multi_match
treats all fields equally.

### 3.2 The solution

Field boosts. Elasticsearch's `multi_match` accepts field names with
a boost suffix: `"name^3"` means "score matches in `name` three times
higher than matches in an unboosted field". Boosts multiply the
BM25-computed score for that field; they do not override BM25.

### 3.3 The field weights chosen

| Field | Boost | Rationale |
|---|---|---|
| name | 3.0 | The product name is the most direct signal of what a document is |
| brand | 2.0 | Brand matches are strong intent signals for shopper queries |
| category | 1.5 | Category matches narrow the intent without pinning a specific product |
| tags | 1.5 | Tags are a controlled vocabulary the catalog maintainers applied |
| description | 1.0 | A description match is weaker: the term may appear in a sentence that is only tangentially about it |

### 3.4 Why these numbers

The ratios matter, not the absolute values. `name^3` relative to
`description^1` means a match on the name is worth three times a
match on the description, all else equal. The absolute magnitude of
boosted scores is not comparable across queries; only ranking within
a query is.

These weights are a first cut. They reflect a reasonable prior: a
product name is more about a product than a sentence in its
description. Tuning them requires labeled relevance data, which this
project does not have. See Section 7.

## 4. Exact Match Boost (9.3)

### 4.1 The problem

A query for exactly the product name should rank that product first.
A user who types "Wireless Noise-Cancelling Headphones" wants that
product, not a list of documents that happen to contain some of
those words.

### 4.2 The solution

A `match_phrase` clause on the name field with a high boost, composed
as a `should` clause alongside the primary `multi_match` must clause.
The `should` clause adds score when it matches without being
required.

### 4.3 The composition

    bool:
      must:
        - multi_match: fields with boosts
      should:
        - match_phrase: name with boost 5.0
      minimum_should_match: 0

The `should` clause is optional. A query that does not phrase-match
any document still returns results; a query that phrase-matches one
document gives that document a score advantage of up to five BM25
units.

### 4.4 Why boost 5.0

The multi_match already boosts name matches at 3.0. The exact-phrase
boost adds on top. A boost of 5.0 gives a phrase match enough weight
to dominate a non-phrase match on a different field, without being
so large that an accidental phrase match on a short query swamps the
ranking entirely. This is a heuristic, not a tuned value.

## 5. Phrase Boost (9.4)

Phase 9.3 describes a phrase boost on the name field. The same
mechanism applies to the description field with a lower boost, so
that a query whose words appear adjacent in a description is
rewarded, but less than an adjacent match in the title.

In practice the description phrase boost is not implemented at
Phase 9. The reason: with five short fixture documents, a description
phrase boost does not produce a measurably different ranking, and
adding an untestable clause would be configuration without a
verifiable effect. It is recorded here as a design option, to be
adopted when the corpus is large enough for the boost to matter.

## 6. Business Signals (9.7)

### 6.1 The problem

Text relevance captures what a user searched for. It does not
capture what the platform knows about the products themselves: a
popular product and a highly-rated product are more likely to
satisfy the user, even if their text relevance is comparable.

### 6.2 The solution

A `function_score` query wraps the text-relevance query and adds
per-document boosts derived from numeric fields. The `function_score`
recomputes the final score from the underlying text score plus the
business-signal contributions.

### 6.3 The signals chosen

| Signal | Field | Weight | Rationale |
|---|---|---|---|
| Rating | rating | 1.0 | Higher-rated products should be preferred |
| Popularity | popularity | 0.5 | Popular products should be preferred, but less than rating |

The numeric fields are in very different ranges: `rating` is 0.0 to
5.0; `popularity` is 10 to 5000. A raw addition would let popularity
dominate. The `field_value_factor` function with `modifier: log1p`
compresses popularity's range so that its contribution is on the
same order of magnitude as rating's. This is the standard technique
for mixing signals with different distributions.

### 6.4 Score mode and boost mode

The `function_score` query is configured as:

    function_score:
      query: <the text-relevance bool query>
      functions:
        - field_value_factor: { field: rating,     factor: 1.0 }
        - field_value_factor: { field: popularity, factor: 0.5, modifier: log1p }
      score_mode: sum
      boost_mode: sum

`score_mode: sum` adds the two field contributions together.
`boost_mode: sum` adds that sum to the text-relevance score rather
than multiplying. Summation is chosen because the text score and the
business signals are on comparable scales after the log1p modifier.
Multiplication would make the business signal explode the text score
for high-popularity documents regardless of text relevance.

### 6.5 Why not a script_score

A `script_score` with a Painless script would allow arbitrary
combinations of business signals. It is rejected for Phase 9 because
it introduces a scripting surface that must itself be designed,
documented, and tested. The `function_score` query with predefined
functions is sufficient for the two signals the platform has, and it
is declarative rather than executable. A future phase that needs a
custom scoring function has a clear place to add it.

## 7. Relevance Strategy (9.8)

### 7.1 The strategy shape

The relevance engineering described in Sections 3-6 is implemented
as a new strategy in the Strategy Pattern established in Phase 3.5:

    LiteralSearchStrategy      (existing)
    NormalizedSearchStrategy   (existing)
    RelevantSearchStrategy     (new)

The new strategy uses a different gateway method: it does not just
pass text; it passes a fully composed relevance query. This is
implemented by extending ``ProductSearchGateway`` with a second
method, ``search_query``, that accepts a pre-built query dictionary.
The existing ``search`` method continues to exist for the simpler
strategies.

### 7.2 Why a new method rather than a new gateway

A new gateway would violate the domain's single contract for
searching products. The domain says "searching products is one
thing"; the difference between the strategies is *how* the search is
composed, not *what is being searched*. The method extension keeps
the port cohesive (four methods total on ``ProductSearchGateway``,
still under the ISP limit defined in docs/05).

### 7.3 How the strategy composes the query

The strategy delegates query construction to a new domain-level
component: a ``RelevanceQueryBuilder`` in the application layer that
knows the platform's relevance policy (boosts, business signals,
phrase clauses). The strategy does not contain policy itself; it
calls the builder.

This separation is deliberate. Relevance policy is a subject that
changes; the strategy is a mechanism that selects policy. Keeping
the policy in one place -- the builder -- means a change in field
weights is a change to one class, not to every strategy.

## 8. Rule for Changing Relevance

A relevance change is any change to field boosts, phrase boost
weights, business signal weights, or the query composition itself.
Such a change:

1. Is recorded in this document.
2. Is validated by an integration test asserting the expected
   ranking on a known fixture.
3. Is a candidate for benchmarking (Phase 22) if it affects query
   latency meaningfully.

Absent a labeled relevance corpus, a relevance change is a change
to a prior, not an optimization. The document says so plainly so
that future readers do not mistake the numbers here for measured
optima.

