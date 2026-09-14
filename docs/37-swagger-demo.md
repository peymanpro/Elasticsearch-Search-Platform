# Swagger Demonstration

This document walks a reviewer through the Swagger UI shipped with
the platform and through the four curated search examples. It
records what each example demonstrates and the shape of the
response the reviewer should see.

The document is descriptive. It is not a replacement for
`docs/24-search-api.md` (the API contract) or `docs/25-openapi.md`
(the schema generation). It is the shortest path for a reviewer to
see the platform working end to end.

---

## 1. Opening Swagger UI

Prerequisites:

- Docker Desktop is running with the platform's Compose project up.
- Elasticsearch is reachable at `http://localhost:9200`.
- The Django development server is running.

Start the stack if it is not already running:

```powershell
docker compose up -d
python manage.py runserver
```

Then open:

- Swagger UI: http://localhost:8000/api/docs/
- Raw OpenAPI schema: http://localhost:8000/api/schema/

The UI lists every endpoint, grouped by tag:

- `service` — `/` and `/api/health/`.
- `search` — `/api/search/`, `/api/suggest/`, `/api/explain/`.

Every request body shown below is available in the "Examples"
dropdown of the relevant endpoint in Swagger UI. They are the same
objects declared in `apps/search/presentation/openapi_examples.py`.

---

## 2. Example 1 — Simple full-text search

Endpoint: `POST /api/search/`

Request body:

```json
{
  "query": "wireless headphones"
}
```

What it demonstrates:

- The default relevance ranking path (`SearchIntent.RELEVANT`).
- BM25 scoring combined with the field boosts documented in
  `docs/14-relevance.md`.
- Default pagination (`page=1`, default page size).

Expected response shape (abridged):

```json
{
  "query": "wireless headphones",
  "total": 42,
  "page": 1,
  "page_size": 20,
  "returned": 20,
  "has_more": true,
  "next_cursor": [4.21, "SKU-1001"],
  "hits": [
    {
      "id": "SKU-1001",
      "score": 4.21,
      "source": { "title": "...", "brand": "...", "category": "...", "price": 129.0 },
      "highlights": { "title": ["<em>wireless</em> <em>headphones</em>"] }
    }
  ]
}
```

Note: `facets` is absent because `include_facets` defaults to false.
`next_cursor` is present even for offset pagination, so a caller may
switch to cursor-based paging from a normal page.

---

## 3. Example 2 — Filtered search sorted by price

Endpoint: `POST /api/search/`

Request body:

```json
{
  "query": "monitor",
  "page": 1,
  "page_size": 10,
  "filters": {
    "category": "Electronics",
    "price_min": 100.0,
    "price_max": 500.0,
    "availability": "in_stock"
  },
  "sort": { "field": "price", "direction": "asc" }
}
```

What it demonstrates:

- The filter DSL (`docs/19-filtering-facets.md` section 3). Filters
  are applied in `filter` context, so they do not affect scoring.
- Business sorting with a stable tie-breaker
  (`docs/20-sorting-pagination.md` section 2.3).
- Offset-based pagination with `page` and `page_size`.

Expected response shape:

```json
{
  "query": "monitor",
  "total": 17,
  "page": 1,
  "page_size": 10,
  "returned": 10,
  "has_more": true,
  "hits": [ /* sorted by price ascending */ ]
}
```

Caveat: `page` and `cursor` are mutually exclusive. Supplying both
returns HTTP 400 with an explicit validation error.

---

## 4. Example 3 — Faceted search

Endpoint: `POST /api/search/`

Request body:

```json
{
  "query": "wireless",
  "page_size": 20,
  "include_facets": true
}
```

What it demonstrates:

- The aggregation path (`docs/19-filtering-facets.md` sections 4
  and 5). When `include_facets` is true, the request is served by
  the `SearchWithFacets` use case instead of the plain search use
  case.
- Faceted navigation: four facets are always computed together —
  `categories`, `brands`, `availability`, `price_ranges`.

Expected response shape:

