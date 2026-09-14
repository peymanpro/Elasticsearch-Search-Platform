"""
Unit tests for the search-noise reader.

These tests do not require Elasticsearch. They exercise the reader
against the real fixture file and against small malformed inputs.
"""

from __future__ import annotations

from pathlib import Path

from infrastructure.datasets.noise_reader import (
    REQUIRED_KEYS,
    NoiseReadError,
    read_noise,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
NOISE_PATH = REPO_ROOT / "data" / "search_noise.jsonl"


def test_reads_the_real_noise_file_without_errors() -> None:
    entries, errors = read_noise(NOISE_PATH)
    assert errors == []
    assert len(entries) >= 30


def test_every_entry_has_the_required_keys() -> None:
    entries, _ = read_noise(NOISE_PATH)
    for entry in entries:
        for key in REQUIRED_KEYS:
            assert key in entry
            assert isinstance(entry[key], str)
            assert entry[key].strip()


def test_categories_are_from_a_known_set() -> None:
    known = {"exact", "typo", "spacing", "case", "reorder", "synonym"}
    entries, _ = read_noise(NOISE_PATH)
    for entry in entries:
        assert entry["category"] in known


def test_blank_lines_are_skipped(tmp_path: Path) -> None:
    target = tmp_path / "noise.jsonl"
    target.write_text(
        '{"noise":"a","canonical":"b","category":"typo","scenario":"S1"}'
        + "\n\n\n"
        + '{"noise":"c","canonical":"d","category":"exact","scenario":"S2"}'
        + "\n",
        encoding="utf-8",
    )
    entries, errors = read_noise(target)
    assert errors == []
    assert len(entries) == 2


def test_invalid_json_is_reported(tmp_path: Path) -> None:
    target = tmp_path / "bad.jsonl"
    target.write_text("not json\n", encoding="utf-8")
    entries, errors = read_noise(target)
    assert entries == []
    assert len(errors) == 1
    assert isinstance(errors[0], NoiseReadError)
    assert errors[0].line_number == 1
    assert "invalid JSON" in errors[0].reason


def test_missing_required_key_is_reported(tmp_path: Path) -> None:
    target = tmp_path / "missing.jsonl"
    target.write_text('{"noise":"a","canonical":"b"}\n', encoding="utf-8")
    entries, errors = read_noise(target)
    assert entries == []
    assert len(errors) == 1
    assert "missing required keys" in errors[0].reason
