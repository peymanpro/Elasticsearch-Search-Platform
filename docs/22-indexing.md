# Indexing Architecture

## 1. Purpose

This document specifies how the platform writes product documents
into Elasticsearch. It covers the roadmap sub-phases:

    * 17.1 -- Bulk indexing
    * 17.2 -- Batch processing
    * 17.3 -- Bulk response handling
    * 17.4 -- Partial failures
    * 17.5 -- Retry strategy
    * 17.6 -- Idempotent indexing
    * 17.7 -- Delete handling

The indexing layer is the bridge between the dataset on disk
(Phase 4) and the searchable index (Phases 5-6). It is the only
part of the platform that writes documents into Elasticsearch.

## 2. Why Bulk Indexing (17.1)

### 2.1 The single-document alternative

Every document could be written with a separate index request.
That is what `infrastructure.elasticsearch.documents.index_document`
does, and it is exactly the right tool for the cases it serves: a
test fixture, a health probe, a handful of ad-hoc writes.

It is the wrong tool for loading a catalog. A 100,000-document
dataset written one document per HTTP round trip is 100,000
requests. Even at 5 ms per request (which is optimistic on a local
machine), that is over eight minutes of pure network overhead, most
of it spent waiting for a reply that carries a one-line JSON
acknowledgement.

### 2.2 The bulk alternative

The Bulk API accepts an array of operations and returns an array of
responses. One HTTP request carries up to N operations. The
recommendation from Elasticsearch's own documentation is to target
a few thousand operations per request, tuned to the document size
and the cluster's capacity.

The speedup is not merely the network cost. Bulk operations on the
server side are processed with shared overhead: one Lucene
checkpoint, one shard-level write lock, one flush when the request
completes. A batch is dramatically cheaper per document than the
same number of individual writes.

## 3. Batch Processing (17.2)

### 3.1 The batch

The platform uses a fixed default batch size of 500 documents.
That is a deliberate middle-of-the-road choice:

* Under 100: the HTTP overhead starts to dominate again.
* Over 1000: a single failing batch takes longer to retry, and the
  memory footprint of holding the batch on the client grows.
* 500 is what a laptop-class Elasticsearch node handles comfortably
  in one request without hitting the thread pool queue limits.

The batch size is exposed as a parameter on the indexer. The
default is the platform's opinion; the parameter is the caller's
override.

### 3.2 Streaming, not loading

The bulk indexer accepts an iterable of documents, not a list. A
caller that reads a JSONL file streams documents from disk; the
indexer batches them as it goes and never holds the full dataset
in memory. A caller that already has a list passes the list; the
indexer still batches it.

This is the difference between indexing 100,000 documents in 500-
document slices and trying to build one 100,000-item list.

## 4. Bulk Response Handling (17.3)

### 4.1 The response shape

The Bulk API returns, for each operation, an entry in an `items`
array. Each entry is a dictionary with one key (the operation
type: `index`, `create`, `update`, or `delete`) whose value carries
the HTTP-level status, an `_id`, and either a `result` or an
`error`.

    {
      "took": 12,
      "errors": false,
      "items": [
        {"index": {"_index": "products-v2", "_id": "SKU-0001", "status": 201, "result": "created"}},
        {"index": {"_index": "products-v2", "_id": "SKU-0002", "status": 201, "result": "created"}},
        ...
      ]
    }

The top-level `errors` boolean is a coarse indicator: it is True
if any item failed. The per-item status is the source of truth.
The platform relies on the per-item entries, not the flag.

### 4.2 The result the platform produces

The indexer returns an `IndexingResult` value object with three
fields:

    succeeded: int          how many items were written successfully
    failed: int             how many items failed
    failures: tuple[...]    one entry per failed item, in input order

A failed entry carries the document id, the failure reason, and
the HTTP status. It does not carry the document source: a caller
that needs to retry a failure already has access to the input.

## 5. Partial Failures (17.4)

### 5.1 What "partial failure" means

A bulk request can succeed at the HTTP level (200 OK) while
individual items within it fail. This is the normal case, not an
error case: a batch of 500 documents is processed item by item,
and one item with an invalid field value does not stop the other
499.

Elasticsearch signals the mixed outcome with `errors: true` in the
response. The platform treats the per-item entries as the source
of truth and does not use the flag.

### 5.2 Common failure categories

The items that fail fall into three categories:

1. **Mapping violations.** A field has the wrong type, or the
   document has an unknown top-level field (which `dynamic: strict`
   rejects). These are permanent: retrying them fails again.
2. **Document-level constraints.** A field value violates an
   analyzer's constraint, or a term is too long for a `keyword`
   field's `ignore_above`. Also permanent.
3. **Transient cluster conditions.** A shard is temporarily
   unavailable, a node is restarting, a bulk queue is full. These
   may succeed on retry.

The platform does not distinguish these categories automatically.
It reports every failure; the caller decides whether to retry the
whole batch, the failed items only, or nothing.

### 5.3 What the platform does with failures

