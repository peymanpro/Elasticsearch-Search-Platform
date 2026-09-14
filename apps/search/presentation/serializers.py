"""
Request serializers.

These serializers describe the HTTP shape of every request the search
API accepts. They validate field presence and type; they do not enforce
domain rules. Domain rules (``page`` must be positive, ``rating`` must
be within 0-5, ``prefix`` must be non-empty) are enforced by the value
objects the use cases construct from these inputs. A request that
passes DRF validation but violates a domain rule fails at the use-case
boundary with a translated error.

See docs/24-search-api.md.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class FilterSerializer(serializers.Serializer):
    """Optional filter predicates. Every field is optional."""

    category = serializers.CharField(required=False, allow_blank=False)
    brand = serializers.CharField(required=False, allow_blank=False)
    availability = serializers.CharField(required=False, allow_blank=False)
    price_min = serializers.FloatField(required=False)
    price_max = serializers.FloatField(required=False)
    rating_min = serializers.FloatField(required=False)
    rating_max = serializers.FloatField(required=False)


class SortSerializer(serializers.Serializer):
    """A field and direction. Both fields are optional; domain defaults apply."""

    field = serializers.CharField(required=False, allow_blank=False)
    direction = serializers.CharField(required=False, allow_blank=False)


class SearchRequestSerializer(serializers.Serializer):
    """Body of a search request."""

    query = serializers.CharField(allow_blank=False)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1)
    cursor = serializers.ListField(
        child=serializers.JSONField(),
        required=False,
        allow_empty=False,
        help_text=(
            "Sort values of the last hit on the previous page. When "
            "supplied, ``page`` is ignored and pagination is cursor-based."
        ),
    )
    filters = FilterSerializer(required=False)
    sort = SortSerializer(required=False)
    include_facets = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """
        Reject cursor and page used together.

        Cursor-based pagination and offset-based pagination are mutually
        exclusive (Phase 15 section 5.2). A request that supplies both
        is a caller mistake, and it fails here rather than silently
        ignoring one of them.
        """
        cursor = attrs.get("cursor")
        page = attrs.get("page")
        if cursor is not None and page is not None:
            raise serializers.ValidationError(
                "cursor and page are mutually exclusive; supply one or the other"
            )
        return attrs


class SuggestRequestSerializer(serializers.Serializer):
    """Query string of a suggest request."""

    q = serializers.CharField(allow_blank=False)
    limit = serializers.IntegerField(required=False, min_value=1)


class ExplainRequestSerializer(serializers.Serializer):
    """Body of an explain request."""

    query = serializers.CharField(allow_blank=False)
    document_id = serializers.CharField(allow_blank=False)


# ---------------------------------------------------------------------------
# Search response
# ---------------------------------------------------------------------------
class HitSerializer(serializers.Serializer):
    """One hit in a search response."""

    id = serializers.CharField(help_text="Document identifier.")
    score = serializers.FloatField(help_text="Relevance score.")
    source = serializers.DictField(
        help_text="The document's fields. Treated as opaque by the API.",
    )
    highlights = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField()),
        help_text=(
            "Mapping from field name to the fragments that matched. "
            "Fields that did not match are absent."
        ),
    )


class FacetBucketSerializer(serializers.Serializer):
    """One bucket of a facet."""

    value = serializers.CharField()
    count = serializers.IntegerField()


class FacetsSerializer(serializers.Serializer):
    """The four facets computed over a search's result set."""

    categories = FacetBucketSerializer(many=True)
    brands = FacetBucketSerializer(many=True)
    availability = FacetBucketSerializer(many=True)
    price_ranges = FacetBucketSerializer(many=True)


