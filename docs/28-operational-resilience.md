# Operational Resilience

## 1. Purpose

This document records how the platform behaves when Elasticsearch is
slow, unavailable, or missing an index, and what the platform
deliberately does not attempt to do. It covers the roadmap
sub-phases:

    * 23.1 -- Connection management
    * 23.2 -- Timeout handling
    * 23.3 -- Retry handling
    * 23.4 -- Elasticsearch unavailable
    * 23.5 -- Missing index
    * 23.6 -- Bulk failure recovery

The document is written against the code that exists. Where a
capability is provided by the Elasticsearch client's transport layer
rather than by the platform's own code, the document says so.

## 2. Connection Management (23.1)

### 2.1 What exists

Every infrastructure adapter obtains its client from
`infrastructure.elasticsearch.client.get_client`. The function:

* Is cached with `functools.lru_cache(maxsize=1)`, so one client
  instance exists per process and its underlying HTTP connection pool
  is reused across requests.
* Reads its configuration from `ElasticsearchSettings.from_env()`,
  which parses environment variables with sensible defaults.
* Logs the URL it is configured to connect to at INFO level and
  warns when credentials are only partially configured.

### 2.2 Configuration surface

| Environment variable | Default | Effect |
|---|---|---|
| `ELASTICSEARCH_URL` | `http://localhost:9200` | Cluster endpoint |
| `ELASTICSEARCH_USERNAME` | (unset) | Basic auth user (requires password) |
| `ELASTICSEARCH_PASSWORD` | (unset) | Basic auth password (requires user) |
| `ELASTICSEARCH_TIMEOUT` | `10.0` | Per-request timeout, seconds |
| `ELASTICSEARCH_MAX_RETRIES` | `3` | Transport-level retry count |

### 2.3 What is not attempted

* **Connection pooling is not tuned.** The client's default pool
  (10 connections) is used. On the platform's single-node
  environment this is more than sufficient.
* **Sniffing is not enabled.** The client is configured with a fixed
  host list. Sniffing would allow the client to discover nodes, but
  the platform has one node.
* **Health-check-before-request is not performed.** A search is sent
  to the cluster directly. If the cluster is down, the request fails
  and the failure is handled by Section 5.

## 3. Timeout Handling (23.2)

### 3.1 What exists

The client is constructed with `request_timeout=settings.timeout`
(default 10 seconds). This is the timeout for a single HTTP round
trip, applied by the `elastic-transport` layer.

When a request exceeds the timeout, the transport raises
`elastic_transport.ConnectionTimeout`. That exception propagates up
through the adapter, through the use case, and to the presentation
layer, where the exception handler (see Section 5) translates it
into an HTTP 504 response with the shaped error body:

    {
      "error": {
        "code": "backend_timeout",
        "message": "the search backend timed out"
      }
    }

### 3.2 What is not attempted

* **Per-query timeouts.** All queries use the same timeout. A
  distinction between "this autocomplete must return in 100 ms" and
  "this faceted search may take 2 seconds" would be a real feature,
  but the platform has no request profiles and no evidence that one
  is needed at this scale.
* **Timeout budget in the application.** A slow query that takes 9.9
  seconds and returns is treated as a success. The timeout is the
  only bound on the request duration.

## 4. Retry Handling (23.3)

### 4.1 What exists

There are two retry mechanisms in play.

**Transport-level retry (from `elastic-transport`).** The client is
constructed with `max_retries=settings.max_retries` (default 3).
When a request fails with a *connection* error ? the socket could
not be established, the peer reset the connection, a DNS failure ?
the transport silently retries the request up to `max_retries`
times before propagating the failure.

This covers the class of transient failures that the client library
is best positioned to handle: the network being briefly uncooperative
in a way that does not involve the server itself.

**Application-level retry for bulk indexing.** The bulk indexer
(`apps/search/infrastructure/bulk_indexer.py`) implements its own
retry on top of the transport's:

* It catches `TransportError` and `TransportConnectionError` from
  `elastic_transport`.
* It retries only when the error is classified as transient. A
  transient error is either:
  * a `ConnectionError` (network-level), or
  * a `TransportError` whose HTTP status is one of 429, 502, 503,
    504.
* The retry policy is bounded: three attempts, with exponential
  backoff starting at 0.5 seconds and doubling between attempts
  (0.5s, 1.0s).
* If the third attempt fails, the final exception propagates.

The bulk indexer performs this retry at the **batch** level, not the
item level. A batch that failed wholesale is retried as a whole.
Individual failed items within a successful batch response are not
retried; they are reported through `IndexingResult.failures`.

### 4.2 Why two mechanisms

The transport's retry handles the "socket was briefly bad" case at
the lowest possible layer, with the least overhead.

The bulk indexer's retry handles the "server is overloaded" case,
which manifests as an HTTP 429 or 503 ? a well-formed response, not
a connection failure, and therefore not covered by the transport's
retry.

The two mechanisms are complementary, not redundant.

### 4.3 What is not attempted

* **Search-level retry.** A search that fails with a 503 does not
  get a retry at the application layer. It relies on the transport's
  retry for connection failures and returns a 503 for server-level
  failures. The reasoning: a search is a user-facing request, and
  making the user wait through a retry is usually worse than
  returning an error the UI can handle. A background reindex
  operation is different ? there is no user waiting, and the work
  is expensive to redo ? which is why it retries and search does
  not.
