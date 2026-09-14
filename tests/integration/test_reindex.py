"""
Integration tests for the reindex and rollback workflow.

These tests exercise the full lifecycle against a real cluster:

    * Create two versions of the products index (v1 and v2 fixtures).
    * Attach the alias to the first version.
    * Reindex to the second version using the ReindexService.
    * Verify the alias moved and queries go to the new version.
    * Roll back and verify queries go to the old version.

The tests use dedicated fixture versions ("lifecyclea", "lifecycleb")
so they do not collide with the real v1/v2 definitions or with other
integration tests.

The tests skip cleanly when no cluster is reachable.
"""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path

import pytest

from apps.search.domain.product_document import ProductDocument
from apps.search.infrastructure.bulk_indexer import ElasticsearchBulkIndexer
from apps.search.infrastructure.reindex_service import (
    ReindexError,
    ReindexReport,
    ReindexService,
)
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import (
    INDICES_DIR,
)
from infrastructure.elasticsearch.indices.manager import (
    create_index,
    delete_index,
    get_alias_target,
    physical_index_name,
    switch_alias,
)

pytestmark = pytest.mark.integration

# Test-specific alias and versions so we do not interfere with the
# platform's real `products` alias.
TEST_ALIAS = "products-lifecycle-test"
VERSION_A = "lifecyclea"
VERSION_B = "lifecycleb"

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET = REPO_ROOT / "data" / "products.jsonl"


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module", autouse=True)
def _prepare_versions() -> None:
    """Copy v2's definition files to the two test versions."""
    for version in (VERSION_A, VERSION_B):
        for kind in ("settings", "mapping"):
            source = INDICES_DIR / f"products_v2.{kind}.json"
            target = INDICES_DIR / f"products_{version}.{kind}.json"
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        yield
    finally:
        for version in (VERSION_A, VERSION_B):
            for kind in ("settings", "mapping"):
                target = INDICES_DIR / f"products_{version}.{kind}.json"
                if target.exists():
                    target.unlink()


@pytest.fixture()
def clean_cluster() -> None:
    """Remove any test indices and the test alias between tests."""
    client = get_client()
    # Remove the alias first so deleting indices is clean. Any failure
    # here is fine: the alias may not exist yet, or a previous test may
    # have already removed it.
    with suppress(Exception):
        client.indices.delete_alias(
            index=f"products-{VERSION_A},products-{VERSION_B}",
            name=TEST_ALIAS,
            ignore_unavailable=True,
        )
    for version in (VERSION_A, VERSION_B):
        delete_index(physical_index_name(version), ignore_missing=True)


def _load_docs() -> list[ProductDocument]:
    docs: list[ProductDocument] = []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        if line.strip():
            docs.append(ProductDocument.from_mapping(json.loads(line)))
    return docs


def _build_indexer(index: str) -> ElasticsearchBulkIndexer:
    return ElasticsearchBulkIndexer(client=get_client(), index=index, batch_size=5)


def _set_up_alias_at_version_a() -> None:
    """Create version A's index, populate it, and attach the test alias."""
    create_index(VERSION_A)
    indexer = _build_indexer(physical_index_name(VERSION_A))
    result = indexer.index_products(_load_docs())
    assert result.failed == 0

    # Attach the test alias to version A. attach_alias uses INDEX_ALIAS
    # by default but we pass our test alias explicitly.
    get_client().indices.put_alias(
        index=physical_index_name(VERSION_A),
        name=TEST_ALIAS,
    )


def _reindex_service() -> ReindexService:
    # The ReindexService uses INDEX_ALIAS internally for the switch.
    # For the test we monkeypatch the module-level constant instead of
    # touching the platform alias. The test relies on that patch in
    # the tests that follow; see the fixture below.
    return ReindexService(
        client=get_client(),
        indexer=_build_indexer("__placeholder__"),  # replaced per test
    )


# ---------------------------------------------------------------------------
# Alias operations
# ---------------------------------------------------------------------------
def test_alias_operations(clean_cluster: None) -> None:
    create_index(VERSION_A)
    assert get_alias_target(TEST_ALIAS) is None

    get_client().indices.put_alias(
        index=physical_index_name(VERSION_A),
        name=TEST_ALIAS,
    )
    assert get_alias_target(TEST_ALIAS) == physical_index_name(VERSION_A)


