"""
Unit tests for the JSONL product reader.

These tests do not require Elasticsearch. They exercise the reader
against the real dataset and against small fixtures created in
temporary directories.
"""

from __future__ import annotations

from pathlib import Path

from infrastructure.datasets.jsonl_reader import (
    JsonlReadError,
    ReadResult,
    read_products,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "data" / "products.jsonl"


def test_reads_the_real_dataset_without_errors() -> None:
    result = read_products(DATASET_PATH)
    assert isinstance(result, ReadResult)
    assert result.is_valid is True
    assert result.errors == ()
    assert len(result.documents) >= 10


def test_documents_carry_expected_field_types() -> None:
    result = read_products(DATASET_PATH)
    doc = result.documents[0]
    assert isinstance(doc.sku, str)
    assert isinstance(doc.tags, tuple)
    assert all(isinstance(t, str) for t in doc.tags)
    assert isinstance(doc.specifications, dict)
    assert isinstance(doc.price, type(doc.price))
    assert doc.language.value == "en"


def test_empty_file_returns_no_documents_and_no_errors(tmp_path: Path) -> None:
    target = tmp_path / "empty.jsonl"
    target.write_text("", encoding="utf-8")
    result = read_products(target)
    assert result.documents == ()
    assert result.errors == ()
    assert result.is_valid is True


def test_blank_lines_are_skipped(tmp_path: Path) -> None:
    target = tmp_path / "blanks.jsonl"
    real = DATASET_PATH.read_text(encoding="utf-8").splitlines()[0]
    target.write_text(f"{real}\n\n\n{real}\n", encoding="utf-8")
    result = read_products(target)
    assert len(result.documents) == 2
    assert result.errors == ()


def test_invalid_json_line_is_reported_with_line_number(tmp_path: Path) -> None:
    target = tmp_path / "bad-json.jsonl"
    target.write_text("{not json}\n", encoding="utf-8")
    result = read_products(target)
    assert result.documents == ()
    assert len(result.errors) == 1
    error = result.errors[0]
    assert isinstance(error, JsonlReadError)
    assert error.line_number == 1
    assert "invalid JSON" in error.reason
    assert result.is_valid is False


def test_missing_required_field_is_reported(tmp_path: Path) -> None:
    target = tmp_path / "missing-field.jsonl"
    target.write_text('{"sku":"X","name":"Incomplete"}\n', encoding="utf-8")
    result = read_products(target)
    assert result.documents == ()
    assert len(result.errors) == 1
    assert "invalid product document" in result.errors[0].reason


def test_invalid_enum_value_is_reported(tmp_path: Path) -> None:
    import json

    real_line = DATASET_PATH.read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(real_line)
    payload["currency"] = "XYZ"
    target = tmp_path / "bad-enum.jsonl"
    target.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    result = read_products(target)
    assert result.documents == ()
    assert len(result.errors) == 1
    assert "invalid product document" in result.errors[0].reason


def test_reader_does_not_stop_on_first_error(tmp_path: Path) -> None:
    target = tmp_path / "mixed.jsonl"
    good_line = DATASET_PATH.read_text(encoding="utf-8").splitlines()[0]
    bad_json = "not json"
    bad_doc = chr(123) + chr(34) + "sku" + chr(34) + ": " + chr(34) + "X" + chr(34) + chr(125)
    body = "\n".join([bad_json, bad_doc, good_line]) + "\n"
    target.write_text(body, encoding="utf-8")
    result = read_products(target)
    assert len(result.errors) == 2
    assert len(result.documents) == 1
