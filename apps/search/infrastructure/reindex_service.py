"""
Index lifecycle service: reindex and rollback.

The ReindexService orchestrates the full reindex workflow described in
docs/23-index-lifecycle.md:

    1. Determine the next version
    2. Create a new physical index for that version
    3. Bulk-index the dataset into the new index
    4. Validate the result
    5. Switch the alias
    6. Return a report

The service is in the infrastructure layer because it directly
orchestrates Elasticsearch lifecycle operations: creating indices,
attaching aliases, checking document counts. The application layer
would wrap it if it needed to expose the workflow over HTTP; the
composition is not needed today.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from apps.search.domain.product_document import ProductDocument
from elasticsearch import Elasticsearch
from infrastructure.elasticsearch.indices import INDEX_ALIAS
from infrastructure.elasticsearch.indices.manager import (
    attach_alias,
    create_index,
    get_alias_target,
    physical_index_name,
    refresh_index,
    switch_alias,
)

logger = logging.getLogger(__name__)


class ReindexError(Exception):
    """Raised when a reindex operation cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class ReindexReport:
    """
    Outcome of a reindex operation.

    Attributes:
        previous_version: The version the alias pointed at before the
            operation. None if there was no alias yet (initial setup).
        new_version: The version that is now live.
        previous_index: The physical index name before the operation.
            None if there was no alias yet.
        new_index: The physical index name that is now live.
        documents_indexed: How many documents the new index holds.
        documents_failed: How many documents failed during indexing.
            A nonzero value here prevents the switch; the operation
            returns a report describing the failure rather than
            raising, so the caller can inspect it.
        validation_notes: Human-readable notes about the validation
            step's outcome.
    """

    previous_version: str | None
    new_version: str
    previous_index: str | None
    new_index: str
    documents_indexed: int
    documents_failed: int
    validation_notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def switched(self) -> bool:
        """True if the alias was actually moved to the new index."""
        return self.previous_index != self.new_index


class ReindexService:
    """
    Orchestrator for the reindex workflow.

    Args:
        client: An Elasticsearch client. Injected so that tests can
            supply a fake.
        indexer: An object with an ``index_products`` method returning
            an ``IndexingResult``. The service uses it to populate the
            new index.
    """

    def __init__(self, client: Elasticsearch, indexer: object) -> None:
        self._client = client
        self._indexer = indexer

    def reindex(
        self,
        new_version: str,
        documents: Iterable[ProductDocument],
    ) -> ReindexReport:
        """
        Run the full reindex workflow to ``new_version``.

        The documents iterable is consumed exactly once. Callers that
        need to retry should re-read the source.

        Raises:
            ReindexError: the new index could not be created, or
                validation failed. In both cases the alias has not
                been touched and the platform continues to serve from
                the previous index.
        """
        # 1) Record the current state.
        previous_index = get_alias_target(INDEX_ALIAS)
        previous_version = _version_from_index(previous_index) if previous_index else None

        new_index = physical_index_name(new_version)
        if new_index == previous_index:
            raise ReindexError(
                f"new version {new_version!r} resolves to the same "
                f"physical index as the current one ({previous_index!r})"
            )

        # 2) Create the new physical index.
        logger.info("reindex: creating %s", new_index)
        create_index(new_version, ignore_existing=False)

        # 3) Bulk-index the dataset.
        logger.info("reindex: bulk-indexing into %s", new_index)
        result = self._indexer.index_products(documents)  # type: ignore[attr-defined]
        refresh_index(new_index)

        # 4) Validate.
        notes = self._validate(
            new_index=new_index,
            indexed=result.succeeded,
            failed=result.failed,
        )
        if notes:
            # Validation failed. Leave the alias alone and report.
            raise ReindexError("reindex validation failed: " + "; ".join(notes))

        # 5) Switch the alias.
        if previous_index is None:
            # First-ever reindex: no alias exists yet. Attach it.
            logger.info("reindex: attaching alias %s to %s", INDEX_ALIAS, new_index)
            attach_alias(new_version, alias=INDEX_ALIAS)
        else:
            logger.info(
                "reindex: switching alias %s from %s to %s",
                INDEX_ALIAS,
                previous_index,
                new_index,
            )
            switch_alias(new_version, alias=INDEX_ALIAS)

        return ReindexReport(
            previous_version=previous_version,
            new_version=new_version,
            previous_index=previous_index,
            new_index=new_index,
            documents_indexed=result.succeeded,
            documents_failed=result.failed,
            validation_notes=(),
        )

    def rollback(self, previous_version: str) -> None:
        """
        Point the alias back at a previous physical index.

        The previous index is expected to still exist. This service
        never deletes indices; deletion is a separate, manual
        operation.
        """
        switch_alias(previous_version, alias=INDEX_ALIAS)

    # --------------------------------------------------------------
    # Validation
    # --------------------------------------------------------------
    def _validate(
        self,
        *,
        new_index: str,
        indexed: int,
        failed: int,
    ) -> tuple[str, ...]:
        """
        Return a tuple of validation failure notes.

        An empty tuple means validation passed. A non-empty tuple
        means the reindex is considered unsafe to switch.

        Three checks:

        * At least one document was indexed. A reindex that reaches
          the switch step with zero documents is almost certainly a
          caller mistake: an empty source file, an already-consumed
          iterable, or a filter that removed everything. Failing
          closed is the safe default.
        * No documents failed during indexing.
        * The count reported by Elasticsearch matches the number of
          successful index operations. This catches a class of failure
          the second check does not see: writes that Elasticsearch
          accepted at the API level but that never became visible (a
          very rare condition, but one that would leave the new index
          incomplete).
        """
        notes: list[str] = []

        if indexed == 0:
            notes.append("no documents were indexed")

        if failed > 0:
            notes.append(f"{failed} documents failed during indexing")

        try:
            self._client.indices.refresh(index=new_index)
            count_response = self._client.count(index=new_index)
            actual_count = int(count_response["count"])
        except Exception as exc:  # noqa: BLE001 - any failure here invalidates the reindex
            notes.append(f"could not count documents in {new_index}: {exc}")
            return tuple(notes)

        if actual_count != indexed:
            notes.append(f"index {new_index} contains {actual_count} documents; expected {indexed}")

        return tuple(notes)


def _version_from_index(index_name: str | None) -> str | None:
    """
    Extract the version from a physical index name (``products-v2``
    -> ``v2``). Returns None for names that do not follow the
    convention.
    """
    if index_name is None:
        return None
    prefix = "products-"
    if not index_name.startswith(prefix):
        return None
    return index_name[len(prefix) :]


__all__ = [
    "ReindexError",
    "ReindexReport",
    "ReindexService",
]
