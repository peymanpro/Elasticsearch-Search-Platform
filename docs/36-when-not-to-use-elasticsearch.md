# When Not to Use Elasticsearch

## 1. Purpose

This document is the last of the Phase 25 set, and it exists to make a
specific point: a developer who can only argue *for* a technology does
not fully understand it. Understanding a tool includes knowing where it
does not fit.

This document records scenarios in which Elasticsearch is the wrong
choice, and explains how the platform's own design reflects that
awareness. It covers Phase 25.7 of the master roadmap.

## 2. When Elasticsearch Is the Wrong Tool

### 2.1 As a system of record

Elasticsearch is not a database. It has weaker durability guarantees
than a purpose-built OLTP store: writes are acknowledged before they
are durable, refreshes are asynchronous, and a single-document write
is not transactional across indices.

**When this matters:** any system where the answer to "did my write
succeed?" must be a firm yes-or-no at the moment of the HTTP response,
and where a lost write is unacceptable.

**The platform's posture:** the JSONL dataset is the system of record.
Elasticsearch holds a derived, rebuildable index of that dataset.
If the index is lost, it is rebuilt from the dataset by the reindex
workflow (`docs/34-reindexing.md`). Nothing in the platform treats
Elasticsearch as the source of truth.

### 2.2 For transactional updates

An Elasticsearch "update" reads the current document, applies the
modification, and re-indexes the result. It is not a partial write;
it is a full re-index. Concurrent updates to the same document can
overwrite each other unless the caller uses optimistic concurrency
(the `if_seq_no` and `if_primary_term` parameters, or the `version`
field).

**When this matters:** any workflow that assumes a document is a
mutable record whose fields are updated independently. An inventory
counter that is decremented in place, a balance that is debited, a
status field that is updated under contention.

**The platform's posture:** the platform does not update documents in
place. Bulk re-loading replaces documents by their deterministic `_id`
(the SKU). See `docs/22-indexing.md` section 7.

### 2.3 For small, single-purpose lookups

If a system needs to answer a single question ? "what is the user with
this email?" ? Elasticsearch is over-engineered. A key-value store,
an in-memory cache, or a small relational table is faster, simpler,
and cheaper. The operational cost of running an Elasticsearch cluster
is real: memory, disk, and the time to tune and monitor it.

**When this matters:** any workload that does not need full-text
search, ranking, aggregations, or the flexible query model. If the
query is always the same shape and always exact-match, a different
tool wins.

**The platform's posture:** the platform is not used to solve the
problem of "one lookup by identifier". It is used to solve "many
different queries over a catalog, with ranking and facets". If a
future caller only wants "get product by SKU", they should not go
through Elasticsearch.

### 2.4 As a primary store for heavily relational data

Elasticsearch does not support joins. `parent-join` is available but
is a narrow, expensive feature. Querying "products in orders placed
by users in Europe last week" requires denormalization: the order,
the user, and the region must all be flattened into each product
document.

**When this matters:** any domain whose queries cross entities, and
any schema that is likely to evolve with new relationships. The
denormalized shape must be maintained on every write; getting that
wrong produces stale data that is hard to detect.

**The platform's posture:** the platform's document model has no
relations. A product is a self-contained record. That is a deliberate
choice to keep the search engineering on the search problem.

### 2.5 For analytics over terabytes of cold data

Elasticsearch is optimized for interactive search over a working set
of data. It is not optimized for analytics over datasets that are
rarely touched. For that workload, a columnar warehouse (ClickHouse,
BigQuery, DuckDB, Snowflake) is a better fit: they are cheaper per
byte stored and cheaper per byte scanned.

**When this matters:** when a business wants to run analytical queries
over years of historical records, most of which are never accessed
interactively.

**The platform's posture:** the catalog is measured in thousands to
hundreds of thousands of documents, all of which are searchable
interactively. Nothing in the platform is designed for cold-storage
analytics.

### 2.6 When the team cannot operate it

An Elasticsearch cluster is an operational artifact. It has a JVM
with a heap that must be sized; shards that must be assigned; a
cluster state that must be stable; a thread pool that must not be
exhausted; a disk that must not fill. None of it is difficult, but
all of it requires attention.

**When this matters:** any team that has no capacity to own the
operational side. A managed service (Elastic Cloud, AWS OpenSearch
Service) is the middle path. A different technology that is more
self-contained (SQLite FTS5, Meilisearch, Typesense) is the low-cost
path.

**The platform's posture:** this project is a demonstration, not a
production deployment. Its operational surface is exactly what
Phase 23 documents and no more. A production deployment would need
to add monitoring, alerting, capacity planning, and backup ? all of
which are out of scope here and are listed in
`docs/02-non-goals.md`.

## 3. What Elasticsearch Is Right For

By contrast, Elasticsearch is the correct tool for:

* Full-text search where ranking matters and the queries cannot be
  enumerated in advance.
* Faceted navigation and aggregation over a catalog.
* Autocomplete and search-as-you-type.
* Fuzzy matching and typo tolerance.
* Multilingual text search where per-language analyzers are needed.
* Any system where the query shape is flexible and the ranking
  algorithm must be tunable.

This platform is built for that set of problems. Every design decision
in `docs/00`?`docs/35` assumes the workload is one of the above.

## 4. The Meta-Point

The list of situations in Section 2 is not an apology for the project.
It is a consequence of the project being about one specific thing:
Elasticsearch search engineering. A repository that tried to also be a
system of record, also a workflow engine, also a reporting backend
would be a repository that failed to be any of them.

The platform's scope choices (`docs/02-non-goals.md`) are informed by
the knowledge that Elasticsearch is a search engine, not a general
purpose data platform. A reviewer who wants evidence that the platform
understands this should look at:

* `docs/22-indexing.md` section 7.3 ? idempotent loading, with the
  explicit statement that Elasticsearch is not the source of truth.
* `docs/23-index-lifecycle.md` section 8.2 ? the platform assumes a
  fixed dataset, not a stream of concurrent writes.
* `docs/02-non-goals.md` ? the excluded technologies that would be
  added if the platform drifted from its purpose.
* `docs/35-trade-offs.md` ? the recorded alternatives, several of
  which would be correct for a different project.

## 5. A Note on the Project's Own Limits

This project has the operational shape of a demonstration. It runs on
a single node, on a single machine, in Docker, with no authentication
and no metrics server. A reviewer should not conclude from the
repository that a real deployment would be operated this way. The
design documents describe what the *search engineering* looks like
when done properly; the *deployment engineering* is a separate
discipline and is out of scope.

## 6. Related Documents

* `docs/00-project-identity.md` ? the scope and principles.
* `docs/02-non-goals.md` ? every technology deliberately not used.
* `docs/22-indexing.md` ? how the platform avoids using
  Elasticsearch as a system of record.
* `docs/23-index-lifecycle.md` ? the assumption of a fixed dataset.
* `docs/35-trade-offs.md` ? the alternatives and their costs.
