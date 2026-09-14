# Non-Goals — Explicit Exclusions

## 1. Purpose

This document records what the project deliberately does **not** do, and
why. It exists to protect the search-engineering focus of the repository
against scope drift, feature creep, and the temptation to turn it into a
broader application.

Each exclusion below is a deliberate decision, not an oversight. Any future
change to this list must be justified by a concrete Elasticsearch capability
that cannot be demonstrated without it, and the justification must be
recorded in the project history.

## 2. Product and Business Exclusions

### 2.1 User accounts, authentication, and authorization

**Excluded.** No login, registration, JWT, OAuth, session, or permission
system.

**Reason.** Authentication is a solved, well-understood problem and has no
relationship to search engineering. Adding it would inflate the codebase
and distract from the Elasticsearch capabilities the project exists to
demonstrate. The API is exposed unauthenticated, on the assumption that it
is a demonstration surface, not a production service.

### 2.2 Payment, cart, checkout, order management

**Excluded.** No commerce flow of any kind.

**Reason.** These are transactional concerns. They belong to a different
class of system and would require an OLTP database and transactional
semantics that are not relevant to search. Elasticsearch is deliberately
not used as a system of record here.

### 2.3 Recommendation and personalization

**Excluded.** No "users who viewed this also viewed", no collaborative
filtering, no learning-to-rank model.

**Reason.** Ranking in this project is explicitly engineered and
explainable through BM25, field boosts, and controlled business signals.
Black-box ranking would obscure the explainability requirement (FR-11)
and the relevance-engineering chapter (Phase 9).

### 2.4 Inventory, pricing, and promotions logic

**Excluded.** The dataset contains price and availability as **searchable
and filterable fields**, not as a managed inventory system.

**Reason.** Inventory management is a business-rule problem, not a search
problem. The platform treats price and availability as data to be
searched, sorted, and aggregated — nothing more.

### 2.5 Admin panel and content management

**Excluded.** No Django admin customization beyond what is needed to run
the application, no CMS, no product-editing UI.

**Reason.** The interaction surface of this project is the HTTP API and
Swagger UI. Building administrative CRUD is orthogonal to search and
would be a Django demonstration rather than an Elasticsearch one.

## 3. Infrastructure and Architecture Exclusions

### 3.1 Microservices

**Excluded.** The system is a single Django application.

**Reason.** Splitting a focused search service into microservices would
add distributed-systems complexity with no search-engineering benefit. One
deployable unit is sufficient to demonstrate every capability on the
roadmap.

### 3.2 Message brokers (Kafka, RabbitMQ, Redis Streams)

**Excluded.** No event-driven ingestion pipeline.

**Reason.** Bulk ingestion and reindexing are demonstrated synchronously
through the Elasticsearch Bulk API and management commands. A message
broker would introduce a dependency whose failure modes are not part of
the search problem.

### 3.3 Relational database (PostgreSQL, MySQL, SQLite as system of record)

**Excluded.** Django is configured to run without a persistent relational
database for search data. The source of truth for indexed documents is
the JSONL dataset on disk.

**Reason.** Elasticsearch is the subject. Introducing a relational
database as a second source of truth would create a synchronization
problem that has nothing to do with the search capabilities being
demonstrated, and would tempt the project toward becoming a CRUD demo
with a search sidecar.

### 3.4 Caching layer (Redis, Memcached)

**Excluded.** No response caching, no query cache.

**Reason.** Search performance is characterized via Elasticsearch itself
and the benchmark harness. An external cache would obscure the actual
Elasticsearch latency that the benchmarks are meant to measure.

### 3.5 Multiple Elasticsearch nodes / clustering

**Excluded.** A single-node Elasticsearch is used.

**Reason.** Every capability on the roadmap (analyzers, relevance, fuzzy,
synonyms, aggregations, aliases, reindexing) is demonstrable on a single
node. Multi-node clustering adds operational complexity without adding
search-engineering demonstration value.

