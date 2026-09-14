# Project Status

One-page, honest status of the Elasticsearch Search Platform.
Reviewed against the actual repository, not from memory.

Last updated at commit: `be9ac3a` (Phase 26.4).

---

## Implemented and tested

These capabilities are implemented, exercised by automated tests,
and reachable through the HTTP API.

- Product document model with explicit Elasticsearch mapping.
- Custom text analysis: standard analyzer, lowercase, ASCII
  folding, and a versioned synonym filter.
- Query DSL: `multi_match` with field boosts, `match_phrase` with
  slop, `bool` with `must`/`should`/`filter`/`minimum_should_match`,
  `fuzzy`, and function score boosting.
- Relevance: field boosts plus function scoring. See
  `docs/14-relevance.md` and `docs/33-relevance.md`.
- Fuzzy search with configurable fuzziness and prefix length.
- Autocomplete: edge n-grams and completion suggester.
- Highlighting of matched fragments per field.
- Filtering by category, brand, price range, rating range, and
  availability.
- Facets: terms aggregations for category, brand, availability;
  range aggregation for price.
- Sorting and pagination: offset-based (`page`/`page_size`) and
  cursor-based (`search_after`) with a stable tie-breaker.
- Explainability: `POST /api/explain/` returns the scoring tree.
- Bulk indexing with batching and retry on transient failures.
- Zero-downtime reindexing via index aliases, with a management
  command and a status command.
- Operational resilience: connection timeouts are treated as
  transient; retries use exponential backoff.
- Observability: correlation IDs and structured logging.
- HTTP API on Django REST Framework with drf-spectacular OpenAPI
  and Swagger UI.

---

## Test coverage

- **452 tests passing** at commit `be9ac3a`.
- Three test groups:
  - `tests/unit/` — pure unit tests, no Elasticsearch.
  - `tests/integration/` — require a running Elasticsearch 8.15.3.
  - `tests/architecture/` — enforce Clean Architecture dependency
    rules and interface segregation.
- Gates run on every commit: `ruff check .`, `ruff format --check .`,
  `pytest -q`. All three currently pass.

---

## Benchmarked

The benchmark harness lives in `benchmarks/`. Recorded results and
their interpretation are in `docs/27-benchmarking.md`.

Measured workloads cover search latency and indexing throughput on
the project fixture. A large-dataset measurement has not been done.

---

## Deferred

Deliberately out of scope or postponed, with reasons:

- **Multilingual / Persian analyzers.** Out of scope per the project
  non-goals. The analysis pipeline is English-only by design.
- **Phrase boost on `description`.** Deferred because the effect is
  unmeasurable on the current fixture; it would be added when a
  dataset where it changes ranking is available.
- **Reindex timing benchmark.** Deferred. A correct measurement
  needs a stable index size and a dedicated run; not done yet.
- **Large-dataset benchmark.** The current fixture is small enough
  to be fast on a laptop; a large-scale measurement has not been
  run.

---

## Known limitations

- Single-node Elasticsearch. No replica shards, no failover
  semantics. Sufficient for demonstrating search engineering, not
  for production availability.
- No authentication or authorization. The API is open by design;
  this is not a production security posture.
- No horizontal scaling story. The platform is a single Django
  process talking to a single Elasticsearch node.
- The API returns HTTP 200 for unhealthy states on `/api/health/`
  with a JSON body carrying the status. Callers must inspect the
  body, not the status code.
- The `explanation` object in `POST /api/explain/` is intentionally
  not fully described in the OpenAPI schema. The recursion contract
  is owned by the domain and tested there.

---

## What is not here

The project is deliberately narrow. It does not include, and will
not include: PostgreSQL, Redis, RabbitMQ, a frontend, authentication,
or payments. See `docs/02-non-goals.md` for the full list.

