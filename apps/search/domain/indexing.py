"""
Indexing result value objects.

The bulk indexer produces an IndexingResult: a report of how many
documents were written, how many failed, and the details of each
failure. The result is a value object rather than a dict so that
callers can rely on field names and types, and so that the counting
logic (succeeded + failed = total) lives in one place.

See docs/22-indexing.md sections 4-8.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class IndexingFailure:
    """
    A single failed operation within a bulk request.

    Attributes:
        document_id: The identifier of the document that failed.
        reason: A human-readable description of why it failed. The
            string comes from Elasticsearch; the platform does not
            interpret it.
        status: The HTTP-equivalent status code Elasticsearch reported
            for this item (e.g. 400, 409, 429).
    """

    document_id: str
    reason: str
    status: int


@dataclass(frozen=True, slots=True)
class IndexingResult:
    """
    The outcome of a bulk indexing or delete operation.

    Attributes:
        succeeded: Number of documents written or deleted successfully.
        failed: Number of documents that failed.
        failures: One entry per failed document, in the order they
            appeared in the input. The tuple is empty when ``failed``
            is zero.

    Invariants:
        succeeded + failed == number of documents submitted
        len(failures) == failed
    """

    succeeded: int
    failed: int
    failures: tuple[IndexingFailure, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        """Total number of operations submitted."""
        return self.succeeded + self.failed

    @property
    def is_fully_successful(self) -> bool:
        """True if no operation failed."""
        return self.failed == 0


__all__ = [
    "IndexingFailure",
    "IndexingResult",
]
