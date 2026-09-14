"""
Score explanation value objects.

The platform's explainability layer exposes Elasticsearch's ``_explain``
response as a recursive value-object tree. Each node carries its own
score contribution, a human-readable description, and an optional set
of children. A caller reads the top-level value for a quick answer and
recurses into ``details`` for the full breakdown.

The tree is deliberately preserved rather than flattened: the point of
an explanation is to know which clause contributed what, and a flat
list loses that structure. See docs/21-explainability.md section 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ScoreExplanation:
    """
    One node of a scoring explanation tree.

    Attributes:
        value: The numeric contribution of this node.
        description: A human-readable description of what this node
            represents. Elasticsearch generates these descriptions;
            the platform does not parse or modify them.
        details: Child nodes. Empty for a leaf. The tuple preserves
            the order Elasticsearch returned.
    """

    value: float
    description: str
    details: tuple[ScoreExplanation, ...] = field(default_factory=tuple)

    @property
    def is_leaf(self) -> bool:
        """True if this node has no children."""
        return not self.details


@dataclass(frozen=True, slots=True)
class ExplainResult:
    """
    The result of explaining a (query, document) pair.

    Attributes:
        matched: True if the document matches the query.
        explanation: The explanation tree, or None when the document
            does not match. The two states are distinct: "no match"
            versus "matched but scored zero". Elasticsearch omits the
            explanation field for non-matching documents, and the
            domain preserves that omission as None.
    """

    matched: bool
    explanation: ScoreExplanation | None


__all__ = [
    "ExplainResult",
    "ScoreExplanation",
]
