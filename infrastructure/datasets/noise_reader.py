"""
JSONL reader for the search-noise dataset.

The noise dataset maps user-input variants (typos, spacing variants,
reorderings, synonym candidates) to the canonical term they should
match. Phase 10 (fuzzy search) and Phase 11 (synonyms) use it as the
corpus for typo-tolerance and synonym-expansion tests.

Entries are intentionally plain dictionaries, not typed value objects.
The format has four string fields with no invariants beyond presence,
and the entire dataset is a test fixture. A typed class would be
ceremony.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_KEYS = ("noise", "canonical", "category", "scenario")


class NoiseReadError(ValueError):
    """Raised when a JSONL line cannot be read as a noise entry."""

    def __init__(self, *, line_number: int, reason: str) -> None:
        self.line_number = line_number
        self.reason = reason
        super().__init__(f"line {line_number}: {reason}")


def read_noise(
    path: Path | str,
) -> tuple[list[dict[str, Any]], list[NoiseReadError]]:
    """
    Read a noise JSONL file.

    Returns a tuple of (entries, errors). Blank lines are skipped.
    Every non-blank line must be a JSON object containing the four
    required keys.
    """
    source = Path(path)
    entries: list[dict[str, Any]] = []
    errors: list[NoiseReadError] = []

    with source.open("r", encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(
                    NoiseReadError(
                        line_number=line_number,
                        reason=f"invalid JSON: {exc.msg}",
                    )
                )
                continue

            if not isinstance(payload, dict):
                errors.append(
                    NoiseReadError(
                        line_number=line_number,
                        reason="entry is not a JSON object",
                    )
                )
                continue

            missing = [k for k in REQUIRED_KEYS if k not in payload]
            if missing:
                errors.append(
                    NoiseReadError(
                        line_number=line_number,
                        reason=f"missing required keys: {missing}",
                    )
                )
                continue

            entries.append(payload)

    return entries, errors


__all__ = ["NoiseReadError", "REQUIRED_KEYS", "read_noise"]