### 3.6 Kubernetes, Terraform, or cloud deployment

**Excluded.** Local Docker Compose only.

**Reason.** The project is a technical demonstration, not a deployment
exercise. Infrastructure-as-code would be a separate project.

## 4. Application-Level Exclusions

### 4.1 Frontend application

**Excluded.** No SPA, no server-rendered UI, no JavaScript build.

**Reason.** The HTTP API is the product surface, and Swagger UI is the
human interface used to demonstrate it. A frontend would consume
engineering time without adding to the Elasticsearch demonstration.

### 4.2 Background task queue (Celery, RQ, Dramatiq)

**Excluded.** No asynchronous task workers.

**Reason.** Ingestion and reindexing are performed through explicit
management commands and API endpoints. Their behavior is meant to be
observed directly, not hidden behind a task queue.

### 4.3 Mobile or desktop clients

**Excluded.** No client applications of any kind.

**Reason.** Same reasoning as 4.1.

### 4.4 Internationalization framework beyond search

**Excluded.** Django's `i18n` and translations of API messages are not a
goal. English is the only language of the API, its documentation, and its
error messages.

**Reason.** The project is multilingual **in its search data**, not in its
user interface or documentation. Conflating the two would blur the
distinction the project is built to make: that multilingual search is an
analyzer and mapping problem, not a translation problem.

## 5. Elasticsearch Features Deliberately Not Demonstrated

Some Elasticsearch features exist that are powerful, well-known, and
tempting to include. They are excluded for the reasons given.

### 5.1 Machine-learning features (anomaly detection, LTR, NLP inference)

**Excluded.** No ML nodes, no inference pipelines, no learning-to-rank.

**Reason.** These features depend on licensed tiers or external model
artifacts, and they would obscure the fundamental relevance engineering
that the project exists to demonstrate. BM25 and boost composition are the
subject, not neural ranking.

### 5.2 Vector search / dense_vector / kNN

**Excluded.** No semantic / vector search.

**Reason.** Vector search is a distinct sub-discipline that deserves its
own dedicated project. Adding it here would dilute the focus on classical
lexical search and ranking.

### 5.3 Cross-cluster search and cross-cluster replication

**Excluded.** Single-cluster only.

**Reason.** Requires multiple clusters, which is already excluded (3.5).

### 5.4 Watcher, Alerting, and anomaly detection

**Excluded.** No alerting.

**Reason.** Operational alerting is unrelated to the search capabilities
being demonstrated, and its inclusion would be a monitoring project, not a
search one.

### 5.5 Snapshot and restore to remote repositories

**Excluded.** No snapshot lifecycle management to S3-compatible backends.

**Reason.** Backup and restore is an operational concern orthogonal to
search engineering. Local index lifecycle (aliases, reindexing, rollback)
is demonstrated without it.

## 6. Testing and Documentation Exclusions

### 6.1 Load testing with external frameworks

**Excluded.** No Locust, k6, or JMeter integration.

**Reason.** Benchmarks are implemented as an internal Python harness so
that they measure the platform's real query path, not an HTTP proxy
layer. Introducing a separate load-testing tool would measure a different
system.

### 6.2 Chaos engineering

**Excluded.** No automated fault injection frameworks.

**Reason.** Failure handling is verified by explicit unit and integration
tests that simulate the relevant failure modes (Section 21.8 of the
roadmap). A chaos framework would add complexity without improving the
verification.

## 7. Rule for Revisiting This List

An item may be removed from this list only when **all** of the following
are true:

1. A concrete capability from the master roadmap cannot be demonstrated
   without it.
2. The addition does not violate the architectural constraints defined in
   `docs/00-project-identity.md` Section 8.
3. The justification is recorded as a decision document under `docs/`,
   with the problem, the alternatives, the chosen approach, and the
   trade-offs.

Absent all three, the exclusion stands.
