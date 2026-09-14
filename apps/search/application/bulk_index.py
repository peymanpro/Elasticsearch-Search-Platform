"""
Use case: bulk-index a stream of product documents.

The use case is a thin coordination layer: it accepts a stream of
``ProductDocument`` instances, delegates to the domain's
``ProductIndexer`` port, and returns the resulting ``IndexingResult``.

The use case does not open files, does not parse JSONL, and does not
know the index name. Those decisions live in the caller or in the
composition root. Its only job is to be the named operation the API
layer calls.
"""

from __future__ import annotations

from collections.abc import Iterable

from apps.search.domain.indexing import IndexingResult
from apps.search.domain.product_document import ProductDocument
from apps.search.domain.strategies import ProductIndexer


class BulkIndexProductsUseCase:
    """Bulk-index a stream of product documents."""

    def __init__(self, indexer: ProductIndexer) -> None:
        self._indexer = indexer

    def execute(self, documents: Iterable[ProductDocument]) -> IndexingResult:
        """Index every document and return the aggregate result."""
        return self._indexer.index_products(documents)


__all__ = ["BulkIndexProductsUseCase"]
