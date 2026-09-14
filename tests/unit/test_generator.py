"""
Unit tests for the deterministic product dataset generator.

These tests do not require Elasticsearch. They assert the two
properties the rest of the project relies on:

    * Determinism -- same seed, same output, byte for byte.
    * Schema conformance -- generated documents are readable by the
      same JSONL reader that consumes the hand-authored dataset.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from generate_products import generate, write_dataset  # noqa: E402

from infrastructure.datasets.jsonl_reader import read_products  # noqa: E402


def test_generate_returns_requested_count() -> None:
    docs = generate(seed=1, count=7)
    assert len(docs) == 7


def test_same_seed_produces_identical_documents() -> None:
    first = generate(seed=42, count=20)
    second = generate(seed=42, count=20)
    assert first == second


def test_different_seeds_produce_different_documents() -> None:
    first = generate(seed=1, count=20)
    second = generate(seed=2, count=20)
    assert first != second


def test_generated_documents_are_readable_by_the_jsonl_reader(tmp_path: Path) -> None:
    docs = generate(seed=99, count=15)
    target = tmp_path / "products.jsonl"
    write_dataset(docs, target)

    result = read_products(target)
    assert result.errors == ()
    assert len(result.documents) == 15


def test_generated_documents_have_unique_skus() -> None:
    docs = generate(seed=7, count=100)
    skus = [d["sku"] for d in docs]
    assert len(skus) == len(set(skus))


def test_generated_documents_use_expected_enum_values() -> None:
    docs = generate(seed=3, count=50)
    for doc in docs:
        assert doc["language"] == "en"
        assert doc["currency"] in {"USD", "EUR", "GBP"}
        assert doc["availability"] in {"in_stock", "out_of_stock", "preorder", "discontinued"}
        assert 0.0 <= doc["rating"] <= 5.0
        assert doc["price"] > 0
        assert doc["popularity"] >= 0


def test_write_dataset_is_byte_deterministic(tmp_path: Path) -> None:
    docs_a = generate(seed=12345, count=30)
    docs_b = generate(seed=12345, count=30)
    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    write_dataset(docs_a, path_a)
    write_dataset(docs_b, path_b)
    assert path_a.read_bytes() == path_b.read_bytes()
