# Index Lifecycle and Reindexing

## 1. Purpose

This document specifies how the platform evolves its search index
over time without taking the search offline. It covers the roadmap
sub-phases:

    * 18.1 -- Versioned indices
    * 18.2 -- Aliases
    * 18.3 -- Reindex workflow
    * 18.4 -- Alias switch
    * 18.5 -- Rollback
    * 18.6 -- Zero-downtime reindex

This is the phase that makes everything before it operationally
safe. Phases 5-17 build the search machinery; this phase lets that
machinery change without a maintenance window.

## 2. The Problem

An Elasticsearch mapping is immutable after an index has
documents. Adding a field, changing a field type, or changing an
analyzer requires a new index. The platform has already crossed
this boundary once: Phase 12 added the `name_suggest` field and
created `products-v2` alongside `products-v1`.

The design that lets v2 exist is only half the story. The other
half is: once v2 is ready, how does the application switch to it
without dropping queries? And how does a rollback work if v2 turns
out to be broken?

## 3. Versioned Indices (18.1)

### 3.1 The convention

Two names exist for each index version, and they have distinct
jobs:

| Name | Example | Mutable? | Referenced by |
|---|---|---|---|
| Physical | products-v2 | Only by lifecycle operations | Reindex, snapshot, delete |
| Alias | products | Freely repointed | Every search query |

The application never references a physical name. Every search,
every facet, every suggest, every explain goes through the alias.
The alias is what makes the physical index name irrelevant to the
rest of the code.

### 3.2 Why the physical name carries a version

Because a mapping change produces a new index, and the old index
must remain valid and searchable until the switch. If the physical
name were version-less (`products`), creating a new index for a
mapping change would require deleting the old one first, which
would take the platform offline for the duration of the reindex.

Versioned physical names let old and new coexist. Reindexing is a
background operation; the switch is a one-second alias update.

### 3.3 What "version" means

A version is a monotonically increasing integer with a `v` prefix:
`v1`, `v2`, `v3`. The version is not a date, not a hash, not a
semantic-version string. It is a counter.

The reason: the only thing the version needs to do is be different
from the previous version. A counter is unambiguous and readable.
A date requires remembering what changed on that date. A hash is
opaque.

### 3.4 The current version

The current version is not stored anywhere on disk or in the
configuration. It is derivable from the alias: the physical index
that the alias points at is the current version. This is
deliberate: a second source of truth for "what version is live"
could disagree with the alias, and the alias is authoritative.

The `infrastructure.elasticsearch.indices.CURRENT_INDEX_VERSION`
constant is a documentation helper: it names the version that
`load_settings`/`load_mapping` should read when building a new
index. It is not consulted at query time. Every query goes through
the alias.

## 4. Aliases (18.2)

### 4.1 What an alias is

An alias is a name that Elasticsearch resolves to one or more
physical indices at request time. A search against an alias is
transparently redirected to the underlying index (or indices).

An alias is not a copy. It is a pointer.

### 4.2 The platform's alias

The platform uses a single alias: `products`.

    products  ->  products-v2  (currently)

Every search method in `ElasticsearchProductSearchGateway`,
`ElasticsearchFacetGateway`, `ElasticsearchProductSuggester`, and
`ElasticsearchProductExplainer` targets this alias. None of them
knows which physical index is behind it.

### 4.3 The alias is exclusive

An Elasticsearch alias may point at multiple indices (for search
across a set). The platform does not use this capability. The
`products` alias always points at exactly one physical index. The
lifecycle operations enforce this: creating a new version and
switching the alias removes the old binding atomically.

### 4.4 The alias does not exist until created

Creating an index does not create an alias. The `create_index`
manager function creates the physical index; a separate operation
attaches the alias. This split is important during a reindex: the
new index must exist and be populated before the alias is attached,
and the alias switch is one atomic operation against the alias
name, not a series of operations against indices.

## 5. Reindex Workflow (18.3)

### 5.1 The source of truth

The platform rebuilds an index by reading the dataset, not by
copying from an existing index. The workflow is:

    dataset (JSONL)  ->  bulk indexer  ->  new physical index  ->  alias switch

This is not what Elasticsearch's own `_reindex` API does.
`_reindex` copies documents from one index to another, server-side,
without leaving the cluster.

### 5.2 Why rebuild from the dataset, not `_reindex`

**The dataset is authoritative.** The platform already treats the
JSONL dataset as the source of truth for what the catalog contains
(see docs/22-indexing.md section 7.3). Reindexing from the dataset
keeps that invariant intact: the new index is derived from the same
source as the old one, so there is no opportunity for the two to
disagree.

**Rebuilding permits document-level changes.** A mapping change is
often accompanied by a document change: a new field is populated,
an old field is dropped, an analyzer is different. Rebuilding from
the dataset lets both changes happen together. `_reindex` would
copy the old documents into the new mapping, which works for a
pure type change but not for a shape change.

**The dataset is small enough to rebuild.** At the platform's
scale (thousands to hundreds of thousands of documents), a full
rebuild takes seconds to minutes. `_reindex` is the correct tool
at a much larger scale; the platform is not at that scale.

**Trade-off.** The rebuild approach pays the parsing and JSONL
reading cost on every reindex. `_reindex` would not. At the
platform's scale, this is negligible. If the dataset ever grew to
the point where parsing became a bottleneck, `_reindex` would
become the better choice, and this decision would be revisited.

