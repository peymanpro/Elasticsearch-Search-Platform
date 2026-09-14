"""
Domain value object representing a product document.

A ProductDocument is the in-memory shape of one line of the JSONL
dataset and one Elasticsearch document. It is created by the dataset
reader (Phase 4.2) and will be the input to the bulk indexer
(Phase 17). It is frozen: constructing a valid document is the only
way to get one, and no later stage can mutate it.

The class deliberately does not validate business rules beyond the
shape of a single document. Cross-document invariants (a brand's
products all agree on its name, a category is spelled consistently)
are dataset-level concerns and belong to the dataset validation in
Phase 4.5, not here.

Nothing in this module imports Django, Django REST Framework, or the
Elasticsearch client. The architecture tests enforce this.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.search.domain.product_schema import (
    Availability,
    Currency,
    ProductLanguage,
)


@dataclass(frozen=True, slots=True)
class ProductDocument:
    """
    A single product, as it will be stored in the catalog.

    Field types are stricter than the JSONL wire format:

    * ``tags`` is a tuple, not a list, so that the instance is
      hashable and cannot be mutated by a consumer.
    * ``price`` is a Decimal, not a float, so that currency arithmetic
      (if it ever happens) is exact.
    * ``language``, ``currency``, and ``availability`` are enum
      members, not raw strings, so that typos are impossible once a
      document is constructed.

    ``specifications`` is a read-only mapping and is excluded from
    equality and hashing: two documents that differ only in an
    unmodeled specification attribute are, for the platform's
    purposes, the same document identity.
    """

    id: str
    sku: str
    name: str
    brand: str
    category: str
    description: str
    tags: tuple[str, ...]
    specifications: Mapping[str, Any] = field(hash=False, compare=False)
    language: ProductLanguage
    price: Decimal
    currency: Currency
    rating: float
    availability: Availability
    created_at: datetime
    popularity: int

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> ProductDocument:
        """
        Build a ProductDocument from a raw JSONL record.

        The mapping is expected to use the exact field names from
        ``ProductField``. Unknown extra keys are ignored rather than
        rejected, because the JSONL format is allowed to carry
        forward-compatible additions; a strict rejection policy would
        break the reader the moment the dataset gained a new field.

        Raises:
            KeyError: a required field is absent.
            ValueError: a value cannot be coerced to its domain type.
        """
        return cls(
            id=str(raw["id"]),
            sku=str(raw["sku"]),
            name=str(raw["name"]),
            brand=str(raw["brand"]),
            category=str(raw["category"]),
            description=str(raw["description"]),
            tags=tuple(str(t) for t in raw["tags"]),
            specifications=dict(raw.get("specifications") or {}),
            language=ProductLanguage(raw["language"]),
            price=Decimal(str(raw["price"])),
            currency=Currency(raw["currency"]),
            rating=float(raw["rating"]),
            availability=Availability(raw["availability"]),
            created_at=_parse_iso_datetime(raw["created_at"]),
            popularity=int(raw["popularity"]),
        )


def _parse_iso_datetime(value: str) -> datetime:
    """
    Parse an ISO 8601 datetime string into a timezone-aware datetime.

    The JSONL dataset uses the trailing ``Z`` convention (UTC). Python
    before 3.11 does not accept ``Z`` in ``fromisoformat``; Python 3.11+
    does. This project requires 3.12, so no substitution is needed.
    """
    return datetime.fromisoformat(value)


__all__ = ["ProductDocument"]
