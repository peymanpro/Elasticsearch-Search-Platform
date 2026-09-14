# Elasticsearch Fundamentals

## 1. Purpose

This document covers the two foundational Elasticsearch topics that
the platform relies on for everything that follows:

    * Section 2 -- the topology of a cluster (nodes, indices, shards).
    * Section 3 -- the lifecycle of a document (create, read, update,
      delete).

It is deliberately narrow. Index design -- settings, mapping, field
types, analyzers -- is the subject of docs/12-index-design.md.

## 2. Cluster, Node, Index

### 2.1 The concepts

A **cluster** is a set of Elasticsearch processes that together hold
data and answer queries. Each process is a **node**. Nodes coordinate
through a shared cluster name and a discovery protocol.

An **index** is a named collection of documents with a common mapping.
An index is split into **shards**; each shard is a Lucene index that
can be moved between nodes and replicated.

A **document** is one JSON object stored in an index, identified by a
unique `_id` within that index.

### 2.2 This project's topology

The development cluster is defined in `docker-compose.yml`:

    * one cluster, named `esp-cluster`
    * one node, named `esp-node-01`, running Elasticsearch 8.15.3
    * one data path, on a container-local volume

A single-node cluster is sufficient to demonstrate every capability on
the roadmap. Multi-node clustering adds operational complexity (shard
allocation, replica management, split-brain avoidance) without adding
search-engineering demonstration value. See docs/02-non-goals.md
section 3.5.

### 2.3 Why this matters for the platform

Two facts about the topology shape the rest of the project:

1. **Only one node.** Replication is not usable. Any index created
   by the platform sets `number_of_replicas: 0`. Setting replicas on
   a single-node cluster leaves shards unassigned and the cluster
   stuck in yellow. This is the correct configuration for a single-
   node development cluster.

2. **Cluster name is stable.** The compose file names the cluster
   `esp-cluster`. Integration tests that assert the cluster name are
   asserting a fact about the environment, not the code -- but they
   are useful as a smoke check that the expected stack is running.

### 2.4 Code surface

The infrastructure layer exposes cluster facts through
`infrastructure.elasticsearch.health`:

    * `ping()` -- is the cluster reachable?
    * `cluster_info()` -- the cluster's identity (name, version).
    * `cluster_health()` -- the cluster's health status.
    * `nodes_info()` -- the nodes' details.

Only `ping()` and `cluster_info()` are used by the platform's API
today. `cluster_health()` and `nodes_info()` exist for integration
tests and for the operational tooling of Phase 23.

## 3. Document Lifecycle

### 3.1 The four operations

Elasticsearch exposes four fundamental operations on a document:

| Operation | HTTP | Effect |
|---|---|---|
| Create or replace | PUT /<index>/_doc/<id> | Indexes the document, overwriting any existing document with the same id |
| Read | GET /<index>/_doc/<id> | Returns the document's _source |
| Update | POST /<index>/_update/<id> | Applies a partial update to the document |
| Delete | DELETE /<index>/_doc/<id> | Removes the document from the index |

Bulk variants exist (`_bulk`) and are the subject of Phase 17. This
section is about the single-document operations.

### 3.2 Create and replace are the same call

`PUT /<index>/_doc/<id>` is idempotent: if the id does not exist, the
document is created; if it exists, the document is replaced. The
response status distinguishes the two (201 for created, 200 for
updated), but from the application's perspective the operation is the
same: after the call, the index contains exactly one document with the
given id and the given source.

This is why the platform uses the SKU as the document id
(docs/09 section 3.4). Re-ingesting the catalog produces no duplicates.

### 3.3 Update is a reindex behind the scenes

Despite the name, `_update` is not a partial write to the stored
document. It reads the current document, applies the modification,
and re-indexes the result. Two consequences follow:

    * An update to a large document is not cheaper than indexing
      that document.
    * The updated document is re-analyzed. If the mapping has
      changed, the update fails.

The platform does not use `_update` for its catalog. Every product
document is written in full by the bulk indexer (Phase 17). Partial
updates are useful in OLTP-style systems where a document is a
long-lived record. Here, the source of truth is the JSONL dataset,
which is regenerated rather than edited.

### 3.4 Delete and the `_delete_by_query` alternative

`DELETE /<index>/_doc/<id>` removes a single document. Removing a set
of documents by a query uses `_delete_by_query`, which runs a search
and deletes matches. The platform does not use `_delete_by_query`:
catalog refresh replaces documents by re-indexing, and Phase 18
handles full catalog replacement through reindexing, not deletion.

### 3.5 Refresh and visibility

A write becomes visible to a search only after a **refresh**. By
default, Elasticsearch refreshes an index once per second. This is
why a bulk index followed immediately by a search can appear to miss
documents: the bulk has completed, but the refresh interval has not
elapsed.

The platform addresses this in three places:

    * Integration tests that index a document and immediately search
      for it call `POST /<index>/_refresh` first.
    * The bulk indexer (Phase 17) uses the `refresh=wait_for`
      parameter on the final batch, so the caller knows when the
      writes are visible.
    * Production behavior is unaffected: a one-second visibility lag
      is appropriate for a search index.

### 3.6 What the platform actually does

Given the four operations:

| Operation | Used by the platform? | Where |
|---|---|---|
| Create or replace | Yes | Bulk indexer (Phase 17), integration test fixtures |
| Read | Yes | Explain endpoint (Phase 16), tests |
| Update | No | The source of truth is the JSONL dataset; documents are replaced, not patched |
| Delete | Only in tests | Test fixtures clean up after themselves |

The platform's document lifecycle is therefore dominated by create-
or-replace. The bulk indexer is the only production writer. This keeps
the platform's write semantics simple: a document is either in the
index with a given source, or it is not.

## 4. Code Surface

Document operations are wrapped by the infrastructure layer under
`infrastructure.elasticsearch.documents` (introduced in Phase 5.2).
The domain and application layers do not call Elasticsearch directly.

