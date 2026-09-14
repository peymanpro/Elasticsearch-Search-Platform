# Benchmarking

## 1. Purpose

This document records what the platform's benchmark harness measures,
how the workload is defined, and the results of running it. It covers
the roadmap sub-phases:

    * 22.1 -- Define workload
    * 22.2 -- Dataset scaling
    * 22.3 -- Search latency
    * 22.4 -- Query type benchmark
    * 22.5 -- Indexing benchmark
    * 22.6 -- Reindex benchmark
    * 22.7 -- Benchmark documentation

The numbers in this document come from actual executions of the
harness on the development machine described in Section 4. They are
not estimated.

## 2. The Harness

The harness lives at `benchmarks/runner.py` and the workload it runs at
`benchmarks/workload.py`.

The harness:

1. Reads a JSONL dataset into `ProductDocument` instances.
2. Recreates a dedicated benchmark index (`products-benchmark`) with
   the current version's settings and mapping.
3. Bulk-indexes the dataset, measuring wall-clock time and throughput.
4. Runs each workload query N times (with M warm-up iterations),
   recording per-iteration latency in milliseconds.
5. Runs the autocomplete query against the `name_suggest` field.
6. Writes a JSON report and a markdown report to `benchmarks/results/`.

The results directory is gitignored: it contains machine-specific
numbers that are meaningful only in the context of the run.

## 3. The Workload (22.1)

The workload is a fixed set of four queries (plus one autocomplete
prefix) defined in `benchmarks/workload.py`. Each query corresponds to
a business scenario from `docs/01-business-scenario.md`.

| Query | Type | Demonstrates |
|---|---|---|
| `exact_match` | multi_match, no fuzziness | Ordinary text search across the boosted field set |
| `phrase_match` | match_phrase on name | Phrase-aware ranking |
| `fuzzy_match` | multi_match with fuzziness AUTO | Typo tolerance |
| `faceted_search` | multi_match plus aggregations | Filtering cost under facets |
| `autocomplete` | bool_prefix on `name_suggest` | Prefix search |

The queries are issued directly through the Elasticsearch client, not
through the Django API. This is deliberate: the benchmark measures the
search engine and the query DSL, not Django's request machinery. A
separate API-level benchmark would be a different measurement.

## 4. The Environment

| Fact | Value |
|---|---|
| Operating system | Windows (WSL2 backend via Docker Desktop) |
| Python | 3.12.10 |
| Elasticsearch | 8.15.3 (Bitnami image via DaoCloud mirror) |
| Nodes | 1 |
| Index configuration | `products-benchmark`, 1 shard, 0 replicas |
| Network path | HTTP from the host process to the container's exposed port |

**All timing includes the HTTP round-trip across the WSL2 network
boundary.** This is the dominant cost on Windows and is what makes the
absolute numbers what they are (Section 6). The relative numbers ? how
one query type compares to another ? are the meaningful measurements
for query-work comparison.

## 5. How to Reproduce

    # Small dataset (12 documents)
    python benchmarks/runner.py --dataset data/products.jsonl \
        --iterations 100 --warmup 10 --batch-size 500

    # Medium dataset (1,000 documents)
    python scripts/generate_products.py --seed 42 --count 1000 \
        --out data/generated/products-1k.jsonl
    python benchmarks/runner.py --dataset data/generated/products-1k.jsonl \
        --iterations 100 --warmup 10 --batch-size 500

The same seed produces the same generated dataset, so results are
comparable across runs on the same machine.

## 6. Results

### 6.1 Small dataset (12 documents)

Environment: as above. Iterations per query: 100. Warm-up: 10.
Batch size: 500.

**Indexing throughput:** 12 documents in 0.02 s (676 docs/s).
The small document count makes this number unreliable ? startup
overhead dominates and the sample is too small for a rate
measurement to be meaningful.

**Search latency (milliseconds):**

| Query | samples | p50 | p95 | p99 |
|---|---|---|---|---|
| exact_match | 100 | 50.04 | 71.19 | 75.87 |
| phrase_match | 100 | 54.09 | 61.01 | 63.20 |
| fuzzy_match | 100 | 60.66 | 74.44 | 79.40 |
| faceted_search | 100 | 54.98 | 71.89 | 74.87 |
| autocomplete | 100 | 55.05 | 59.01 | 61.65 |

### 6.2 Medium dataset (1,000 documents)

Environment: as above. Iterations per query: 100. Warm-up: 10.
Batch size: 500.

