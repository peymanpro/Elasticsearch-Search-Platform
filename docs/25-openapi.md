# OpenAPI Documentation

## 1. Purpose

This document specifies how the platform documents its own HTTP
surface. It covers the roadmap sub-phases:

    * 20.1 -- Endpoint documentation
    * 20.2 -- Search examples
    * 20.3 -- Error documentation
    * 20.4 -- Search scenario collection

## 2. The Tooling

The platform uses `drf-spectacular` to generate the OpenAPI 3
schema. The schema is served at `/api/schema/` and rendered as
interactive documentation at `/api/docs/` (Swagger UI). Both
endpoints were added in Phase 1.5 and are exercised by the smoke
tests added there.

## 3. Endpoint Documentation (20.1)

### 3.1 What the schema carries

For every endpoint the schema documents:

* The HTTP method and path.
* The request body shape (for POST endpoints) or query parameters
  (for GET endpoints).
* The response shape.
* A human-readable description.
* The tag that groups endpoints in the UI.

Each view declares its schema through the `@extend_schema`
decorator from `drf_spectacular.utils`. The decorator names the
request and response serializers; drf-spectacular introspects them
to produce the schema components.

### 3.2 The tags

Two tags group the endpoints in the Swagger UI:

| Tag | Endpoints |
|---|---|
| service | `/`, `/api/health/` |
| search | `/api/search/`, `/api/suggest/`, `/api/explain/` |

The grouping is by *audience*: `service` endpoints are consumed
by infrastructure and monitoring; `search` endpoints are consumed
by application code.

## 4. Search Examples (20.2)

### 4.1 Why examples

A schema says what fields exist; an example says what a realistic
request looks like. Swagger UI's "Try it out" button uses the
first example the schema provides. Without one, the caller sees a
minimal skeleton that exercises none of the platform's features.

The platform declares a named example for each search endpoint.
The examples come from the project's own business scenarios
(docs/01-business-scenario.md, sections S1-S14), so they double as
a demonstration of what the platform is for.

### 4.2 The examples

Four examples are declared for `POST /api/search/`:

| Name | Demonstrates |
|---|---|
| simple | Text search with default pagination and relevance sort |
| filtered | Category + price range filter and sort by price |
| faceted | Text search with `include_facets` enabled |
| cursor | Cursor-based pagination of a paginated result set |

One example is declared for each of the other endpoints.

### 4.3 Why these four

The four search examples together exercise every feature the
endpoint supports. A reviewer who clicks through the Swagger UI
and tries each example has seen the entire search surface. This is
deliberate: the schema is the documentation, and the examples are
the demonstration.

## 5. Error Documentation (20.3)

### 5.1 The common error shape

Every error the platform returns uses the shape described in
docs/24-search-api.md section 7:

    {
      "error": {
        "code": "invalid_request",
        "message": "page must be >= 1, got 0",
        "details": {}
      }
    }

This shape is declared once as an OpenAPI component called
`ApiError`, and the endpoint schemas reference it. A generated
client can therefore produce a typed error class rather than a
stringly-typed blob.

### 5.2 Which endpoints declare errors

Every endpoint declares at least the 400 response. The search and
explain endpoints additionally declare 503 and 504, since they
depend on Elasticsearch being reachable and responsive.

The error declarations are documentation, not enforcement. The
actual response shape is produced by the exception handler
(apps/search/presentation/exception_handler.py). The two must
agree; the schema test in Section 7 asserts that they do.

## 6. Search Scenario Collection (20.4)

### 6.1 What it is

The examples attached to the search endpoint are drawn from a
fixed, curated collection that mirrors the project's business
scenarios. The collection is defined once, in a module the view
imports; the examples are referenced by name in the schema and
the same example bodies can be used by tests and by scripts.

### 6.2 Why a collection, not inline bodies

An inline example in a decorator is documented in one place and
forgotten. A collection is a fact about the platform: "these are
the queries we consider representative." Reviewing the collection
is a way to review what the platform claims to do.

The collection lives at
`apps/search/presentation/openapi_examples.py`. It exports a small
number of named constants, one per scenario. Views reference them
by name.

## 7. Testing

The tests verify:

1. **The schema generates.** A request to `/api/schema/` returns
   a 200 with a YAML or JSON body. This is tested in the existing
   `tests/test_openapi.py` and continues to pass.
2. **Every endpoint appears.** The generated schema contains
   entries for the paths the platform documents.
3. **Every example appears.** The generated schema contains the
   named examples for the search endpoint.
4. **The error shape is present.** The `ApiError` component is
   defined and referenced by every endpoint.

These tests are in `tests/unit/test_openapi_schema.py`, which uses
the DRF test client to fetch the schema and parses it with the
`yaml` module.

## 8. Rule for Changing the API Documentation

A new endpoint, a changed request shape, or a new example is a
change to this document and to the code, in the same commit. An
endpoint that is not documented in the schema is not part of the
platform's public surface.

