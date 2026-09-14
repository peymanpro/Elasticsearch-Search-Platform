"""
Integration tests for the index manager.

These tests require a running Elasticsearch cluster. They create the
real products-v1 index, verify its settings and mapping, then delete
it. To avoid interfering with any manually created index, the tests
use a suffix variant of the version string.
"""

from __future__ import annotations

import pytest

from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import (
    index_document,
)
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import (
    load_mapping,
    load_settings,
)
from infrastructure.elasticsearch.indices.manager import (
    create_index,
    delete_index,
    index_exists,
    physical_index_name,
    refresh_index,
)

pytestmark = pytest.mark.integration

TEST_VERSION = "v1test"


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture()
def test_index() -> str:
    """Create the test index, yield its name, delete it."""
    # Create the file-based definition under a test-only version
    # suffix so that a real products-v1 index (created by a later
    # phase) is not clobbered.
    from infrastructure.elasticsearch.indices import INDICES_DIR

    for kind in ("settings", "mapping"):
        source = INDICES_DIR / f"products_v1.{kind}.json"
        target = INDICES_DIR / f"products_{TEST_VERSION}.{kind}.json"
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    name = physical_index_name(TEST_VERSION)
    # Ensure clean slate in case of a prior failure
    delete_index(name, ignore_missing=True)
    create_index(TEST_VERSION)

    try:
        yield name
    finally:
        delete_index(name, ignore_missing=True)
        # Clean up the temporary definition files
        for kind in ("settings", "mapping"):
            target = INDICES_DIR / f"products_{TEST_VERSION}.{kind}.json"
            if target.exists():
                target.unlink()


def test_create_index_makes_it_exist(test_index: str) -> None:
    assert index_exists(test_index) is True


def test_created_index_has_expected_settings(test_index: str) -> None:
    settings = get_client().indices.get_settings(index=test_index)
    inner = settings[test_index]["settings"]["index"]
    assert inner["number_of_shards"] == "1"
    assert inner["number_of_replicas"] == "0"


def test_created_index_has_expected_mapping(test_index: str) -> None:
    mapping = get_client().indices.get_mapping(index=test_index)
    props = mapping[test_index]["mappings"]["properties"]

    assert mapping[test_index]["mappings"]["dynamic"] == "strict"

    expected = {
        "id": "keyword",
        "sku": "keyword",
        "name": "text",
        "brand": "text",
        "category": "text",
        "description": "text",
        "tags": "text",
        "specifications": "flattened",
        "language": "keyword",
        "price": "double",
        "currency": "keyword",
        "rating": "double",
        "availability": "keyword",
        "created_at": "date",
        "popularity": "long",
    }
    for field, expected_type in expected.items():
        assert field in props, f"missing field: {field}"
        actual = props[field]["type"]
        assert actual == expected_type, f"{field}: expected {expected_type}, got {actual}"


def test_multi_field_subfields_exist(test_index: str) -> None:
    mapping = get_client().indices.get_mapping(index=test_index)
    props = mapping[test_index]["mappings"]["properties"]

    for field in ("name", "brand", "category", "tags"):
        assert "fields" in props[field], f"{field} should have a keyword subfield"
        assert "keyword" in props[field]["fields"], f"{field}.keyword missing"


def test_delete_index_is_idempotent(test_index: str) -> None:
    delete_index(test_index)
    assert index_exists(test_index) is False
    # A second delete is a no-op because ignore_missing=True by default
    delete_index(test_index)


def test_dynamic_strict_rejects_unknown_top_level_field(test_index: str) -> None:
    from elasticsearch import BadRequestError

    with pytest.raises(BadRequestError):
        index_document(
            index=test_index,
            document_id="bad-1",
            source={"id": "bad-1", "unknown_field": "x"},
            refresh=True,
        )


def test_refresh_index_does_not_raise(test_index: str) -> None:
    refresh_index(test_index)  # must not raise


def test_loaders_return_the_expected_shapes() -> None:
    settings = load_settings("v1")
    mapping = load_mapping("v1")
    assert "number_of_shards" in settings
    assert "properties" in mapping
    assert mapping["dynamic"] == "strict"
