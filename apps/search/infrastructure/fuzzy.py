"""
Fuzzy query composer (infrastructure layer).

Composes the Elasticsearch query used by the fuzzy search strategy:

    multi_match over a boosted field set, with fuzziness: AUTO and
    prefix_length: 2.

All the fuzzy policy parameters live as constructor arguments with
documented defaults. The class is stateless beyond those parameters.

The application layer's fuzzy strategy depends on the domain Protocol
``FuzzyQueryComposer``, not on this class. The composition root wires the
concrete implementation. See docs/15-fuzzy-search.md.
"""

from __future__ import annotations

from typing import Any

from infrastructure.elasticsearch.query.builder import QueryBuilder
from infrastructure.elasticsearch.query.clauses import MultiMatchClause

# The field list is imported at module scope from the relevance module
# because the platform's policy is that fuzzy and relevant searches
# target the same fields. If a future phase changes one list, it must
# change the other; a divergence would silently rank fuzzy results
# differently from relevant ones for the same query.
DEFAULT_FUZZINESS = "AUTO"
DEFAULT_PREFIX_LENGTH = 2


class ElasticsearchFuzzyQueryComposer:
    """
    Compose a fuzzy multi_match query.

    Args:
        fields: The fields to search, in the same ``name^boost`` form
            used by the relevance composer. Callers typically pass
            ``FIELD_BOOSTS`` from the relevance module.
        fuzziness: The ``fuzziness`` parameter value. Defaults to
            ``AUTO``.
        prefix_length: The ``prefix_length`` parameter value. Defaults
            to 2.
    """

    def __init__(
        self,
        fields: tuple[str, ...],
        fuzziness: str = DEFAULT_FUZZINESS,
        prefix_length: int = DEFAULT_PREFIX_LENGTH,
    ) -> None:
        self._fields = fields
        self._fuzziness = fuzziness
        self._prefix_length = prefix_length

    def build(self, text: str) -> dict[str, Any]:
        """Return the complete Elasticsearch fuzzy query for ``text``."""
        return (
            QueryBuilder()
            .must(
                MultiMatchClause(
                    fields=self._fields,
                    value=text,
                    fuzziness=self._fuzziness,
                    prefix_length=self._prefix_length,
                )
            )
            .build()
        )


__all__ = [
    "DEFAULT_FUZZINESS",
    "DEFAULT_PREFIX_LENGTH",
    "ElasticsearchFuzzyQueryComposer",
]