* **Circuit breaker.** The platform does not implement a
  circuit-breaker pattern that stops issuing requests to a known-bad
  cluster. The transport's retry plus the client's timeouts are
  considered sufficient at the platform's scale. A production
  system under real traffic would benefit from a circuit breaker;
  the platform does not have enough concurrent load for the state
  machine to be meaningful.
* **Item-level bulk retry.** After a batch is reported as
  successful-with-failures, the failed items are not automatically
  retried. The `IndexingResult` carries enough information for a
  caller to compose a retry, but the platform does not do so
  automatically because most item failures (mapping violations,
  malformed documents) are permanent and would fail again.

## 5. Elasticsearch Unavailable (23.4)

### 5.1 What exists

When Elasticsearch is not reachable, the transport raises a
`TransportConnectionError` (or a `ConnectionTimeout` if the endpoint
accepts the connection but does not respond). The presentation
layer's exception handler
(`apps/search/presentation/exception_handler.py`) translates these
into shaped HTTP responses:

| Exception type | HTTP status | Error code |
|---|---|---|
| `ConnectionTimeout` | 504 | `backend_timeout` |
| `TransportConnectionError` | 503 | `backend_unavailable` |
| `ElasticsearchNotFoundError` | 503 | `backend_unavailable` |
| Any other `TransportError` | 503 | `backend_unavailable` |

The health endpoint is the exception: it does not raise when the
cluster is unreachable. It returns HTTP 200 with a body describing
the situation:

    {
      "status": "unhealthy",
      "cluster": {"status": "unreachable", "number_of_nodes": 0},
      "index": {"alias": "products", "points_at": null, "document_count": 0}
    }

The reason: a load balancer needs to know whether the service is up
(HTTP status) and whether it can serve searches (JSON body). The
two are different questions.

### 5.2 What is tested

The behavior in Section 5.1 is exercised by
`tests/integration/test_failure_handling.py`, which patches the
client's method to raise each of the exception types and asserts
the resulting HTTP status and body shape.

## 6. Missing Index (23.5)

### 6.1 What exists

If the `products` alias does not resolve ? because the index has not
been created, or the alias was deleted, or a reindex was interrupted
before the alias switch ? a search request returns an
`ElasticsearchNotFoundError` from the client.

The exception handler maps this to the same 503 / `backend_unavailable`
response as a connection failure, with a distinct message:
`"the search backend reports the target index as missing"`.

The distinction between "connection failed" and "index missing" is
deliberately preserved in the message even though both produce a
503. A monitoring system can grep the message; a caller who only
reads the code sees the same class of failure ("the backend cannot
serve this request right now").

### 6.2 What is tested

Covered by `test_search_against_nonexistent_index_returns_503` in
`tests/integration/test_failure_handling.py`.

## 7. Bulk Failure Recovery (23.6)

### 7.1 What exists

The bulk indexer handles failure at two levels.

**Batch-level failure.** If a bulk request itself fails (the HTTP
call returns an error, or the connection drops), and the error is
classified as transient, the batch is retried under the policy in
Section 4.1. A batch that ultimately fails after all retries raises;
it is not silently dropped.

**Item-level failure.** If the bulk request succeeds but some items
within it failed (a mapping violation, an invalid document), the
response is parsed by `_parse_bulk_response`. Each failed item
becomes an `IndexingFailure` with the document id, the failure
reason, and the HTTP status Elasticsearch assigned to that item.
The overall `IndexingResult` reports the counts and the failures.

The indexer does not lose the successful items in a partially-failed
batch. Nor does it retry the failed items; they are reported.

### 7.2 What the caller can do with failures

The `IndexingResult` gives the caller everything needed to decide:

* `result.is_fully_successful` ? a quick check.
* `result.failures` ? a tuple of `IndexingFailure`, each carrying
  enough information to log or to build a retry of just those
  documents.

The reindex service (Phase 18) uses this: if any item failed, the
reindex validation fails and the alias is not switched.

### 7.3 What is tested

* Item-level failure reporting is tested in
  `tests/unit/test_bulk_indexer.py` and
  `tests/integration/test_bulk_indexing.py`.
* Batch-level retry behavior is tested in
  `tests/unit/test_bulk_indexer_retry.py` (added in Phase 23).
* The reindex validation's behavior on failure is tested in
  `tests/integration/test_reindex.py`.

## 8. What is Not Attempted

This is a list of resilience features the platform deliberately does
not have. Each is a real feature in a production system; each is out
of scope here.

* **Circuit breaker.** No state machine to stop issuing requests to
  a known-unhealthy cluster.
* **Bulkhead isolation.** No thread pool per endpoint class; all
  work runs in the request thread.
* **Request hedging.** No send-two-requests-take-the-first strategy.
* **Search-level retry.** See Section 4.3.
* **Item-level bulk retry.** See Section 4.3.
* **Cross-cluster failover.** One cluster, one endpoint.
* **Rate limiting.** No concurrency limit on outgoing requests to
  Elasticsearch.
* **Graceful degradation to a cached result set.** The platform
  has no cache and does not serve stale results.

Each of these would be a project in its own right. The platform's
resilience story is: fail clearly, fail distinguishably, do not lose
data on a batch failure, and report enough for the caller to decide
what to do next.

## 9. Rule for Changing Resilience

A change to retry policy, timeout configuration, exception
translation, or the recovery strategy for a failure mode is a change
to this document and to the code, in the same commit. A new failure
mode that is not mentioned here is not covered by the platform's
resilience story.