```json
{
  "query": "wireless",
  "total": 88,
  "page": 1,
  "page_size": 20,
  "returned": 20,
  "has_more": true,
  "next_cursor": [3.77, "SKU-2042"],
  "hits": [ /* ... */ ],
  "facets": {
    "categories":   [ { "value": "Electronics",  "count": 61 }, { "value": "Accessories", "count": 27 } ],
    "brands":       [ { "value": "Acme",         "count": 33 }, { "value": "Globex",      "count": 21 } ],
    "availability": [ { "value": "in_stock",     "count": 72 }, { "value": "preorder",   "count": 16 } ],
    "price_ranges": [ { "value": "0-50",         "count": 12 }, { "value": "50-100",      "count": 40 } ]
  }
}
```

Note: the four facet keys are always present together when
`include_facets` is true. Buckets are ordered by count descending.

---

## 5. Example 4 — Cursor-based pagination

Endpoint: `POST /api/search/`

Request body (first call — plain search to obtain a cursor):

```json
{
  "query": "wireless",
  "page_size": 20
}
```

The response contains `next_cursor`, e.g. `[4.2, "SKU-1001"]`. Use
it verbatim in the follow-up request:

```json
{
  "query": "wireless",
  "page_size": 20,
  "cursor": [4.2, "SKU-1001"]
}
```

What it demonstrates:

- `search_after` cursor pagination
  (`docs/20-sorting-pagination.md` section 4).
- Stable iteration over a large result set. Cursor pagination does
  not suffer from the page-drift that offset pagination shows when
  the index changes between calls.

Expected response shape:

```json
{
  "query": "wireless",
  "total": 88,
  "page": null,
  "page_size": 20,
  "returned": 20,
  "has_more": true,
  "next_cursor": [3.9, "SKU-1063"],
  "hits": [ /* ... */ ]
}
```

Note: when the request is cursor-based, `page` is `null` in the
response. This is the documented signal that the response belongs
to a cursor-paginated sequence. Do not mix `page` and `cursor` in
the same request; the serializer rejects it with HTTP 400.

---

## 6. Other endpoints

### `GET /api/suggest/`

Query string parameters:

- `q` (required) — the prefix. Example: `headph`.
- `limit` (optional) — maximum number of suggestions. Example: `5`.

Expected response shape:

```json
{
  "prefix": "headph",
  "suggestions": [
    "Wireless Bluetooth Headphones",
    "Noise-Cancelling Over-Ear Headphones"
  ]
}
```

Suggestions are full product names, not raw completion tokens.

### `POST /api/explain/`

Request body:

```json
{
  "query": "wireless headphones",
  "document_id": "SKU-1001"
}
```

Expected response shape:

```json
{
  "matched": true,
  "explanation": {
    "value": 4.21,
    "description": "sum of:",
    "details": [
      { "value": 2.10, "description": "weight(title:wireless in 12) ...", "details": [] }
    ]
  }
}
```

If the document does not match the query, `matched` is `false` and
`explanation` is `null`. The tree is recursive; the domain value
object `ScoreExplanation` owns its contract
(`docs/21-explainability.md`).

### `GET /api/health/`

Expected response shape:

```json
{
  "status": "healthy",
  "cluster": { "name": "esp-node-01", "status": "green", "number_of_nodes": 1 },
  "index":   { "alias": "products", "points_at": "products-000001", "document_count": 5000 }
}
```

The HTTP status is always 200; the JSON body carries `healthy`,
`degraded`, or `unhealthy`.

---

## 7. Error responses

Every error response, regardless of endpoint, has the same shape:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "cursor and page are mutually exclusive; supply one or the other",
    "details": { }
  }
}
```

Status codes a reviewer may see:

| Code | Meaning                                                         |
|------|-----------------------------------------------------------------|
| 400  | Request failed validation (DRF or domain).                     |
| 503  | Elasticsearch is unreachable or returned an unretryable error.  |
| 504  | Elasticsearch did not respond within the configured timeout.    |

---

## 8. What this demonstrates

The four search examples together exercise the full search surface:

- The plain search path (BM25 + boosts).
- The filter + sort path.
- The facet aggregation path.
- The cursor pagination path.

The suggest and explain endpoints complete the picture: prefix
autocomplete and score inspection. A reviewer who runs all six
requests has seen every capability the platform exposes over HTTP.

