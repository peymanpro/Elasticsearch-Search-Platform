# Success Criteria — Project Acceptance

## 1. Purpose

This document defines the criteria by which the project will be judged
complete. It exists so that "done" is a measurable claim rather than an
opinion, and so that every phase can be evaluated against concrete
acceptance criteria.

The criteria are organized by dimension:

- **Functional** — the search behaviors that must exist and be correct.
- **Technical / Elasticsearch** — the specific Elasticsearch capabilities
  that must be demonstrated with design rationale.
- **Architectural** — the structural properties the codebase must exhibit.
- **Quality** — testing, error handling, and correctness.
- **Performance** — what must be measured, and what may not be claimed.
- **Operational** — resilience and observability.
- **Documentation** — the technical writing that accompanies the code.

Each criterion is stated so that it can be checked by inspecting the
repository. "Yes" or "no", not "sort of".

## 2. Functional Criteria

- **FC-1** Full-text search across product name, description, brand,
  category, and tags, with field weighting and BM25 scoring.
- **FC-2** Phrase-aware matching works: `match_phrase` influences ranking
  when the query matches a contiguous phrase in the document.
- **FC-3** Fuzzy matching accepts controlled typos (e.g. `mindrey` →
  `Mindray`) with a bounded false-positive rate.
- **FC-4** Synonym expansion works for the defined medical vocabulary
  (`ECG` ↔ `electrocardiogram`, `BP` ↔ `blood pressure`, etc.).
- **FC-5** Autocomplete returns relevant suggestions for prefixes
  (`moni` → `monitor`, `monitoring`).
- **FC-6** Filtering by category, brand, availability, price range, and
  rating range works and combines with full-text search.
- **FC-7** Aggregations return category, brand, availability, and price
  buckets for faceted navigation.
- **FC-8** Sorting works by relevance, price, rating, and recency, with a
  deterministic tie-breaker.
- **FC-9** Pagination works via `from`/`size` and via `search_after` for
  deep pagination.
- **FC-10** Highlighting returns matched-term fragments for the searched
  fields.
- **FC-11** The `_explain` API is exposed and returns a meaningful scoring
  breakdown for a (query, document) pair.
- **FC-12** English and Persian queries are both handled correctly, with
  Persian character normalization verified by tests.

## 3. Technical / Elasticsearch Criteria

For each of the following, the repository must contain **all three**:

1. The implementation.
2. A written engineering decision (problem → options → choice → rationale
   → trade-offs → how it is tested).
3. A test that demonstrates the capability.

Required capabilities:

- **EC-1** Explicit mapping (no reliance on dynamic mapping for domain
  fields).
- **EC-2** Multi-fields (`text` + `keyword`) where both search and
  aggregation/sort are required on the same logical field.
- **EC-3** Custom analyzers for English and Persian, verified with
  `_analyze`.
- **EC-4** Query DSL coverage: `bool` (with `must`/`should`/`filter`/
  `must_not`), `match`, `multi_match`, `match_phrase`, `term`, `range`,
  fuzzy match.
- **EC-5** Relevance engineering: field boosts, exact-match boost, phrase
  boost, controlled fuzzy parameters.
- **EC-6** Synonym handling with a documented search-time vs. index-time
  decision.
- **EC-7** Autocomplete via `search_as_you_type` (or a documented
  alternative with equivalent behavior).
- **EC-8** Highlighting configured per field.
- **EC-9** Aggregations: `terms` and `range`, combined with filtered
  results.
- **EC-10** Bulk indexing with idempotent document IDs and explicit
  partial-failure handling.
- **EC-11** Versioned physical indices behind a stable alias.
- **EC-12** Reindexing workflow with validation and atomic alias switch.
- **EC-13** A documented and demonstrated rollback path.
- **EC-14** `_explain` integration exposed through the API.

## 4. Architectural Criteria

- **AC-1** Clean Architecture dependency rule is respected: the domain
  layer imports neither Django nor the Elasticsearch client.
