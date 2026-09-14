# Trade-off Documentation

## 1. Purpose

This document records the design alternatives that were rejected, and
why. It exists because a design that cannot explain its rejected
alternatives is a design that was not made deliberately.

It covers Phase 25.6 of the master roadmap. The alternatives below are
grouped by the area they affect; the phase that made the decision is
noted alongside each.

## 2. Domain and Scope Trade-offs

### 2.1 Multilingual catalog: single-language vs. multilingual index

*Chosen:* single-language (English-only) catalog. (Phase 4.1)

*Alternative:* index every product twice with a `language` field, and
add a per-language analyzer chain for each supported language.

*Why not:* multilingual search is a distinct engineering problem
worth its own dataset and its own analyzers. Mixing it into a
single-purpose search platform would add configuration complexity
without adding demonstration value. The project is English-only by
user instruction; the decision is documented in `docs/09` section
3.1 and the multilingual sub-phase (4.3) is formally out of scope.

*Cost of the choice:* a future migration to multilingual would
require a reindex. That is acceptable and anticipated.

### 2.2 Product identity: `{sku}-{language}` vs. `sku`

*Chosen:* `sku` alone. (Phase 4.1)

*Alternative:* `{sku}-{language}` composite.

*Why not:* with a single-language catalog, the composite key carries
no additional information. The simple SKU is exactly the identity of
a document.

## 3. Index Design Trade-offs

### 3.1 `specifications`: flattened vs. object vs. explicit subfields

*Chosen:* `flattened`. (Phase 5.5, `docs/12`)

*Alternatives:* object with `dynamic: true` (silent mapping drift);
object with `dynamic: false` (unindexed subfields); explicit
subfields (rigid schema).

*Why flattened:* a general catalog spans categories with disjoint
attribute sets. Declaring every possible specification as a top-level
field would produce a sparse, rigid schema. Flattened avoids
dynamic-mapping drift while keeping arbitrary attributes searchable
as keywords.

*Cost of the choice:* flattened fields cannot serve numeric range
queries. A numeric spec that must be filtered is promoted to a
top-level field.

### 3.2 Analyzers: index-time vs. search-time synonyms

*Chosen:* search-time synonyms. (Phase 11.3, `docs/16`)

*Alternative:* index-time synonyms ? expand tokens in the inverted
index.

*Why search-time:* the vocabulary changes more often than the mapping
does. Search-time synonyms can be updated by editing the synonym
file and recreating the index; index-time synonyms would require a
full reindex for every vocabulary change.

*Cost of the choice:* phrase queries over the `name` field see
expanded terms, which is acceptable at the platform's scale. See
`docs/16` section 3.2 for the full trade-off table.

## 4. Query and Relevance Trade-offs

### 4.1 `multi_match` operator: `or` vs. `and`

*Chosen:* `or` (the default). (Phase 9.7, `docs/14`)

*Alternative:* `and` ? every query term must appear.

*Why `or`:* the default `or` is the least surprising choice for a
general catalog. A user who types two words typically expects any of
them to match, and a document that matches both is boosted by the
accumulated term scores. Switching to `and` would produce empty
results for queries where the user typed a word the catalog does not
contain.

*Cost of the choice:* a multi-word query can match documents that
contain only some of the terms. The field boosts reduce the effect,
and the exact-phrase `should` clause rewards the best matches.

### 4.2 Fuzzy placement: opt-in strategy vs. always-on

*Chosen:* opt-in via the `FUZZY` intent. (Phase 10.4, `docs/15`)

*Alternative:* apply fuzziness to every search.

*Why opt-in:* fuzzy matching changes what "match" means. A search
for "tv" that quietly matches "to" and "ten" is not a search for
"tv". The default search must be honest; fuzzy is offered as a
fallback a caller chooses when an exact search failed.

*Cost of the choice:* the API does not implement a "retry fuzzy on
zero results" policy. That is a caller decision; the mechanism is
available.

### 4.3 Synonyms: equivalence vs. explicit mapping

*Chosen:* equivalence (`tv,television,telly`). (Phase 11.1)

*Alternative:* explicit mapping (`tv => television`).

*Why equivalence:* the platform's vocabulary is symmetric. A user may
type either form; both should match the same documents. Explicit
mapping is useful when one direction is meaningful and the other is
not (an acronym whose expansion is a phrase).

### 4.4 Pagination: `search_after` vs. raising `max_result_window`

*Chosen:* `search_after` for deep pagination; the platform's
`Pagination` value object rejects pages beyond the window. (Phase
15.5, `docs/20`)

*Alternative:* raise `max_result_window` and use `from`/`size`
everywhere.

*Why `search_after`:* raising the window moves the limit but does
not remove it, and makes an out-of-memory condition possible.
`search_after` uses the sort order of the last hit on the previous
page as a cursor; the cost does not grow with depth.

### 4.5 Field boosts: tuned vs. reasoned priors

*Chosen:* reasoned priors (`name^3.0`, `brand^2.0`, ...). (Phase 9.2)

*Alternative:* tune the weights against a labeled relevance corpus.

