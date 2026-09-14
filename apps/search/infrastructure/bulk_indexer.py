"""
Bulk indexer for Elasticsearch.

Streams documents into Elasticsearch through the Bulk API in batches,
handles partial failures, retries transient errors with bounded
backoff, and reports the outcome as an IndexingResult.

See docs/22-indexing.md.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Iterator
from typing import Any

from elastic_transport import ConnectionError as TransportConnectionError

from apps.search.domain.indexing import IndexingFailure, IndexingResult
from apps.search.domain.product_document import ProductDocument
from elasticsearch import Elasticsearch, TransportError

logger = logging.getLogger(__name__)

# Default batch size. See docs/22-indexing.md section 3.1.
DEFAULT_BATCH_SIZE = 500

# Retry policy. See docs/22-indexing.md section 6.2.
MAX_ATTEMPTS = 3
INITIAL_BACKOFF_SECONDS = 0.5
BACKOFF_MULTIPLIER = 2.0

# HTTP statuses the platform treats as transient.
TRANSIENT_STATUSES = frozenset({429, 502, 503, 504})


class ElasticsearchBulkIndexer:
    """
    Adapter that writes documents to Elasticsearch through the Bulk API.

    Args:
        client: An Elasticsearch client.
        index: The index to write to.
        batch_size: Number of documents per bulk request. Defaults to
            500.
    """

    def __init__(
        self,
        client: Elasticsearch,
        index: str,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")
        self._client = client
        self._index = index
        self._batch_size = batch_size

    # --------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------
    def index_documents(self, documents: Iterable[dict[str, Any]]) -> IndexingResult:
        """
        Index documents, streaming them through batches.

        Each document must carry an ``id`` field. The value becomes the
        document `_id`, so re-indexing the same document is idempotent.

        Batching is by **document**, not by operation. Each document
        produces two bulk operations (an action line and a source line);
        batching by operation would split a pair across batches and
        produce a malformed request.
        """
        return self._run_bulk_operation(
            units=_iter_index_units(documents),
        )

    def index_products(self, documents: Iterable[ProductDocument]) -> IndexingResult:
        """
        Index ``ProductDocument`` instances.

        This method is a thin convenience over :meth:`index_documents`:
        the domain objects are converted to mappings via their
        ``to_mapping`` method, and the resulting stream is passed to the
        same batching path. Having both methods lets the indexer serve
        both a domain-aware caller (which has ProductDocument objects)
        and a domain-agnostic one (which has plain dicts).
        """
        return self.index_documents(doc.to_mapping() for doc in documents)

    def delete_documents(self, document_ids: Iterable[str]) -> IndexingResult:
        """
        Delete documents by id.

        Deleting a document that does not exist is reported as a success
        (Elasticsearch returns status 404 with `result: not_found`, which
        the platform treats as the desired end state).

        Each id produces one bulk operation, so batching by id and
        batching by operation are the same thing here.
        """
        return self._run_bulk_operation(
            units=_iter_delete_units(document_ids),
        )

    # --------------------------------------------------------------
    # Implementation
    # --------------------------------------------------------------
    def _run_bulk_operation(
        self,
        *,
        units: Iterator[list[dict[str, Any]]],
    ) -> IndexingResult:
        """
        Run a bulk operation over a stream of "units".

        A unit is one document's worth of operations: a list of one or
        two dicts (an action line, optionally followed by a source
        line). Batching groups units, then flattens them into a single
        operations list per request.
        """
        succeeded = 0
        failed = 0
        failures: list[IndexingFailure] = []

        for unit_batch in _batched(units, self._batch_size):
            operations: list[dict[str, Any]] = []
            for unit in unit_batch:
                operations.extend(unit)
            response = self._send_with_retry(operations)
            batch_result = _parse_bulk_response(response)
            succeeded += batch_result.succeeded
            failed += batch_result.failed
            failures.extend(batch_result.failures)

        return IndexingResult(
            succeeded=succeeded,
            failed=failed,
            failures=tuple(failures),
        )

    def _send_with_retry(self, batch: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Send one bulk request, retrying transient failures.

        The target index is passed as a parameter to the bulk call, not
        as part of each action line. Elasticsearch treats an ``index``
        URL parameter as applying to every operation in the request,
        which keeps the action lines minimal and avoids repeating the
        same index name for every document.

        Raises the final exception when all attempts are exhausted or
        the failure is not transient.
        """
        delay = INITIAL_BACKOFF_SECONDS
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self._client.bulk(index=self._index, operations=batch)
            except (TransportError, TransportConnectionError) as exc:
                if not _is_transient(exc):
                    raise
                if attempt == MAX_ATTEMPTS:
                    logger.error(
                        "bulk request failed after %d attempts: %s",
                        attempt,
                        exc,
                    )
                    raise
                logger.warning(
                    "transient bulk failure (attempt %d/%d): %s; retrying in %.1fs",
                    attempt,
                    MAX_ATTEMPTS,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay *= BACKOFF_MULTIPLIER

        # Unreachable: the loop either returns or raises.
        raise RuntimeError("bulk retry loop exited without returning or raising")


# ---------------------------------------------------------------------------
# Operation iterators
# ---------------------------------------------------------------------------
def _iter_index_units(
    documents: Iterable[dict[str, Any]],
) -> Iterator[list[dict[str, Any]]]:
    """
    Yield one unit per document.

    A unit is a list of one or two operations: an `index` action line
    and, for an index operation, the document source that follows it.
    Grouping them into a single unit means a batch can never split the
    pair.
    """
    for doc in documents:
        document_id = doc.get("id")
        if not document_id:
            raise ValueError("document is missing an 'id' field")
        yield [
            {"index": {"_id": str(document_id)}},
            doc,
        ]


def _iter_delete_units(
    document_ids: Iterable[str],
) -> Iterator[list[dict[str, Any]]]:
    """
    Yield one unit per document id.

    A delete unit is a single operation: a `delete` action line. The
    Bulk API does not expect a source line after a delete.
    """
    for document_id in document_ids:
        yield [{"delete": {"_id": str(document_id)}}]


def _batched(items: Iterator[Any], size: int) -> Iterator[list[Any]]:
    """Yield consecutive lists of at most ``size`` items."""
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------
def _parse_bulk_response(response: dict[str, Any]) -> IndexingResult:
    """
    Convert a Bulk API response into an IndexingResult.

    Each entry in ``items`` corresponds to one operation. An entry
    whose action value carries a `result` of `created`, `updated`, or
    `deleted`, or a status of 200 or 201, is a success. An entry that
    carries `error`, or a status of 404 for a delete, is treated as a
    failure -- except that a delete returning 404/not_found is
    explicitly considered a success, matching the idempotent semantics
    of the single-document delete.
    """
    items = response.get("items", [])
    succeeded = 0
    failures: list[IndexingFailure] = []

    for entry in items:
        action_name, action = _first_action(entry)
        if action_name is None:
            continue

        status = int(action.get("status", 0))
        document_id = str(action.get("_id", ""))
        error = action.get("error")

        if error is not None:
            failures.append(
                IndexingFailure(
                    document_id=document_id,
                    reason=_describe_error(error),
                    status=status,
                )
            )
            continue

        if action_name == "delete" and status == 404:
            # Idempotent delete: the document was already absent. This
            # is the desired end state, not a failure.
            succeeded += 1
            continue

        if 200 <= status < 300:
            succeeded += 1
            continue

        failures.append(
            IndexingFailure(
                document_id=document_id,
                reason=f"unexpected status {status}",
                status=status,
            )
        )

    return IndexingResult(
        succeeded=succeeded,
        failed=len(failures),
        failures=tuple(failures),
    )


def _first_action(entry: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """Return the (action name, action payload) of a bulk response item."""
    for name in ("index", "create", "update", "delete"):
        action = entry.get(name)
        if isinstance(action, dict):
            return name, action
    return None, {}


def _describe_error(error: Any) -> str:
    """Render the ``error`` field of a bulk item as a short string."""
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        reason = error.get("reason")
        if isinstance(reason, str):
            return reason
        error_type = error.get("type")
        if isinstance(error_type, str):
            return error_type
    return str(error)


def _is_transient(exc: Exception) -> bool:
    """
    Return True if the exception is a transient failure worth retrying.

    A TransportError carries an HTTP status when the server responded
    with an error code; the platform treats 429, 502, 503, and 504 as
    transient. A TransportConnectionError is a network-level failure
    and is always treated as transient.
    """
    if isinstance(exc, TransportConnectionError):
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in TRANSIENT_STATUSES
    return False


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "ElasticsearchBulkIndexer",
]
