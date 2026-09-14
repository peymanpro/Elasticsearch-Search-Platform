"""Unit tests for the ProductDocument round-trip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.search.domain.product_document import ProductDocument

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET = REPO_ROOT / "data" / "products.jsonl"


def _first_real_document() -> ProductDocument:
    first_line = DATASET.read_text(encoding="utf-8").splitlines()[0]
    return ProductDocument.from_mapping(json.loads(first_line))


def test_to_mapping_produces_json_serializable_dict() -> None:
    doc = _first_real_document()
    payload = doc.to_mapping()
    # The whole point is that this succeeds without a custom encoder.
    json.dumps(payload)
    assert isinstance(payload, dict)


def test_roundtrip_through_mapping_is_stable() -> None:
    doc = _first_real_document()
    restored = ProductDocument.from_mapping(doc.to_mapping())
    assert restored == doc


def test_to_mapping_serializes_enums_as_strings() -> None:
    doc = _first_real_document()
    payload = doc.to_mapping()
    assert payload["language"] == "en"
    assert payload["currency"] in {"USD", "EUR", "GBP"}
    assert payload["availability"] in {"in_stock", "out_of_stock", "preorder", "discontinued"}


def test_to_mapping_serializes_tags_as_list() -> None:
    doc = _first_real_document()
    payload = doc.to_mapping()
    assert isinstance(payload["tags"], list)
    assert all(isinstance(t, str) for t in payload["tags"])


def test_to_mapping_serializes_price_as_float() -> None:
    doc = _first_real_document()
    payload = doc.to_mapping()
    assert isinstance(payload["price"], float)


def test_to_mapping_serializes_datetime_as_iso_string() -> None:
    doc = _first_real_document()
    payload = doc.to_mapping()
    assert isinstance(payload["created_at"], str)
    assert "T" in payload["created_at"]


def test_from_mapping_rejects_missing_required_field() -> None:
    with pytest.raises(KeyError):
        ProductDocument.from_mapping({"id": "X", "sku": "X"})


def test_all_real_dataset_documents_roundtrip() -> None:
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        original = ProductDocument.from_mapping(json.loads(line))
        restored = ProductDocument.from_mapping(original.to_mapping())
        assert restored == original