Every failure is recorded in the `IndexingResult`. The batch is
not aborted; the next batch is processed. A caller that wants
fail-fast behavior checks the result and stops.

The platform does not retry within the indexer. Retry is a
separate concern with its own policy (Section 6), and mixing it
into the bulk loop would obscure what succeeded on first attempt
versus what succeeded after retries.

## 6. Retry Strategy (17.5)

### 6.1 What the platform retries

The platform retries the entire batch when the bulk request itself
fails with a **transient** error. Transient errors include:

* Network timeouts against the cluster.
* HTTP 503 (Service Unavailable) responses.
* `es_rejected_execution_exception` (the bulk thread pool is full).

The platform does not retry when the request fails with a
**permanent** error:

* HTTP 400 (Bad Request) -- the batch is malformed.
* HTTP 401 / 403 -- authentication or authorization.
* HTTP 404 -- the index does not exist.

An HTTP-level failure that is not transient is reported as the
failure of the whole batch. The caller decides how to respond.

### 6.2 The retry policy

The retry policy is bounded:

    max_attempts: 3       (initial attempt plus two retries)
    backoff: exponential  (0.5s, 1.0s, 2.0s)

The delay is exponential with a small base. This is the standard
pattern for contending with a temporarily overloaded server: the
first retry is cheap, and each subsequent retry gives the server
more time to recover.

The policy is deliberately not configurable at Phase 17. If the
platform ever needs different values, that is a change with its
own rationale.

### 6.3 What retry does not cover

The platform does not retry individual failed items within a
successful batch. If one document failed because of a mapping
violation, retrying it produces the same failure. If a document
failed because of a transient condition, the whole batch is far
more likely to have hit the same condition and been retried as a
unit.

Item-level retry is a policy a caller can implement on top of the
`IndexingResult`: take the failures, build a new batch, run the
indexer again. The platform exposes the information; the caller
composes the strategy.

## 7. Idempotent Indexing (17.6)

### 7.1 The mechanism

Every document is indexed under a deterministic id. For products,
that id is the SKU (see docs/09 section 3.4). The Bulk API
operation used is `index`, which creates a document if the id is
new and replaces it if the id exists.

Consequence: ingesting the same dataset twice produces the same
final index state as ingesting it once. No duplicates, no stale
data, no error.

### 7.2 Why idempotency matters

A bulk load can fail partway through for reasons that have nothing
to do with the data: a network drop, a container restart, a
developer interrupting the command. Without idempotency, the
correct response is to delete the index and start over, because
the index is now in an unknown partial state.

With idempotency, the correct response is to re-run the load.
Documents that were already written are overwritten with the
same values; documents that were not are written for the first
time. The final state is correct.

### 7.3 What idempotency does not cover

Idempotent loading replaces documents with the same id. It does
not delete documents whose id is no longer present in the source.
A product removed from the dataset stays in the index until it
is explicitly deleted (Section 8) or until the whole index is
rebuilt from scratch.

This is a deliberate choice. Automatically pruning unknown ids
would require reading the index and diffing against the source
on every load, which does not scale. The platform's policy is:
the dataset is the source of truth, and rebuilding the index from
the dataset is the mechanism that keeps them aligned. Phase 18
formalizes this as the reindex workflow.

## 8. Delete Handling (17.7)

### 8.1 Bulk delete

Deletion is a first-class operation in the Bulk API: a `delete`
action carries only the index name and the document id. The
platform exposes bulk delete alongside bulk index so that a
caller can remove a set of documents in one request.

A bulk delete reports the same shape of result as a bulk index:
a count of successes, a count of failures, and per-item entries
for failures. A delete of a document that does not exist is not
a failure -- Elasticsearch reports `result: not_found` with a
status of 404, and the platform treats it as a success, matching
the single-document delete's idempotent semantics.

### 8.2 What bulk delete is for

Bulk delete is not the mechanism for keeping the index aligned
with the dataset (Section 7.3). It is a targeted tool: remove
a specific list of documents by id, for example a curated list
of discontinued SKUs. It is not used during routine loading.

### 8.3 Bulk update

The Bulk API also supports a partial `update` action. The platform
does not expose it. The dataset is regenerated rather than
edited; a document that changes is written in full. Bulk update
would be an optimization for a workload the platform does not
have.

## 9. Testing

The tests verify:

1. **Successful bulk.** A batch of 100+ fixture documents is
   indexed; the result reports all of them succeeded; the index
   contains the expected count.
2. **Idempotency.** The same batch is indexed twice; the index
   still contains the same count, and the documents carry the
   same values.
3. **Partial failure.** A batch containing one document that
   violates the mapping and several that do not is indexed; the
   result reports the exact counts and the failed item carries
   the document id and a reason.
4. **Bulk delete.** A batch of deletes removes the expected
   documents and reports them as successes; a delete of a
   non-existent id is reported as a success, not a failure.

## 10. Rule for Changing Indexing

A change to the batch size, the retry policy, the idempotency
mechanism, or the shape of `IndexingResult` is a change to this
document and to the code, in the same commit. The rule mirrors
the other design documents in this project.

