"""
Index definitions for the products catalog.

The settings and mapping for each index version are stored as JSON
files next to this module. The loader reads them and exposes them as
dictionaries. There is one definition today:

    products_v1    -- the first version of the products index

A later version (products_v2) would be added as additional files and
exposed through the same loader. See docs/12-index-design.md.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

INDICES_DIR = Path(__file__).resolve().parent


@cache
def load_settings(version: str) -> dict[str, Any]:
    """
    Return the settings block for an index version.

    Args:
        version: A version identifier matching a file named
            ``products_{version}.settings.json`` (e.g. ``"v1"``).
    """
    path = INDICES_DIR / f"products_{version}.settings.json"
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


@cache
def load_mapping(version: str) -> dict[str, Any]:
    """
    Return the mapping block for an index version.

    The returned dictionary contains ``dynamic`` and ``properties``.
    When passing it to the Elasticsearch client, wrap it under the
    ``mappings`` key (see the manager for how this is done).
    """
    path = INDICES_DIR / f"products_{version}.mapping.json"
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


CURRENT_INDEX_VERSION = "v1"
INDEX_ALIAS = "products"


__all__ = [
    "CURRENT_INDEX_VERSION",
    "INDEX_ALIAS",
    "INDICES_DIR",
    "load_mapping",
    "load_settings",
]