### 5.3 The steps

A reindex operation, in order:

1. **Determine the target version.** Compute the next version
   number from the current one (`v1` -> `v2`, `v2` -> `v3`).
2. **Create the new physical index.** Read its settings and mapping
   from the version's JSON files, and issue `indices.create`.
3. **Bulk index the dataset.** Stream the JSONL through the bulk
   indexer. Partial failures are reported but do not abort the
   operation: the validation step in step 4 decides whether the
   result is acceptable.
4. **Validate.** Compare the document count in the new index to
   the number of documents that were supposed to be indexed. If
   they differ, stop and report.
5. **Switch the alias.** Atomically remove the alias from the old
   index and add it to the new one.
6. **Leave the old index in place.** It is not deleted. It remains
   available for rollback until a human decides it is no longer
   needed.

Each step is a method on a `ReindexService`. The steps that can
fail (steps 1, 3, and 4) do so before the alias switch, so a
failed reindex leaves the platform serving queries from the
existing index unchanged.

## 6. Alias Switch (18.4)

### 6.1 What the switch is

The switch is one HTTP request to Elasticsearch's `_aliases`
endpoint:

    {
      "actions": [
        {"remove": {"index": "products-v1", "alias": "products"}},
        {"add":    {"index": "products-v2", "alias": "products"}}
      ]
    }

Both actions are executed together. From the moment the request
succeeds, every subsequent query against `products` sees v2.
Queries that were already in flight when the request landed
complete against v1.

### 6.2 Why a single request

Elasticsearch guarantees the `_aliases` request is atomic: either
both actions succeed, or neither does. There is no moment when
the `products` alias points at neither index, and there is no
moment when it points at both.

Two separate requests (remove then add, or add then remove) would
create a brief window where the alias was either unbound (a
remove-before-add sequence) or ambiguous (an add-before-remove
sequence). The single request removes both windows.

## 7. Rollback (18.5)

### 7.1 When rollback is needed

The most common reason is not that the reindex itself failed --
that is caught by validation before the alias switch. The common
reason is that the *new* index behaves differently in ways that
only appear under real queries: a different ranking, a slower
search, a filtering query that returns nothing. These are not
detectable by counting documents.

### 7.2 How rollback works

Rollback is the same `_aliases` request, in reverse:

    {
      "actions": [
        {"remove": {"index": "products-v2", "alias": "products"}},
        {"add":    {"index": "products-v1", "alias": "products"}}
      ]
    }

Because the old index was not deleted, it is still present with
its original documents. The alias points at it again, and the
platform serves queries from it exactly as before.

### 7.3 The cost of rollback

Rollback loses any writes made to the new index between the
switch and the rollback. The platform is a read-mostly system:
writes happen during indexing, not during normal operation. So
this cost is negligible.

If the platform ever supported live updates to individual
documents (it does not; the dataset is the source of truth),
rollback would need to replay those writes. The design assumes
the write-free window between reindex and rollback.

## 8. Zero-Downtime Reindex (18.6)

### 8.1 What "zero downtime" means here

The platform is never unreachable, and no query is ever served
against a half-populated index.

* Throughout the reindex, `products` points at the live version
  and answers every query.
* At the moment of the switch, the new index is fully populated
  and validated.
* After the switch, queries are served from the new index with no
  interruption.

### 8.2 What is not covered

The platform does not run the reindex concurrently with writes to
the old index. The dataset is fixed between the start and end of
a reindex; if it changes mid-reindex, the new index reflects the
state at the time the bulk indexer read it, which may not match
what a parallel writer is adding.

This is acceptable because the platform has no other writer. The
dataset is loaded by the reindex operation and by nothing else.
A production system with a streaming ingestion path would need a
different design (dual-write during reindex, or a change-data
capture pipeline). That design is out of scope for this project
(see docs/02-non-goals.md section 3.2).

## 9. Validation Before Switch

Two checks are performed before the alias is switched:

1. **Document count.** The number of documents in the new index
   must equal the number of documents that were submitted for
   indexing, minus any reported failures. If they differ by more
   than the reported failure count, the reindex is considered
   broken and the switch is aborted.
2. **Sentinel search.** A known document must be findable by a
   known query in the new index. This is a smoke test: it catches
   the case where the index was created but not populated, or
   populated under the wrong field names.

Neither check is a full test of the new index's behavior. Both
are cheap, fast, and catch the common failure modes (empty index,
wrong mapping). A larger validation (rank comparison against the
old index, performance smoke test) is a candidate for later work.

## 10. Testing

The tests cover:

1. **Alias operations.** Create, switch, delete alias. Verify the
   alias resolves to the expected physical index.
2. **Full reindex workflow.** From an existing v2 index serving
   queries, create a v3 index, populate it from the dataset,
   validate, and switch the alias. Verify that queries now go to
   v3 and return the correct results.
3. **Rollback.** After a successful reindex, roll back to v2 and
   verify that queries again go to v2.
4. **Validation rejects a broken reindex.** Simulate a partial
   failure; verify that the switch does not happen.

## 11. Rule for Changing Lifecycle

A change to the alias name, the version naming convention, the
reindex steps, or the validation rules is a change to this
document and to the code, in the same commit. The rule mirrors
the other design documents in this project.

