# Search API

## 1. Purpose

This document specifies the HTTP surface of the platform. It covers
the roadmap sub-phases:

    * 19.1 -- Product search endpoint
    * 19.2 -- Suggest endpoint
    * 19.3 -- Facet response
    * 19.4 -- Explain endpoint
    * 19.5 -- Reindex command
    * 19.6 -- Index health endpoint

Every endpoint in this document is a thin translation layer: it
validates an HTTP request, calls an application-layer use case, and
serializes the result. No endpoint contains search logic; no
endpoint talks to Elasticsearch directly.

## 2. The Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | /api/search/ | Search with text, filters, sort, facets, pagination |
| GET | /api/suggest/ | Autocomplete suggestions for a prefix |
| POST | /api/explain/ | Explain a (text, document_id) pair |
| GET | /api/health/ | Index and cluster health |
| (CLI) | manage.py reindex | Build a new index version and switch the alias |

The four HTTP endpoints share a common prefix and a common
response-error shape (Section 5).

The reindex operation is deliberately **not** an HTTP endpoint.
Section 8 explains why.

## 3. POST /api/search/

### 3.1 Request body

    {
      "query": "wireless headphones",
      "page": 1,
      "page_size": 20,
      "filters": {
        "category": "Electronics",
        "brand": "Sony",
        "availability": "in_stock",
        "price_min": 100.0,
        "price_max": 500.0,
        "rating_min": 4.0,
        "rating_max": 5.0
      },
      "sort": {
        "field": "price",
        "direction": "asc"
      },
      "include_facets": true
    }

All fields except `query` are optional. The default page is 1 with
20 items; the default sort is relevance descending; the default is
no facets.

### 3.2 Response body

    {
      "query": "wireless headphones",
      "total": 47,
      "page": 1,
      "page_size": 20,
      "returned": 20,
      "has_more": true,
      "next_cursor": [4.2, "SKU-1001"],
      "hits": [
        {
          "id": "SKU-1001",
          "score": 12.5,
          "source": { ... product document ... },
          "highlights": {
            "name": ["<em>Wireless</em> Noise-Cancelling Headphones"],
            "description": ["... <em>wireless</em> ..."]
          }
        },
        ...
      ],
      "facets": {
        "categories":   [{"value": "Electronics", "count": 30}, ...],
        "brands":       [{"value": "Sony", "count": 8}, ...],
        "availability": [{"value": "in_stock", "count": 40}, ...],
        "price_ranges": [{"value": "100-250", "count": 15}, ...]
      }
    }

`facets` is present only when the request sets `include_facets` to
true. When present, the facets are computed over the same filtered
result set as the hits (Phase 14 section 5).

### 3.3 Pagination modes

The request supports both pagination modes from Phase 15:

* **Offset-based.** Set `page` and optionally `page_size`. The
  response carries no cursor.