class SearchResponseSerializer(serializers.Serializer):
    """Response body of ``POST /api/search/``."""

    query = serializers.CharField(help_text="The text that was searched for.")
    total = serializers.IntegerField(
        help_text="Total number of matching documents across the index.",
    )
    page = serializers.IntegerField(
        allow_null=True,
        help_text=("Offset-based pagination page number. Null when the search was cursor-based."),
    )
    page_size = serializers.IntegerField()
    returned = serializers.IntegerField(help_text="Number of hits in this page.")
    has_more = serializers.BooleanField(
        help_text="True if more hits exist beyond this page.",
    )
    next_cursor = serializers.ListField(
        child=serializers.JSONField(),
        allow_null=True,
        required=False,
        help_text=(
            "Sort values of the last hit on this page. Pass back as "
            "``cursor`` in the next request to fetch the following page."
        ),
    )
    hits = HitSerializer(many=True)
    facets = FacetsSerializer(
        allow_null=True,
        required=False,
        help_text="Present only when the request set ``include_facets`` to true.",
    )


# ---------------------------------------------------------------------------
# Suggest response
# ---------------------------------------------------------------------------
class SuggestResponseSerializer(serializers.Serializer):
    """Response body of ``GET /api/suggest/``."""

    prefix = serializers.CharField(help_text="The prefix that was searched.")
    suggestions = serializers.ListField(
        child=serializers.CharField(),
        help_text="Full product names that matched the prefix.",
    )


# ---------------------------------------------------------------------------
# Explain response
# ---------------------------------------------------------------------------
class ExplainResponseSerializer(serializers.Serializer):
    """
    Response body of ``POST /api/explain/``.

    The ``explanation`` field is a recursive JSON object whose shape is
    defined by the domain's ``ScoreExplanation`` value object (Phase 16
    section 4.1). The API does not re-declare the recursion in its
    schema; the domain tests own that contract.
    """

    matched = serializers.BooleanField(
        help_text="True if the document matched the query.",
    )
    explanation = serializers.DictField(
        allow_null=True,
        help_text=(
            "The scoring breakdown tree, or null when the document did "
            "not match. See docs/21-explainability.md."
        ),
    )


# ---------------------------------------------------------------------------
# Health response
# ---------------------------------------------------------------------------
class ClusterHealthSerializer(serializers.Serializer):
    """Cluster-level health information."""

    name = serializers.CharField()
    status = serializers.CharField()
    number_of_nodes = serializers.IntegerField()


class IndexHealthSerializer(serializers.Serializer):
    """Index-level health information."""

    alias = serializers.CharField(help_text="The alias all searches go through.")
    points_at = serializers.CharField(
        allow_null=True,
        help_text=(
            "The physical index the alias currently resolves to. Null "
            "if the alias does not exist yet."
        ),
    )
    document_count = serializers.IntegerField(
        help_text="Number of documents in the index the alias points at.",
    )


class HealthResponseSerializer(serializers.Serializer):
    """Response body of ``GET /api/health/``."""

    status = serializers.ChoiceField(choices=["healthy", "degraded", "unhealthy"])
    cluster = ClusterHealthSerializer()
    index = IndexHealthSerializer()


# ---------------------------------------------------------------------------
# Service root
# ---------------------------------------------------------------------------
class ServiceRootResponseSerializer(serializers.Serializer):
    """Response shape of the service-root endpoint."""

    service = serializers.CharField(help_text="Service identifier.")
    status = serializers.ChoiceField(
        choices=["healthy", "degraded"],
        help_text="Coarse service state derived from backend reachability.",
    )


# ---------------------------------------------------------------------------
# Error response (common shape)
# ---------------------------------------------------------------------------
class ApiErrorDetailSerializer(serializers.Serializer):
    """
    The inner ``error`` object of every error response.

    Attributes:
        code: Stable identifier the caller branches on.
        message: Human-readable description.
        details: Optional structured context. Absent when there is none.
    """

    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField(required=False)


class ApiErrorSerializer(serializers.Serializer):
    """
    The response body of every API error.

    See docs/24-search-api.md section 7 and docs/25-openapi.md section 5.
    """

    error = ApiErrorDetailSerializer()
