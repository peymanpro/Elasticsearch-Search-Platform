"""
Integration tests for the bulk indexer.

These tests exercise the bulk indexer against a real Elasticsearch
cluster: they create a temporary index, load documents, verify the
results, exercise idempotency, and exercise partial failures.

The tests skip cleanly when no cluster is reachable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.search.application.bulk_index import BulkIndexProductsUseCase
from apps.search.domain.indexing import IndexingResult
from apps.search.domain.product_document import ProductDocument
from apps.search.infrastructure.bulk_indexer import ElasticsearchBulkIndexer
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import load_mapping, load_settings

pytestmark = pytest.mark.integration

TEST_INDEX = "products-bulk-test"
REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET = REPO_ROOT / "data" / "products.jsonl"


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def bulk_index() -> str:
    client = get_client()
    client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)

    settings = load_settings("v2")
    mapping = load_mapping("v2")
    client.indices.create(
        index=TEST_INDEX,
        settings=settings,
        mappings={"dynamic": mapping["dynamic"], "properties": mapping["properties"]},
    )

    try:
        yield TEST_INDEX
    finally:
        client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


@pytest.fixture()
def empty_index(bulk_index: str) -> str:
    """Clear the index between tests that need a fresh start."""
    client = get_client()
    client.delete_by_query(
        index=bulk_index,
        body={"query": {"match_all": {}}},
        refresh=True,
        conflicts="proceed",
    )
    return bulk_index


def _load_dataset() -> list[ProductDocument]:
    docs: list[ProductDocument] = []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        if line.strip():
            docs.append(ProductDocument.from_mapping(json.loads(line)))
    return docs


def _count(index: str) -> int:
    get_client().indices.refresh(index=index)
    result = get_client().count(index=index)
    return int(result["count"])


# ---------------------------------------------------------------------------
# Indexing real documents
# ---------------------------------------------------------------------------
def test_indexes_the_real_dataset(empty_index: str) -> None:
    docs = _load_dataset()
    indexer = ElasticsearchBulkIndexer(client=get_client(), index=empty_index, batch_size=5)
    result = indexer.index_products(docs)

    assert isinstance(result, IndexingResult)
    assert result.failed == 0, f"unexpected failures: {result.failures}"
    assert result.succeeded == len(docs)
    assert _count(empty_index) == len(docs)


def test_indexing_larger_than_a_batch(empty_index: str) -> None:
    # Load the dataset, then duplicate the ids under new SKUs so we
    # exercise more than one batch. We rebuild the docs with a suffix.
    base_docs = _load_dataset()
    expanded: list[ProductDocument] = []
    for copy in range(3):
        for doc in base_docs:
            new_id = f"{doc.id}-copy{copy}"
            expanded.append(
                ProductDocument(
                    id=new_id,
                    sku=new_id,
                    name=doc.name,
                    brand=doc.brand,
                    category=doc.category,
                    description=doc.description,
                    tags=doc.tags,
                    specifications=doc.specifications,
                    language=doc.language,
                    price=doc.price,
                    currency=doc.currency,
                    rating=doc.rating,
                    availability=doc.availability,
                    created_at=doc.created_at,
                    popularity=doc.popularity,
                )
            )

    indexer = ElasticsearchBulkIndexer(client=get_client(), index=empty_index, batch_size=5)
    result = indexer.index_products(expanded)

    assert result.failed == 0
    assert result.succeeded == len(expanded)
    assert _count(empty_index) == len(expanded)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def test_indexing_twice_leaves_the_same_count(empty_index: str) -> None:
    docs = _load_dataset()
    indexer = ElasticsearchBulkIndexer(client=get_client(), index=empty_index, batch_size=5)

    first = indexer.index_products(docs)
    assert first.failed == 0
    first_count = _count(empty_index)

    second = indexer.index_products(docs)
    assert second.failed == 0
    second_count = _count(empty_index)

    assert first_count == second_count
    assert first_count == len(docs)


def test_reindexing_replaces_values(empty_index: str) -> None:
    docs = _load_dataset()
    indexer = ElasticsearchBulkIndexer(client=get_client(), index=empty_index, batch_size=5)
    indexer.index_products(docs)

    # Rebuild the first document with a changed price.
    original = docs[0]
    changed = ProductDocument(
        id=original.id,
        sku=original.sku,
        name=original.name,
        brand=original.brand,
        category=original.category,
        description=original.description,
        tags=original.tags,
        specifications=original.specifications,
        language=original.language,
        price=original.price + 100,
        currency=original.currency,
        rating=original.rating,
        availability=original.availability,
        created_at=original.created_at,
        popularity=original.popularity,
    )
    indexer.index_products([changed])

    get_client().indices.refresh(index=empty_index)
    stored = get_client().get(index=empty_index, id=original.id)
    assert stored["_source"]["price"] == float(original.price + 100)


# ---------------------------------------------------------------------------
# Partial failures
# ---------------------------------------------------------------------------
def test_partial_failure_reports_the_bad_document(empty_index: str) -> None:
    docs = _load_dataset()[:3]
    # Inject a document whose source contains an unknown top-level field.
    # dynamic: strict on the mapping rejects it.
    bad = docs[0].to_mapping()
    bad["id"] = "BAD-1"
    bad["sku"] = "BAD-1"
    bad["unknown_field"] = "not in mapping"

    indexer = ElasticsearchBulkIndexer(client=get_client(), index=empty_index, batch_size=10)
    result = indexer.index_documents([docs[0].to_mapping(), bad, docs[1].to_mapping()])

    assert result.failed == 1
    assert result.succeeded == 2
    failure = result.failures[0]
    assert failure.document_id == "BAD-1"
    assert failure.status == 400
    assert "unknown_field" in failure.reason or "strict" in failure.reason


# ---------------------------------------------------------------------------
# Bulk delete
# ---------------------------------------------------------------------------
def test_bulk_delete_removes_documents(empty_index: str) -> None:
    docs = _load_dataset()
    indexer = ElasticsearchBulkIndexer(client=get_client(), index=empty_index, batch_size=5)
    indexer.index_products(docs)
    assert _count(empty_index) == len(docs)

    ids_to_delete = [doc.id for doc in docs[:5]]
    result = indexer.delete_documents(ids_to_delete)

    assert result.failed == 0
    assert result.succeeded == len(ids_to_delete)
    assert _count(empty_index) == len(docs) - len(ids_to_delete)


def test_bulk_delete_of_missing_ids_is_a_success(empty_index: str) -> None:
    indexer = ElasticsearchBulkIndexer(client=get_client(), index=empty_index, batch_size=10)
    result = indexer.delete_documents(["NEVER-EXISTED-1", "NEVER-EXISTED-2"])

    assert result.failed == 0
    assert result.succeeded == 2


# ---------------------------------------------------------------------------
# The use case
# ---------------------------------------------------------------------------
def test_use_case_wraps_the_indexer(empty_index: str) -> None:
    docs = _load_dataset()[:5]
    indexer = ElasticsearchBulkIndexer(client=get_client(), index=empty_index, batch_size=10)
    use_case = BulkIndexProductsUseCase(indexer=indexer)

    result = use_case.execute(docs)

    assert result.failed == 0
    assert result.succeeded == len(docs)
    assert _count(empty_index) == len(docs)
