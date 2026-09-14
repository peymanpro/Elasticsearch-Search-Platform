# Observability

## 1. Purpose

This document records how the platform emits information about its own
behavior. It covers the roadmap sub-phases:

    * 24.1 -- Structured logging
    * 24.2 -- Search duration
    * 24.3 -- Indexing metrics
    * 24.4 -- Correlation ID

The platform has no metrics server, no tracing backend, and no
dashboard. It logs to stdout. The design goal is that every event an
operator would want to see is one structured log line, and every log
line related to a single request carries the same correlation ID.

## 2. What "Structured" Means Here

A structured log line has:

* A **timestamp** (added by the logging framework).
* A **level** (`INFO`, `WARNING`, `ERROR`).
* A **logger name** -- the module that emitted the event.
* A **correlation ID** -- a per-request identifier.
* A **message** in the form `event_type=value key1=value1 key2=value2`.

The message format is not JSON. It is key=value pairs separated by
spaces, which is what a human reads easily in a terminal and what a
log processor can parse with a small regex. JSON was considered and
rejected: on a terminal it is harder to scan, and the platform does
not have a log processor that would benefit from the structure.

Every log line emitted by the platform's own modules follows this
convention. Third-party libraries (Django, elastic-transport) emit
their own formats; the platform does not attempt to normalize them.

## 3. Structured Logging (24.1)

### 3.1 The events

The platform emits the following events. Every one follows the
key=value format.

| Logger | Level | Event | Fields |
|---|---|---|---|
| `apps.search.presentation.middleware` | INFO | `request.start` | method, path, correlation_id |
| `apps.search.presentation.middleware` | INFO | `request.end` | method, path, status, duration_ms, correlation_id |
| `apps.search.application.search_products` | INFO | `search.executed` | query_len, total, returned, duration_ms, correlation_id |
| `apps.search.application.search_products` | WARNING | `search.slow` | duration_ms, threshold_ms, correlation_id |
| `apps.search.infrastructure.bulk_indexer` | INFO | `bulk.indexed` | documents, succeeded, failed, duration_ms |
| `apps.search.infrastructure.bulk_indexer` | WARNING | `bulk.retrying` | attempt, max_attempts, delay_s, error |
| `apps.search.infrastructure.bulk_indexer` | ERROR | `bulk.exhausted` | attempts, error |

### 3.2 What is deliberately not logged

* **Query text.** A user's search query can contain arbitrary content
  and, in a production system, could contain PII. The platform logs
  the query's length, not its content.
* **Document source.** Logging full documents would dwarf the
  operational signal and could leak data.
* **HTTP headers.** No headers are logged, not even the ones the
  platform reads.
* **Exception tracebacks by default.** A traceback is emitted only at
  the `ERROR` level and only when the exception is not otherwise
  classified. Classified failures (Section 5) log a one-line
  description, not a stack.

## 4. Search Duration (24.2)

### 4.1 What is measured

Every application-layer use case that performs a search measures the
elapsed wall-clock time from the start of `execute` to the return of
the result. The duration is reported in milliseconds as
`duration_ms` on the log line.

### 4.2 Where the measurement lives

The measurement lives in the use case, not in the view and not in the
gateway. Reasons:

* The **view** also measures total HTTP time, which includes
  serialization, DRF validation, and response rendering. That is a
  different number and it is not the platform's search cost.
* The **gateway** measures only the Elasticsearch round trip. That
  excludes the query composition and result translation the platform
  performs, which are part of the search cost the platform should be
  aware of.

The use case boundary is the natural measure of "how long did the
platform take to answer this search."

### 4.3 The slow threshold

A search that exceeds a threshold is logged at WARNING in addition to
INFO. The threshold is a module-level constant in the use case
module: **500 ms**. The value is chosen because a search slower than
half a second is noticeable to a user and worth flagging even if it
did not time out. It is not tuned, and it is exposed as a constant so
that a deployment with a different latency budget can adjust it in
one place.

## 5. Indexing Metrics (24.3)

### 5.1 What is logged

The bulk indexer logs one line at the end of each `index_documents`
or `delete_documents` call:

    bulk.indexed documents=1000 succeeded=1000 failed=0 duration_ms=273

Per-batch events are not logged by default. A batch is an internal
chunking detail; the caller cares about the whole operation.

### 5.2 What is not logged

* **Per-document events.** Even at failure, a per-document line per
  failed item would flood the log for a large dataset with a
  systematic mapping problem.
* **The `IndexingFailure` details.** Failures are reported to the
  caller through the `IndexingResult`. If the caller wants them
  logged, the caller logs them. The indexer logs the count, not the
  list.

### 5.3 Retry events