- **AC-2** The application layer coordinates use cases and depends on
  domain contracts, not on the Elasticsearch client.
- **AC-3** The infrastructure layer is the only layer that talks to
  Elasticsearch directly.
- **AC-4** Every abstraction (interface, factory, strategy, builder)
  exists to solve a concrete problem, and that problem is documented.
  Abstractions without a documented reason are removed.
- **AC-5** Design patterns applied are recorded, and each has passed the
  Phase 3.8 review (keep / simplify / remove).
- **AC-6** No dependency exists solely because it is fashionable, and no
  technology excluded by `docs/02-non-goals.md` is present.

## 5. Quality Criteria

- **QC-1** Automated tests exist at the unit level for the domain rules.
- **QC-2** Automated tests exist at the query-builder level that assert
  the *shape* of the generated Elasticsearch DSL, not just the API
  response.
- **QC-3** Automated tests exist at the analyzer level, using `_analyze`
  against a real Elasticsearch.
- **QC-4** Relevance tests assert expected ranking for a curated query set.
- **QC-5** Integration tests exercise the API → application →
  Elasticsearch path against a running cluster.
- **QC-6** Failure tests simulate Elasticsearch unavailability, timeouts,
  missing indices, and bulk partial failures, and assert the expected
  behavior.
- **QC-7** Reported test results come only from actual executions.
  Un-executed tests are never reported as passing.

## 6. Performance Criteria

- **PC-1** A benchmark harness exists, is deterministic, and is
  reproducible.
- **PC-2** The benchmark workload covers: exact match, fuzzy match, phrase
  match, aggregation, and autocomplete.
- **PC-3** Indexing throughput is measured for bulk ingestion at
  small / medium / large dataset sizes.
- **PC-4** Reindex duration is measured.
- **PC-5** Reported numbers come only from actual measurements, on a
  documented hardware and software configuration.
- **PC-6** No universal performance claim is made. The project
  characterizes *this* implementation under *defined* workloads.

## 7. Operational Criteria

- **OC-1** The Elasticsearch client is managed by a single component with
  configured timeouts and connection limits.
- **OC-2** Elasticsearch unavailability produces a defined, documented
  API response (never an unhandled traceback).
- **OC-3** Missing indices are detected and reported meaningfully.
- **OC-4** Bulk partial failures are handled: failed items are extracted,
  retried under a bounded policy, and reported.
- **OC-5** Structured logs are emitted for search operations, indexing
  operations, and errors, with a correlation ID propagated from the HTTP
  request.
- **OC-6** Search duration and indexing outcomes are measurable from the
  logs or metrics endpoint.

## 8. Documentation Criteria

- **DC-1** `README.md` describes the project, how to run it, and what it
  demonstrates.
- **DC-2** An architecture document exists and matches the code.
- **DC-3** An index-design document exists with per-field rationale.
- **DC-4** An analyzer document exists with rationale for each analyzer.
- **DC-5** A relevance document exists explaining the ranking strategy.
- **DC-6** A reindexing document exists describing the zero-downtime
  workflow and the rollback path.
- **DC-7** A trade-offs document exists capturing the alternatives that
  were rejected and why.
- **DC-8** A document exists explaining *when not to use Elasticsearch*,
  demonstrating that the project's author understands Elasticsearch's
  limits as well as its strengths.
- **DC-9** Swagger UI is populated with realistic example queries for each
  endpoint, and each example is executable against a running cluster.
- **DC-10** All documentation is in English. Persian appears only as
  search data in the dataset and in test fixtures, never in prose.

## 9. The Final Question

A reviewer inspecting this repository should be able to answer **yes** to:

> "Does this developer genuinely understand Elasticsearch beyond basic
> CRUD and search calls?"

The criteria above exist to make that answer demonstrable rather than
aspirational.

## 10. Rule for Changing These Criteria

Criteria may be strengthened. They may be weakened only when a concrete
constraint makes the original criterion impossible, and the weakening is
recorded as a decision document under `docs/` with the problem, the
alternatives, and the reason.
