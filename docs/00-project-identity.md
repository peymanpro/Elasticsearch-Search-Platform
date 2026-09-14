# Project Identity — Elasticsearch Search Platform

## 1. The Problem This Project Addresses

Many repositories claim to "use Elasticsearch" but do little more than call
`client.search()` against an index created by dynamic mapping, and then wrap
the call in CRUD endpoints. That is not search engineering; it is API plumbing
with a search library attached.

Search is its own engineering discipline. It has a design space: mapping
choices, analyzer choices, relevance choices, index lifecycle choices, and
failure-handling choices. Each decision has trade-offs, and each trade-off
must be made explicitly rather than inherited by accident.

This repository exists to demonstrate that discipline end to end.

## 2. What This Repository Is

A **search platform for medical products** built on Elasticsearch, exposed
through a Django REST Framework API, structured according to Clean
Architecture.

The medical-product domain is not the point. It is a realistic carrier for
search problems that general search systems face: multilingual text,
domain vocabulary, brand and category facets, numeric ranges, structured
attributes, and ranking that must consider both textual relevance and
controlled business signals.

The point is the engineering. The domain makes the engineering concrete.

## 3. What "Search Platform" Means Here

Not a single endpoint. A platform, in the following sense:

- **Index design** — explicit mappings chosen per field based on how that
  field is searched, filtered, sorted, or aggregated.
- **Text analysis** — custom analyzers designed for the actual text the
  platform ingests, not the default `standard` analyzer taken for granted.
- **Ingestion** — bulk indexing with idempotent document identifiers,
  batching, partial-failure handling, and retry strategy.
- **Lifecycle** — versioned physical indices behind stable aliases, with
  reindexing, validation, atomic alias switching, and rollback.
- **Relevance** — BM25 understood rather than inherited, field boosting,
  phrase and exact-match boosts, fuzzy matching with controlled fuzziness,
  and synonym-driven query expansion.
- **Query capabilities** — full-text search, filtering, faceted search,
  autocomplete, highlighting, sorting, and pagination (including
  `search_after` for deep pagination).
- **Explainability** — the platform can explain why a document ranked where
  it did, using the `_explain` API and structured scoring analysis.
- **Operability** — explicit handling of Elasticsearch unavailability,
  timeouts, missing indices, and bulk failures; structured logging and
  basic metrics for the search path.

## 4. Scope: Elasticsearch-First

Elasticsearch is the center of gravity. Django is a delivery mechanism for
exposing the platform over HTTP and for providing a documented OpenAPI
surface.

Consequently:

- Every non-trivial Elasticsearch capability that appears in the roadmap
  must be implemented with a written rationale and with tests that
  demonstrate it.
- Django-specific features that do not serve the search problem are out
  of scope, even if they are convenient.
- The architecture is organized so that the domain and application layers
  do not depend on Elasticsearch or Django directly. Infrastructure adapts
  Elasticsearch to domain contracts; presentation adapts HTTP to
  application use cases.

## 5. What This Repository Is Not

To protect the scope:

- **Not** a CRUD demo with a search endpoint bolted on.
- **Not** a Django tutorial.
- **Not** a Persian-only or English-only project. It supports both languages
  specifically because multilingual analysis is a real search-engineering
  problem worth demonstrating.
- **Not** a microservices project. One deployable application is sufficient.
- **Not** an authentication, payments, or user-management project. These
  problems are unrelated to search engineering.
- **Not** a frontend project. The API and Swagger UI are the user surface.
- **Not** a distributed-systems showcase. A single-node Elasticsearch is
  sufficient to demonstrate every capability in the roadmap.
- **Not** an infrastructure project. Redis, RabbitMQ, PostgreSQL, and
  message brokers are deliberately excluded unless a specific search
  requirement demands them and the rationale is recorded.

## 6. Engineering Principles Applied

The following principles govern implementation. They are listed here so
that later decisions can be checked against them.

- **Clean Architecture** with explicit dependency rules. The domain layer
  knows nothing about Elasticsearch or Django.
- **SOLID**, applied where it improves testability, extensibility, or
  separation of concerns — and *not* applied as ceremony. Abstractions
  without a concrete problem to solve are removed.
- **Design patterns** (Strategy, Builder, Adapter, Factory, Specification,
  Repository) only when the problem actually benefits from them. The
  review step of each pattern is documented.
- **Documented trade-offs.** Non-obvious decisions (mapping types, analyzer
  choices, fuzzy parameters, synonym placement, pagination strategy,
  reindexing workflow) are recorded as engineering decisions with the
  problem, options considered, chosen approach, rationale, and how the
  choice is verified.
- **Honest reporting.** Tests are reported only when actually executed.
  Benchmarks are reported only when actually measured. No invented
  numbers, no assumed results.

## 7. What "Done" Means

The repository is not done merely when the endpoints exist. It is done when
it demonstrates, in an inspectable form:

- explicit Elasticsearch mappings with per-field rationale,
- custom analyzers verified by analyzer-level tests,
- English and Persian search treated as first-class,
- Query DSL used deliberately (bool, match, multi_match, match_phrase,
  term, range, fuzzy),
- relevance engineered rather than inherited,
- synonyms, autocomplete, and highlighting implemented and tested,
- filtering, aggregations, and faceted search implemented and tested,
- explainability exposed via API,
- bulk indexing with idempotency and partial-failure handling,
- versioned indices, aliases, zero-downtime reindexing, and rollback,
- automated unit, integration, relevance, and failure tests,
- reproducible benchmarks with recorded results,
- operational handling of Elasticsearch failures,
- professional Swagger documentation,
- a professional README and technical documentation.

## 8. Non-Negotiable Constraints

- All engineering content in the repository is written in **English**.
  Persian text may appear only as search data, never as documentation.
- No unrelated technologies are introduced without a recorded requirement.
- Implementation proceeds in small, verifiable steps. No large
  unverifiable changes.
- Git history is composed of small, logically-scoped commits with
  descriptive messages.
- Every completed sub-phase has: design, implementation, verification,
  test, documentation, and commit.