When the indexer retries a batch, it logs a `bulk.retrying` line at
WARNING with the attempt number and the delay. This is the only
per-batch event that is logged, and only when the retry path is
triggered. A successful batch without retries produces no
per-batch log line.

## 6. Correlation ID (24.4)

### 6.1 What it is

A correlation ID is a string that identifies one HTTP request. Every
log line emitted while the request is being served carries the same
ID. When a user reports "my search failed at 14:32", the operator
filters the logs by the ID and sees only the events for that request.

### 6.2 Where it comes from

If the incoming request has an `X-Correlation-ID` header, its value
is used. This lets an upstream proxy or load balancer assign the ID,
so a single request can be traced across services.

If the header is absent, the middleware generates one: a UUID4 in
string form. The platform is not the source of truth for the ID; it
is a producer of last resort.

### 6.3 How it propagates

The middleware stores the ID in a `contextvars.ContextVar`. Every
other component reads it through
`apps.search.presentation.correlation.get_correlation_id()`.

`contextvars` is the right tool because:

* It is per-request. Two concurrent requests do not see each other's
  IDs.
* It is process-safe without any lock.
* It survives across the sync/async boundary that Django's middleware
  chain uses.

The `ContextVar` is set by the middleware, read by every log
emitter, and reset when the request finishes. If a component reads
it outside a request context -- a management command, a test that
calls a use case directly -- the getter returns `"-"`, a sentinel
that means "no correlation ID in scope". The getter does not raise,
because a management command or a unit test is a legitimate caller
that simply has no HTTP request to attach an ID to.

### 6.4 What is not done with it

* **Not returned in the response headers.** The platform could echo
  the correlation ID back so a client could log it, and a production
  system usually does. It is a small change. It is not done here
  because the platform's callers are curl and Swagger UI, neither of
  which does anything useful with a response header.
* **Not propagated to Elasticsearch.** The platform does not send
  the correlation ID to Elasticsearch as a request header. Doing so
  would enable correlation in the cluster's own logs, which is
  valuable at production scale but not needed here.
* **Not stored anywhere except the log lines.** There is no
  correlation-ID index, no tracing store. The log lines are the
  store.

## 7. Log Format and Destination

### 7.1 The format

The Django logging configuration sets the formatter for the console
handler. Phase 24 changes it to include the correlation ID:

    %(asctime)s %(levelname)s [%(correlation_id)s] %(name)s %(message)s

A line looks like:

    2026-09-14 21:45:01,234 INFO [3f2b8a1c] apps.search.presentation.middleware request.end method=POST path=/api/search/ status=200 duration_ms=52

The `[correlation_id]` field is injected by a logging filter (Section
8) that reads the contextvar. If there is no correlation ID in scope,
the filter substitutes `-`.

### 7.2 The destination

Stdout. Docker captures it; the development shell prints it. No file
handler, no rotation, no aggregation. A production deployment would
add a log shipper; that is out of scope (Section 9).

## 8. The Logging Filter

A Django logging filter named `CorrelationIdFilter` reads
`get_correlation_id()` and puts the result on the log record as
`record.correlation_id`. The filter is attached to every handler
that formats log lines, so every emitted line has the field
available.

The filter has one purpose and no configuration. If there is no
correlation ID, it substitutes the sentinel `-`.

## 9. What is Deliberately Not Done

* **Metrics endpoint (Prometheus, StatsD).** No metrics server, no
  counter export. The log lines are the metrics surface.
* **Distributed tracing (OpenTelemetry, Jaeger).** The correlation
  ID is not a span; it is a request label. A tracing integration
  would be a different project.
* **Log aggregation (ELK, Loki).** No log shipper, no index for
  logs.
* **Application Performance Monitoring.** No APM agent.
* **Alerting.** No alert rules. A log line that says
  `bulk.exhausted` is not turned into a page.
* **Audit log.** The platform does not log who did what; there is no
  authentication (docs/02-non-goals.md section 2.1).

## 10. Testing

The observability layer is tested by:

1. **Unit tests for the correlation ID middleware.** A synthetic
   request with and without the `X-Correlation-ID` header. Assert
   the value is stored, retrieved, and reset. Assert the sentinel
   `-` is returned when no request is in scope.
2. **Unit tests for the logging filter.** A log record passed
   through the filter, with and without a correlation ID in scope.
3. **Integration test that a search request produces the expected
   log lines.** Assert that a `request.start`, a `search.executed`,
   and a `request.end` line are emitted, and that all three carry
   the same correlation ID.

These tests use `pytest`'s `caplog` fixture, which captures log
records from the running process without any handler configuration.

## 11. Rule for Changing Observability

A new log event, a change to the format, a change to the correlation
ID mechanism, or a new metric is a change to this document and to the
code, in the same commit. A log line that is not documented here is
not part of the platform's observability surface.