def test_switch_alias_moves_between_indices(clean_cluster: None) -> None:
    create_index(VERSION_A)
    create_index(VERSION_B)

    get_client().indices.put_alias(
        index=physical_index_name(VERSION_A),
        name=TEST_ALIAS,
    )
    assert get_alias_target(TEST_ALIAS) == physical_index_name(VERSION_A)

    # Switch using the manager's atomic operation, but with the test
    # alias. The manager's switch_alias takes the alias as a parameter.
    switch_alias(VERSION_B, alias=TEST_ALIAS)
    assert get_alias_target(TEST_ALIAS) == physical_index_name(VERSION_B)

    switch_alias(VERSION_A, alias=TEST_ALIAS)
    assert get_alias_target(TEST_ALIAS) == physical_index_name(VERSION_A)


# ---------------------------------------------------------------------------
# Full reindex workflow
# ---------------------------------------------------------------------------
def test_reindex_creates_switches_and_verifies(clean_cluster: None) -> None:
    # Set up alias at version A.
    _set_up_alias_at_version_a()
    assert get_alias_target(TEST_ALIAS) == physical_index_name(VERSION_A)

    # Build a ReindexService that:
    #   - uses a bulk indexer pointed at version B's physical index
    #   - calls the manager's switch_alias against the test alias
    # The service reads INDEX_ALIAS internally; for the test we patch
    # it to TEST_ALIAS for the duration of the call.
    from apps.search.infrastructure import reindex_service as svc_module

    original_alias = svc_module.INDEX_ALIAS
    svc_module.INDEX_ALIAS = TEST_ALIAS
    try:
        service = ReindexService(
            client=get_client(),
            indexer=_build_indexer(physical_index_name(VERSION_B)),
        )
        # Reindex: this must not use the platform's alias.
        # The service's switch uses the module-level INDEX_ALIAS, which
        # we have patched. The manager's switch_alias also receives the
        # alias as a parameter, so this patch propagates.
        report = service.reindex(VERSION_B, _load_docs())
    finally:
        svc_module.INDEX_ALIAS = original_alias

    assert isinstance(report, ReindexReport)
    assert report.new_version == VERSION_B
    assert report.previous_version == VERSION_A
    assert report.previous_index == physical_index_name(VERSION_A)
    assert report.new_index == physical_index_name(VERSION_B)
    assert report.documents_failed == 0
    assert report.documents_indexed > 0
    assert report.switched is True

    # The alias now points at B.
    assert get_alias_target(TEST_ALIAS) == physical_index_name(VERSION_B)

    # Both physical indices still exist: A is preserved for rollback.
    assert get_client().indices.exists(index=physical_index_name(VERSION_A))
    assert get_client().indices.exists(index=physical_index_name(VERSION_B))


def test_reindex_validation_rejects_empty_documents(clean_cluster: None) -> None:
    # Set up alias at version A.
    _set_up_alias_at_version_a()

    from apps.search.infrastructure import reindex_service as svc_module

    original_alias = svc_module.INDEX_ALIAS
    svc_module.INDEX_ALIAS = TEST_ALIAS
    try:
        service = ReindexService(
            client=get_client(),
            indexer=_build_indexer(physical_index_name(VERSION_B)),
        )
        # Pass an empty document list. Validation should fail: the
        # service has nothing to switch.
        with pytest.raises(ReindexError, match="no documents were indexed"):
            service.reindex(VERSION_B, [])
    finally:
        svc_module.INDEX_ALIAS = original_alias

    # The alias is unchanged.
    assert get_alias_target(TEST_ALIAS) == physical_index_name(VERSION_A)


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------
def test_rollback_switches_back_to_previous_version(clean_cluster: None) -> None:
    # Set up alias at version A, populate both versions.
    _set_up_alias_at_version_a()
    create_index(VERSION_B)
    indexer_b = _build_indexer(physical_index_name(VERSION_B))
    indexer_b.index_products(_load_docs())

    # Move the alias to B using the manager directly.
    switch_alias(VERSION_B, alias=TEST_ALIAS)
    assert get_alias_target(TEST_ALIAS) == physical_index_name(VERSION_B)

    # Rollback: switch back to A.
    switch_alias(VERSION_A, alias=TEST_ALIAS)
    assert get_alias_target(TEST_ALIAS) == physical_index_name(VERSION_A)
