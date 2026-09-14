"""
Management command: reindex_status.

Reports the current alias target, the document count, and the list of
physical indices that exist for the products alias. Useful for
verifying a reindex succeeded and for spotting stale indices.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.indices import INDEX_ALIAS
from infrastructure.elasticsearch.indices.manager import get_alias_target


class Command(BaseCommand):
    help = "Report the current products alias target and index status."

    def handle(self, *args, **options) -> None:
        client = get_client()

        target = get_alias_target(INDEX_ALIAS)
        self.stdout.write(f"alias          : {INDEX_ALIAS}")
        self.stdout.write(f"points_at      : {target}")

        if target is not None:
            try:
                client.indices.refresh(index=INDEX_ALIAS)
                count = int(client.count(index=INDEX_ALIAS)["count"])
            except Exception as exc:  # noqa: BLE001 - reporting, not raising
                self.stdout.write(self.style.WARNING(f"count failed: {exc}"))
                count = -1
            self.stdout.write(f"document_count : {count}")

        # List all physical indices matching products-*
        indices = client.indices.get(index="products-*", ignore_unavailable=True)
        self.stdout.write("")
        self.stdout.write("physical indices:")
        if not indices:
            self.stdout.write("  (none)")
        else:
            for name in sorted(indices.keys()):
                marker = " (live)" if name == target else ""
                self.stdout.write(f"  {name}{marker}")