* **Cursor-based.** Set `page_size` and `cursor` (a list matching
  the previous response's `next_cursor`). The `page` field is
  ignored. The response carries the cursor for the next page.

When both are absent, the default is page 1, offset-based.

## 4. GET /api/suggest/

### 4.1 Request

    GET /api/suggest/?q=headph&limit=5

`q` is required and non-empty. `limit` is optional; the default is
5 and the maximum is 20 (see Phase 12 section 5).

### 4.2 Response

    {
      "prefix": "headph",
      "suggestions": [
        "Wireless Noise-Cancelling Headphones",
        "Wired Studio Headphones"
      ]
    }

Suggestions are the full product names that matched. The response
does not include scores, ranks, or document ids: an autocomplete
suggestion is a string, and the caller uses it as one.

## 5. POST /api/explain/

### 5.1 Request

    {
      "query": "wireless headphones",
      "document_id": "SKU-1001"
    }

### 5.2 Response

A matching document:

    {
      "matched": true,
      "explanation": {
        "value": 12.5,
        "description": "sum of",
        "details": [
          {
            "value": 7.5,
            "description": "weight(name:wireless ...)",
            "details": [...]
          },
          ...
        ]
      }
    }

A non-matching document:

    {
      "matched": false,
      "explanation": null
    }

The tree is preserved to whatever depth Elasticsearch returned it.
The domain object `ScoreExplanation` is recursive (Phase 16 section
4.1); the serializer recurses with it.

## 6. GET /api/health/

### 6.1 Response

    {
      "status": "healthy",
      "cluster": {
        "name": "esp-cluster",
        "status": "green",
        "number_of_nodes": 1
      },
      "index": {
        "alias": "products",
        "points_at": "products-v2",
        "document_count": 12
      }
    }

### 6.2 Status values

| Status | Meaning |
|---|---|
| healthy | The cluster is reachable, the alias resolves, and the index has documents |
| degraded | The cluster is reachable but something is off (alias missing, index empty, cluster red) |
| unhealthy | The cluster is not reachable |

### 6.3 Why this endpoint exists

A load balancer, a monitoring system, or a human needs to answer
"is the platform able to serve searches right now?" without
issuing a real search and interpreting the result. The health
endpoint answers the question directly.

It is distinct from the service-root endpoint at `/`, which
reports only the platform's own liveness. The health endpoint
reports the platform's ability to serve a specific class of
request.

## 7. Error Responses

### 7.1 The common shape

All API errors use a common JSON body:

    {
      "error": {
        "code": "invalid_request",
        "message": "page must be >= 1, got 0",
        "details": {}
      }
    }

`code` is a stable string an automated caller can branch on.
`message` is a human-readable description. `details` is an
optional object for structured context.

### 7.2 Error codes and HTTP statuses

| Code | HTTP | Raised when |
|---|---|---|
| invalid_request | 400 | A request field fails domain validation (empty query, page = 0, invalid sort field, ...) |
| not_found | 404 | The path does not exist. The explain endpoint does not use 404 for a non-matching document; that is a 200 with matched=false |
| backend_unavailable | 503 | Elasticsearch is unreachable |
| backend_timeout | 504 | Elasticsearch did not respond within the configured timeout |
| internal_error | 500 | Any unexpected failure |

Domain exceptions (`InvalidSearchQueryError`, `InvalidPaginationError`,
`InvalidFiltersError`, `InvalidSuggestQueryError`) are translated to
`invalid_request` with their message preserved. This is the boundary
where the domain stops speaking in exceptions and starts speaking
in HTTP codes.

## 8. The Reindex Command (19.5)

### 8.1 Why not an HTTP endpoint

A reindex operation:

* Reads an entire dataset from disk (potentially hundreds of
  thousands of documents).
* Creates a new physical index and bulk-indexes into it, taking
  seconds to minutes.
* Moves the alias that all queries depend on.
* Consumes significant cluster resources (CPU, heap, disk I/O).

Exposing this over HTTP would be wrong on several axes. An HTTP
endpoint implies a request/response cycle measured in seconds; a
reindex measured in minutes would time out at every reverse proxy.
An HTTP endpoint implies a caller that can retry; a reindex that
partially completed and was retried would collide with its own
half-created index. An HTTP endpoint implies a caller that the
platform can refuse; a reindex is a privilege operation, and the
platform has no authentication (docs/02-non-goals.md section 2.1).

### 8.2 The command

    python manage.py reindex --version v3 [--dataset data/products.jsonl]

The command:

1. Loads the dataset from the path (or the default).
2. Parses each line into a `ProductDocument`.
3. Calls the `ReindexService` (Phase 18).
4. Prints a report and exits with a nonzero code on failure.

### 8.3 A companion command

    python manage.py reindex_status

prints the alias target, the document count, and the count of
physical indices that exist for the products alias. Useful for
verifying a reindex succeeded, and for checking before an
operation whether a stale index is present.

Neither command is exposed over HTTP. The HTTP surface is
read-only.

## 9. Composition

### 9.1 Where the use cases are built

The composition root
(`apps/search/presentation/composition.py`) is the only place that
chooses concrete adapters and wires them into use cases. The
initial version of the file (Phase 3.2) built only the service
status use case. Phase 19 extends it with the four search-related
use cases:

    build_search_products_use_case()   -> SearchProductsUseCase
    build_search_with_facets_use_case() -> SearchWithFacetsUseCase
    build_get_suggestions_use_case()   -> GetSuggestionsUseCase
    build_explain_score_use_case()     -> ExplainScoreUseCase

### 9.2 Where the views live

Every search-related view lives in
`apps/search/presentation/views.py`. Every serializer for those
views lives in `apps/search/presentation/serializers.py`. Every
URL is registered in `apps/search/presentation/urls.py`.

The `config/urls.py` module continues to include the app's URL
configuration under the root prefix and to expose the OpenAPI
schema and the Swagger UI. It does not know the search endpoints
individually.

### 9.3 How errors are translated

A custom DRF exception handler (registered in settings) translates
domain exceptions to the error shape of Section 7. Without it, DRF
would return its own `{"detail": "..."}` shape, which does not
carry a code field and is therefore harder for callers to branch
on.

The handler is a single function that examines the exception type
and returns the shaped error. It does not contain business logic.

## 10. Testing

The tests exercise the HTTP surface through the DRF test client,
with a real Elasticsearch cluster behind it. Every endpoint has:

* A happy-path test (a request that succeeds and returns the
  expected shape).
* At least one validation test (a request that should be rejected
  at the DRF level, e.g. a missing required field).
* At least one domain-validation test (a request that passes DRF
  but violates a domain rule, e.g. `page=0`).

The tests are marked integration because they need the cluster.
They skip cleanly when none is reachable.

## 11. Rule for Changing the API

A change to a request shape, a response shape, an error code, or
a path is a change to this document and to the serializers, views,
and tests, in the same commit. The rule mirrors the other design
documents in this project.