*Why not tuning:* the platform has no labeled corpus. Tuning without
labels would be guesswork dressed as optimization. The weights are
recorded, the tests assert ranking order, and a future project with
labeled data can revisit them.

### 4.6 Business signals: `function_score` vs. `script_score`

*Chosen:* `function_score` with `field_value_factor`. (Phase 9.7)

*Alternative:* `script_score` with a Painless script.

*Why `function_score`:* a script would allow arbitrary combinations
of business signals, but it would also introduce a scripting surface
that must itself be designed, documented, and tested. The two signals
the platform has (rating and popularity) are expressible with the
predefined functions.

## 5. Architecture Trade-offs

### 5.1 Repository vs. Gateway

*Chosen:* domain-declared gateways, not a repository. (Phase 3.8,
`docs/08`)

*Alternative:* a `ProductRepository` that represents a persistent
collection.

*Why not a repository:* the platform does not have a persistent
collection. It has a search operation that returns a page of results.
A repository would be a second abstraction over the same concern with
no second concrete behavior to justify it.

### 5.2 Single app vs. multiple apps

*Chosen:* a single Django app (`apps.search`). (Phase 2.1)

*Alternative:* split into `apps.catalog`, `apps.search`,
`apps.search_api`, etc.

*Why single:* the platform's domain is cohesive. Splitting it would
create artificial boundaries that would then need to be crossed. A
second app would be justified by a second bounded context (a
different domain) ? which the platform does not have.

### 5.3 Django middleware vs. DRF-level correlation

*Chosen:* a Django middleware. (Phase 24.4)

*Alternative:* an DRF `Authentication`-style class, a decorator, or
explicit setup in each view.

*Why middleware:* it runs once per request, wraps the whole request
lifecycle, and can emit both the start and the end event. A
DRF-level class would miss the response-rendering phase; a decorator
would need to be applied to every view.

### 5.4 Log format: key=value vs. JSON

*Chosen:* key=value pairs. (Phase 24.2)

*Alternative:* structured JSON.

*Why key=value:* it is what a human reads easily in a terminal. The
platform does not have a log processor that would benefit from JSON.
A deployment that wanted JSON could add a JSON formatter and leave
the log-event structure unchanged.

## 6. Operational Trade-offs

### 6.1 Retry: bulk retries, search does not

*Chosen:* bulk operations retry under a bounded policy; search does
not. (Phase 23.3, `docs/28`)

*Alternative:* apply a search-level retry.

*Why:* a search is a user-facing request. Making a user wait through
a retry is usually worse than returning an error the UI can handle.
A background reindex has no user waiting and its work is expensive to
redo, which is why it retries and search does not.

### 6.2 Resilience: circuit breaker vs. timeout + retry

*Chosen:* timeouts and retry, no circuit breaker. (Phase 23, `docs/28`)

*Alternative:* a circuit breaker that stops issuing requests to a
known-bad cluster.

*Why not:* the platform does not have enough concurrent load for the
state machine to be meaningful. A production system with real traffic
would benefit from one.

### 6.3 Content: what is logged vs. what is not

*Chosen:* log the query's *length*, not its content. (Phase 24.3)

*Alternative:* log the query text itself.

*Why not:* a user's search query can contain arbitrary content and,
in a production system, could contain PII. The operational signal is
the query's length and duration, not the text.

## 7. Data Handling Trade-offs

### 7.1 Dataset on disk vs. database as source of truth

*Chosen:* the JSONL dataset is the source of truth. (Phase 4.2,
`docs/22`)

*Alternative:* a relational database that holds the canonical
records and pushes updates to Elasticsearch.

*Why not:* the platform has no relational workload. Introducing a
database as a second source of truth would create a synchronization
problem unrelated to the search capabilities being demonstrated. A
change to a document is a change to the dataset, and the dataset is
loaded into the index by the same bulk path that the platform uses
for initial loading.

### 7.2 Reindex from dataset vs. from index

*Chosen:* rebuild from the dataset. (Phase 18.5, `docs/23`)

*Alternative:* Elasticsearch's `_reindex` API ? copy documents
server-side from one index to another.

*Why from the dataset:* the dataset is already treated as the
authority; rebuilding from it keeps that invariant intact. `_reindex`
would copy old-shaped documents into a new mapping, which works for a
pure type change but not for a shape change. The rebuild pays the
parsing cost, which is negligible at the platform's scale.

## 8. What This Document Does Not Do

* **It does not record every micro-decision.** A variable name is
  not a trade-off. The entries above are decisions a reviewer would
  question if they were not explained.
* **It does not claim the alternatives were wrong.** Every
  alternative listed is legitimate in a different context. What the
  document records is why the chosen approach fits this project's
  context.
* **It is not exhaustive of the future.** New trade-offs discovered
  in later phases go into the corresponding design document, not
  here. This document consolidates what exists today.

## 9. Related Documents

* `docs/02-non-goals.md` ? what the project does not do, and why.
* `docs/08-pattern-review.md` ? the design-pattern review that
  decided which patterns were kept.
* `docs/14-relevance.md` ? the relevance decisions in detail.
* `docs/23-index-lifecycle.md` ? the reindex design.
* `docs/28-operational-resilience.md` ? the operational decisions.