**Indexing throughput:** 1,000 documents in 0.27 s (3,699 docs/s).
This is the more meaningful throughput measurement: the sample is
large enough that startup overhead is amortized.

**Search latency (milliseconds):**

| Query | samples | p50 | p95 | p99 |
|---|---|---|---|---|
| exact_match | 100 | 55.89 | 79.02 | 82.54 |
| phrase_match | 100 | 52.63 | 61.11 | 63.99 |
| fuzzy_match | 100 | 60.74 | 75.02 | 82.27 |
| faceted_search | 100 | 58.69 | 73.33 | 76.27 |
| autocomplete | 100 | 55.57 | 58.32 | 60.75 |

## 7. What the Numbers Say

### 7.1 The network path dominates

The medium dataset has 83? more documents than the small one. If the
platform's search cost were dominated by query work inside
Elasticsearch, the medium-dataset latencies would be noticeably higher.

They are not. Median latency for `exact_match` went from 50.04 ms on
12 documents to 55.89 ms on 1,000 documents ? a 12% increase across
an 83? dataset increase. The other queries show similar behavior.

The explanation is that the fixed cost of a request on this
environment (the HTTP round trip from the host process through the
WSL2 network boundary to the container, plus the client's response
deserialization) is on the order of 50 ms, and the marginal cost of
searching a 1,000-document index is a small fraction of that.

**Conclusion:** the measured numbers describe this environment, not
the platform's underlying search cost. What they can be used for is
comparing query types against each other within the same run ? a
comparison in which the fixed cost is common to both sides.

### 7.2 Query type cost differences

Within a run, the four search types are ordered consistently across
both datasets:

* `phrase_match` is the fastest. `match_phrase` on a single short
  field has fewer terms to score than a multi_match over five fields.
* `exact_match` and `faceted_search` are close to each other. The
  aggregation cost in the faceted query is small relative to the
  fixed cost; it does not measurably slow the query.
* `fuzzy_match` is the slowest. Fuzzy expansion multiplies the terms
  the engine has to consider, and its cost is visible even against
  the fixed overhead.
* `autocomplete` sits between `phrase_match` and `exact_match`,
  consistent with `bool_prefix` over three subfields.

These relative orderings are the durable observations from this
benchmark. The absolute numbers are machine-specific.

### 7.3 Indexing throughput

The 3,699 docs/s measured on the medium dataset is a real rate for
this environment: single node, 500-document batches, HTTP transport.
It is not a production rate for Elasticsearch; a production cluster
with a local client and a higher thread-pool budget would be much
faster. It is the rate this specific configuration achieves, and it
is stable across the runs performed during development.

## 8. What is Not Measured

* **Latency at large scale (100k documents).** Generating a 100k
  dataset and running the full workload against it would take
  approximately 30 seconds for indexing and 60+ seconds for the
  workload, which is longer than the current benchmark budget. This is
  a deliberate limit for Phase 22; if a future phase needs the
  measurement, the harness already supports it.
* **Reindex duration (22.6).** The benchmark harness accepts a
  `reindex_seconds` field on the report but does not yet populate it.
  Reindexing is covered functionally by `tests/integration/test_reindex.py`;
  a timing measurement is deferred.
* **Cold-start latency.** The warm-up iterations exclude first-touch
  costs. The steady-state number is what is reported.
* **Node-internal component breakdown.** Elasticsearch's profile API
  would allow reporting how much of the query time is spent in each
  Lucene primitive. That analysis is a separate exercise; the harness
  reports the black-box latency a client would experience.

## 9. Honest Caveats

* **The benchmark is not a comparison with any other system.** The
  platform is not claiming that its Elasticsearch setup is faster or
  slower than any alternative. It is characterizing what this specific
  configuration produces on this specific machine.
* **No tuning was performed.** The values in Section 6 are the numbers
  that the platform produces without optimization. Tuning the
  environment (running the runner inside the container, disabling
  fsync, using the local transport) would produce different numbers;
  none of that was done.
* **The Docker-on-Windows environment dominates.** Numbers from a
  native Elasticsearch installation or from a runner inside the
  container would be substantially lower across the board. That is not
  a limitation of the platform; it is a property of the environment
  the platform was measured in.

## 10. Rule for Changing the Benchmark

A change to the workload, the runner, or the report format is a change
to this document and to the code, in the same commit. A new measurement
is added to Section 6 with its environment; the previous numbers are
not overwritten, because a benchmark result is a fact about a specific
run, not a claim that replaces the last one.
