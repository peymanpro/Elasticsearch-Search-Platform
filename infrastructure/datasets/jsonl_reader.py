"""
JSONL reader for the product dataset.

The reader walks a JSONL file one line at a time, parses each line
as JSON, and constructs a ``ProductDocument`` from the resulting
mapping. Its only responsibilities are:

    * Open the file as UTF-8.
    * Skip blank lines.
    * Parse each non-blank line as JSON.
    * Delegate to ``ProductDocument.from_mapping`` to construct the
      domain object.
    * Report the source line number on any failure so that the
      offending row can be found in the file.

The reader does not validate cross-document invariants (uniqueness
of ids, consistency of brand capitalization). Those belong to the
dataset generator and its validation step in Phase 4.5.

Nothing in this module imports Django, DRF, or the Elasticsearch
client. The architecture tests enforce this.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from apps.search.domain.product_document import ProductDocument


class JsonlReadError(ValueError):
    """
    Raised when a JSONL line cannot be read as a product document.

    Carries the source line number and the offending line so that the
    failure is actionable without re-running under a debugger.
    """

    def __init__(self, *, line_number: int, line: str, reason: str) -> None:
        self.line_number = line_number
        self.line = line
        self.reason = reason
        super().__init__(f"line {line_number}: {reason}")


@dataclass(frozen=True, slots=True)
class ReadResult:
    """
    Aggregate result of reading a JSONL file.

    Attributes:
        documents: All successfully parsed documents, in file order.
        errors: All failures encountered. Reading does not stop on the
            first error; every malformed line is reported. This makes
            the tool useful as a dataset validator, not just a loader.
    """

    documents: tuple[ProductDocument, ...]
    errors: tuple[JsonlReadError, ...]

    @property
    def is_valid(self) -> bool:
        """True if no errors were encountered."""
        return not self.errors


def read_products(path: Path | str) -> ReadResult:
    """
    Read a product JSONL file and return both valid documents and
    errors.

    The function is strict about what it will not tolerate (blank
    lines are skipped; every non-blank line must parse as JSON and
    must produce a valid ``ProductDocument``), and lenient about
    structure (callers receive errors rather than exceptions, so a
    partially valid dataset can still be inspected).
    """
    source = Path(path)
    documents: list[ProductDocument] = []
    errors: list[JsonlReadError] = []

    with source.open("r", encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(
                    JsonlReadError(
                        line_number=line_number,
                        line=line,
                        reason=f"invalid JSON: {exc.msg}",
                    )
                )
                continue

            try:
                documents.append(ProductDocument.from_mapping(payload))
            except (KeyError, ValueError, TypeError) as exc:
                errors.append(
                    JsonlReadError(
                        line_number=line_number,
                        line=line,
                        reason=f"invalid product document: {exc!r}",
                    )
                )

    return ReadResult(
        documents=tuple(documents),
        errors=tuple(errors),
    )


__all__ = ["JsonlReadError", "ReadResult", "read_products"]
