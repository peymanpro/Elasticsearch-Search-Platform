"""
Index definitions for the products catalog.

The settings and mapping for each index version are stored as JSON
files next to this module. The loader reads them and exposes them as
dictionaries. There is one definition today:

    products_v1    -- the first version of the products index

A later version (products_v2) would be added as additional files and
exposed through the same loader. See docs/12-index-design.md.

Synonym injection
-----------------
The settings file declares a synonym filter with an empty ``synonyms``
array. The loader populates that array at load time by reading the
synonym file at ``infrastructure/elasticsearch/synonyms/
products_synonyms.txt``. This keeps the synonym file as the single
source of truth for the vocabulary while leaving the settings JSON
declarative and hand-readable. See docs/16-synonyms.md.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

INDICES_DIR = Path(__file__).resolve().parent
SYNONYMS_DIR = INDICES_DIR.parent / "synonyms"
SYNONYMS_FILE = SYNONYMS_DIR / "products_synonyms.txt"


@cache
def _load_synonym_lines() -> tuple[str, ...]:
    """
    Return the non-comment, non-blank lines of the synonym file.

    The synonym filter accepts an array of strings where each string is
    one rule (an equivalence group or an explicit mapping). Comment
    lines beginning with '#' and blank lines are stripped.
    """
    if not SYNONYMS_FILE.exists():
        return ()
    lines: list[str] = []
    for raw in SYNONYMS_FILE.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return tuple(lines)


@cache
def load_settings(version: str) -> dict[str, Any]:
    """
    Return the settings block for an index version, with synonyms
    injected.

    Args:
        version: A version identifier matching a file named
            ``products_{version}.settings.json`` (e.g. ``"v1"``).
    """
    path = INDICES_DIR / f"products_{version}.settings.json"
    with path.open("r", encoding="utf-8") as stream:
        settings = json.load(stream)

    # Inject the synonym list into the filter definition. The JSON
    # declares the filter with an empty array so that the shape is
    # visible; the loader fills it.
    try:
        synonym_filter = settings["analysis"]["filter"]["product_synonym_filter"]
    except KeyError:
        return settings  # settings without a synonym filter are valid

    synonym_filter["synonyms"] = list(_load_synonym_lines())
    return settings


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
    "SYNONYMS_DIR",
    "SYNONYMS_FILE",
    "load_mapping",
    "load_settings",
]
