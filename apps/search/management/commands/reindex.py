"""
Management command: reindex.

Builds a new physical index version, populates it from a JSONL dataset,
validates the result, and switches the products alias to the new version.
See docs/23-index-lifecycle.md and docs/24-search-api.md section 8.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.search.domain.product_document import ProductDocument
from apps.search.infrastructure.bulk_indexer import ElasticsearchBulkIndexer
from apps.search.infrastructure.reindex_service import (
    ReindexError,
    ReindexReport,
    ReindexService,
)
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.indices.manager import physical_index_name

DEFAULT_DATASET = Path("data") / "products.jsonl"


class Command(BaseCommand):
    help = (
        "Build a new physical index version from the dataset, validate it, "
        "and switch the products alias to the new version."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--version",
            required=True,
            help="Target version identifier, e.g. v3.",
        )
        parser.add_argument(
            "--dataset",
            type=Path,
            default=DEFAULT_DATASET,
            help=f"Path to the JSONL dataset. Default: {DEFAULT_DATASET}",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Bulk indexing batch size. Default: 500.",
        )

    def handle(self, *args, **options) -> None:
        version = options["version"]
        dataset_path: Path = options["dataset"]
        batch_size = int(options["batch_size"])

        if not dataset_path.exists():
            raise CommandError(f"dataset not found: {dataset_path}")

        self.stdout.write(f"Loading dataset from {dataset_path}")
        documents = _load_documents(dataset_path)
        self.stdout.write(f"  loaded {len(documents)} documents")

        target_index = physical_index_name(version)
        self.stdout.write(f"Target physical index: {target_index}")

        indexer = ElasticsearchBulkIndexer(
            client=get_client(),
            index=target_index,
            batch_size=batch_size,
        )
        service = ReindexService(client=get_client(), indexer=indexer)

        try:
            report = service.reindex(version, documents)
        except ReindexError as exc:
            raise CommandError(f"reindex failed: {exc}") from exc

        self._print_report(report)

    def _print_report(self, report: ReindexReport) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Reindex complete"))
        self.stdout.write(f"  previous version : {report.previous_version}")
        self.stdout.write(f"  previous index   : {report.previous_index}")
        self.stdout.write(f"  new version      : {report.new_version}")
        self.stdout.write(f"  new index        : {report.new_index}")
        self.stdout.write(f"  documents indexed: {report.documents_indexed}")
        self.stdout.write(f"  documents failed : {report.documents_failed}")
        self.stdout.write(f"  alias switched   : {report.switched}")


def _load_documents(path: Path) -> list[ProductDocument]:
    """Read a JSONL file and parse each line into a ProductDocument."""
    documents: list[ProductDocument] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CommandError(f"line {line_number} is not valid JSON: {exc.msg}") from exc
        try:
            documents.append(ProductDocument.from_mapping(payload))
        except (KeyError, ValueError, TypeError) as exc:
            raise CommandError(
                f"line {line_number} is not a valid product document: {exc!r}"
            ) from exc
    return documents
