# Reindexing ? Consolidated Reference

## 1. Purpose

This document is the consolidated reference for how the platform
evolves its index safely. It supersedes `docs/22-indexing.md` and
`docs/23-index-lifecycle.md` as the operational summary and references
both for full detail.

It covers Phase 25.5 of the master roadmap.

## 2. When a Reindex Is Required

An Elasticsearch mapping is immutable after an index has documents.
A reindex is required when any of the following change:

* **A new field is added** ? e.g. `name_suggest` in `v2`.
* **An existing field's type changes** ? a `text` field becoming a
  `keyword`.
* **An analyzer changes** ? the tokens in the inverted index are
  derived from the analyzer; changing it requires re-deriving them.
* **An alias needs to be repointed at a new physical index.**

A change to document content does not require a reindex; existing
documents can be updated in place. The platform's write model is
that documents are replaced by re-running the bulk loader with the
same `_id` (the SKU). See `docs/22-indexing.md` section 7.

## 3. The Reindex Workflow

The `ReindexService` orchestrates the workflow. It runs in six steps:

1. **Determine the target version.** Compute the next version number
   from the current one (`v2` -> `v3`).
2. **Create the new physical index.** Read its settings and mapping
   from the version's JSON files, and issue `indices.create`.
3. **Bulk-index the dataset.** Stream the JSONL through the bulk
   indexer.
4. **Validate.** Compare the document count in the new index to the
   number of documents that were successfully indexed. If they
   differ, or if zero documents were indexed, stop and report.
5. **Switch the alias.** Atomically remove the alias from the old
   index and add it to the new one.
6. **Leave the old index in place.** It remains available for
   rollback until a human decides it is no longer needed.

Steps 1?4 happen entirely before the alias switch. A failure in any of
those steps leaves the platform serving queries from the existing
index, unchanged. Step 5 is the only moment when the live index
changes.

## 4. The Alias Switch

The switch is one HTTP request to Elasticsearch's `_aliases` endpoint:

    {
      "actions": [
        {"remove": {"index": "products-v2", "alias": "products"}},
        {"add":    {"index": "products-v3", "alias": "products"}}
      ]
    }

Elasticsearch guarantees the request is atomic. There is no moment
when the alias points at neither index, and no moment when it points
at both. Queries issued before the switch completes finish against
`v2`; queries issued after complete against `v3`.

This atomicity is what makes the switch zero-downtime.

## 5. Rollback

Rollback is the same request, in reverse:

    {
      "actions": [
        {"remove": {"index": "products-v3", "alias": "products"}},
        {"add":    {"index": "products-v2", "alias": "products"}}
      ]
    }

Because the old index was not deleted, it is still present with its
original documents. The alias points at it again and the platform
serves queries from it exactly as before.

The cost of rollback is the loss of any writes made to the new index
between the switch and the rollback. The platform is a read-mostly
system: writes happen during indexing, not during normal operation.
So this cost is negligible.

## 6. Validation

Two checks happen before the switch. Both must pass; a single failure
aborts the reindex.

1. **At least one document was indexed.** A reindex that reaches the
   switch step with zero documents is almost certainly a caller
   mistake: an empty source file, an already-consumed iterable, or a
   filter that removed everything.
2. **Document count matches.** The count reported by Elasticsearch
   in the new index must equal the number of successful index
   operations reported by the indexer. A mismatch (very rare)
   indicates that some accepted writes never became visible.

Neither check is a full test of the new index's behavior. Both are
cheap, fast, and catch the common failure modes.

## 7. The Commands

Two management commands implement the workflow:

    # Rebuild the index to a new version and switch the alias.
    python manage.py reindex --version v3

    # Report the current alias target and physical index list.
    python manage.py reindex_status

Neither command is exposed over HTTP. The HTTP surface is read-only.
The reasoning: a reindex is measured in minutes and consumes
significant cluster resources, and the platform has no authentication
to gate a destructive operation. See `docs/24-search-api.md` section 8.

## 8. What the Platform Does Not Do

* **It does not reindex from the old index.** The source of truth is
  the JSONL dataset, not the live index. Elasticsearch's own
  `_reindex` API would copy documents from one index to another
  server-side; the platform does not use it, because the platform
  already treats the dataset as the authority for what the catalog
  contains.
* **It does not run the reindex concurrently with writes.** The
  design assumes the dataset is fixed between the start and end of a
  reindex. A production system with a streaming ingestion path would
  need a different design (dual-write or change-data capture).
* **It does not delete old indices.** The lifecycle service never
  deletes an index. Deletion is a separate, manual operation.
* **It does not measure reindex duration in the benchmark harness.**
  Functional tests exist (`tests/integration/test_reindex.py`); a
  timing measurement is deferred.

## 9. Verification

* `tests/integration/test_reindex.py` ? creates two versions, runs a
  full reindex, verifies the alias switch, verifies rollback, and
  verifies that a validation failure does not switch the alias.
* `tests/unit/test_bulk_indexer.py` ? the bulk indexer that the
  reindex workflow uses is tested independently of the workflow.

## 10. Related Documents

* `docs/22-indexing.md` ? bulk indexing, batching, partial-failure
  handling, and retry.
* `docs/23-index-lifecycle.md` ? the full lifecycle design.
* `docs/31-index-design.md` ? the fields that a reindex will produce.
