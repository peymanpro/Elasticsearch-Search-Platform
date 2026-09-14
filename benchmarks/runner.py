"""
Benchmark runner.

Measures search latency, autocomplete latency, bulk indexing throughput,
and (optionally) reindex duration against a live Elasticsearch cluster.
The runner does not go through the API layer; it issues Elasticsearch
requests directly, because the API adds a fixed overhead the benchmark
is not trying to measure.

Usage:

    python benchmarks/runner.py --dataset data/products.jsonl --iterations 100
    python benchmarks/runner.py --dataset data/generated/products-1k.jsonl --iterations 50

Results are written to benchmarks/results/ (gitignored) as a JSON file
and a human-readable markdown summary. The same summary is printed to
stdout.

See docs/27-benchmarking.md.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Load .env so the Elasticsearch client uses the same configuration the
# application does. This must happen before importing the client.
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
# When this file is executed directly (python benchmarks/runner.py),
# Python puts the script's directory at sys.path[0] rather than the
# repository root. The application packages (apps, infrastructure) are
# only importable if the repository root is on sys.path. The bootstrap
# below adds it, so that both invocation styles work:
#
#     python benchmarks/runner.py ...
#     python -m benchmarks.runner ...
#
# When invoked with -m, the repository root is already on sys.path
# and the insert is a harmless no-op.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


from apps.search.domain.product_document import ProductDocument  # noqa: E402
from apps.search.infrastructure.bulk_indexer import ElasticsearchBulkIndexer  # noqa: E402
from benchmarks.workload import AUTOCOMPLETE_PREFIX, WORKLOAD, BenchmarkQuery  # noqa: E402
from infrastructure.elasticsearch.client import get_client  # noqa: E402
from infrastructure.elasticsearch.indices import load_mapping, load_settings  # noqa: E402

BENCHMARK_INDEX = "products-benchmark"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ---------------------------------------------------------------------------
# Result value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class LatencyStats:
    """Distribution of a set of latency measurements, in milliseconds."""

    samples: int
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float
    p95_ms: float
    p99_ms: float
    stdev_ms: float


@dataclass(frozen=True, slots=True)
class ThroughputStats:
    """Throughput of a bulk operation."""

    documents: int
    total_seconds: float
    documents_per_second: float


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """The complete result of one benchmark run."""

    generated_at: str
    dataset_path: str
    dataset_size: int
    iterations: int
    warmup: int
    environment: dict[str, str]
    search_latencies: dict[str, LatencyStats]
    autocomplete_latency: LatencyStats
    indexing: ThroughputStats
    reindex_seconds: float | None


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------
def _percentile(sorted_values: list[float], p: float) -> float:
    """
    Nearest-rank percentile.

    Chosen over an interpolating method because the sample sizes here
    are small (tens to hundreds of iterations) and the nearest-rank
    method's output is trivially explainable: "the p95 is the value at
    or below which 95% of the samples fall, using the sorted sample
    nearest to that position."
    """
    if not sorted_values:
        return 0.0
    idx = int(round((len(sorted_values) - 1) * p / 100))
    return sorted_values[idx]


def _latency_stats(latencies_ms: list[float]) -> LatencyStats:
    """Compute the summary statistics for a set of latencies."""
    if not latencies_ms:
        return LatencyStats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    sorted_ms = sorted(latencies_ms)
    return LatencyStats(
        samples=len(sorted_ms),
        min_ms=sorted_ms[0],
        max_ms=sorted_ms[-1],
        mean_ms=statistics.fmean(sorted_ms),
        median_ms=_percentile(sorted_ms, 50),
        p95_ms=_percentile(sorted_ms, 95),
        p99_ms=_percentile(sorted_ms, 99),
        stdev_ms=statistics.pstdev(sorted_ms) if len(sorted_ms) > 1 else 0.0,
    )


def _measure_query(
    client,
    index: str,
    query: BenchmarkQuery,
    iterations: int,
    warmup: int,
) -> LatencyStats:
    """Run one query many times and return latency stats."""
    # The Elasticsearch 8.x client rejects mixing a ``body`` parameter
    # with specific parameters (``size``, ``aggs``, ``query``). The body
    # of a benchmark query therefore is spread directly into kwargs so
    # that every field reaches the client in its own named parameter.
    request: dict[str, Any] = {"index": index, "size": 20}
    request.update(query.body)

    # Warm-up: the first few requests pay connection setup and cache
    # effects. Excluding them keeps the measured set from being
    # dominated by startup noise.
    for _ in range(warmup):
        client.search(**request)

    latencies_ms: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        client.search(**request)
        latencies_ms.append((time.perf_counter() - started) * 1000.0)

    return _latency_stats(latencies_ms)


def _measure_autocomplete(
    client,
    index: str,
    prefix: str,
    iterations: int,
    warmup: int,
) -> LatencyStats:
    """Measure the autocomplete path against the search_as_you_type field."""
    request: dict[str, Any] = {
        "index": index,
        "size": 5,
        "query": {
            "multi_match": {
                "query": prefix,
                "type": "bool_prefix",
                "fields": [
                    "name_suggest",
                    "name_suggest._2gram",
                    "name_suggest._3gram",
                ],
            }
        },
    }

    for _ in range(warmup):
        client.search(**request)

    latencies_ms: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        client.search(**request)
        latencies_ms.append((time.perf_counter() - started) * 1000.0)

    return _latency_stats(latencies_ms)


def _measure_indexing(
    client,
    index: str,
    documents: list[ProductDocument],
    batch_size: int,
) -> ThroughputStats:
    """Measure bulk indexing throughput."""
    indexer = ElasticsearchBulkIndexer(
        client=client,
        index=index,
        batch_size=batch_size,
    )
    started = time.perf_counter()
    result = indexer.index_products(documents)
    elapsed = time.perf_counter() - started

    return ThroughputStats(
        documents=result.succeeded,
        total_seconds=elapsed,
        documents_per_second=(result.succeeded / elapsed) if elapsed > 0 else 0.0,
    )


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
def _load_dataset(path: Path) -> list[ProductDocument]:
    documents: list[ProductDocument] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            documents.append(ProductDocument.from_mapping(json.loads(stripped)))
    return documents


def _recreate_benchmark_index(client, version: str = "v2") -> None:
    """Delete and recreate the benchmark index with the version's definition."""
    client.indices.delete(index=BENCHMARK_INDEX, ignore_unavailable=True)
    settings = load_settings(version)
    mapping = load_mapping(version)
    client.indices.create(
        index=BENCHMARK_INDEX,
        settings=settings,
        mappings={
            "dynamic": mapping["dynamic"],
            "properties": mapping["properties"],
        },
    )


def _environment_facts() -> dict[str, str]:
    """Capture the environment the benchmark ran in."""
    client = get_client()
    try:
        info = client.info()
        es_version = info.get("version", {}).get("number", "unknown")
        cluster_name = info.get("cluster_name", "unknown")
    except Exception:
        es_version = "unreachable"
        cluster_name = "unreachable"

    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor() or "unknown",
        "cpu_count": str(os.cpu_count() or 0),
        "elasticsearch_version": es_version,
        "elasticsearch_cluster": cluster_name,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_benchmark(
    dataset_path: Path,
    iterations: int,
    warmup: int,
    batch_size: int,
) -> BenchmarkReport:
    """Run the whole benchmark and return the report."""
    client = get_client()

    print(f"Loading dataset from {dataset_path}")
    documents = _load_dataset(dataset_path)
    print(f"  loaded {len(documents)} documents")

    print(f"Recreating benchmark index {BENCHMARK_INDEX}")
    _recreate_benchmark_index(client)

    print(f"Indexing ({batch_size} per batch)")
    indexing = _measure_indexing(client, BENCHMARK_INDEX, documents, batch_size)
    print(
        f"  {indexing.documents} documents in {indexing.total_seconds:.2f}s "
        f"({indexing.documents_per_second:.0f} docs/s)"
    )

    client.indices.refresh(index=BENCHMARK_INDEX)

    print(f"Searching ({iterations} iterations, {warmup} warmup)")
    search_latencies: dict[str, LatencyStats] = {}
    for query in WORKLOAD:
        stats = _measure_query(client, BENCHMARK_INDEX, query, iterations, warmup)
        search_latencies[query.name] = stats
        print(
            f"  {query.name:20s} p50={stats.median_ms:6.2f}ms  "
            f"p95={stats.p95_ms:6.2f}ms  p99={stats.p99_ms:6.2f}ms"
        )

    print("Autocomplete")
    autocomplete_latency = _measure_autocomplete(
        client,
        BENCHMARK_INDEX,
        AUTOCOMPLETE_PREFIX,
        iterations,
        warmup,
    )
    print(
        f"  autocomplete        p50={autocomplete_latency.median_ms:6.2f}ms  "
        f"p95={autocomplete_latency.p95_ms:6.2f}ms  "
        f"p99={autocomplete_latency.p99_ms:6.2f}ms"
    )

    print("Done.")

    return BenchmarkReport(
        generated_at=datetime.now(UTC).isoformat(),
        dataset_path=str(dataset_path),
        dataset_size=len(documents),
        iterations=iterations,
        warmup=warmup,
        environment=_environment_facts(),
        search_latencies=search_latencies,
        autocomplete_latency=autocomplete_latency,
        indexing=indexing,
        reindex_seconds=None,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def write_report(report: BenchmarkReport) -> tuple[Path, Path]:
    """Write the report as JSON and as markdown; return the paths."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = RESULTS_DIR / f"benchmark-{stamp}.json"
    md_path = RESULTS_DIR / f"benchmark-{stamp}.md"

    json_path.write_text(
        json.dumps(asdict(report), indent=2),
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, md_path


def _render_markdown(report: BenchmarkReport) -> str:
    lines: list[str] = []
    lines.append("# Benchmark Report")
    lines.append("")
    lines.append(f"Generated at: {report.generated_at}")
    lines.append(f"Dataset: `{report.dataset_path}` ({report.dataset_size} documents)")
    lines.append(f"Iterations per query: {report.iterations}")
    lines.append(f"Warm-up iterations: {report.warmup}")
    lines.append("")
    lines.append("## Environment")
    lines.append("")
    for key, value in report.environment.items():
        lines.append(f"* **{key}**: {value}")
    lines.append("")
    lines.append("## Indexing throughput")
    lines.append("")
    lines.append(f"* {report.indexing.documents} documents in {report.indexing.total_seconds:.2f}s")
    lines.append(f"* Throughput: **{report.indexing.documents_per_second:.0f} docs/s**")
    lines.append("")
    lines.append("## Search latency (milliseconds)")
    lines.append("")
    lines.append("| Query | samples | min | median | mean | p95 | p99 | stdev |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for name, stats in report.search_latencies.items():
        lines.append(
            f"| {name} | {stats.samples} | {stats.min_ms:.2f} | "
            f"{stats.median_ms:.2f} | {stats.mean_ms:.2f} | "
            f"{stats.p95_ms:.2f} | {stats.p99_ms:.2f} | {stats.stdev_ms:.2f} |"
        )
    stats = report.autocomplete_latency
    lines.append(
        f"| autocomplete | {stats.samples} | {stats.min_ms:.2f} | "
        f"{stats.median_ms:.2f} | {stats.mean_ms:.2f} | "
        f"{stats.p95_ms:.2f} | {stats.p99_ms:.2f} | {stats.stdev_ms:.2f} |"
    )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "* All measurements are on a single Elasticsearch node running "
        "in Docker on the same machine as the benchmark runner."
    )
    lines.append("* Latency includes HTTP round-trip and client-side serialization.")
    lines.append("* The workload is defined in `benchmarks/workload.py`.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/products.jsonl"),
        help="JSONL dataset to load. Default: data/products.jsonl",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Measured iterations per query. Default: 100",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=10,
        help="Warmup iterations per query (not measured). Default: 10",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Bulk indexing batch size. Default: 500",
    )
    args = parser.parse_args()

    if not args.dataset.exists():
        print(f"dataset not found: {args.dataset}", file=sys.stderr)
        sys.exit(1)

    report = run_benchmark(
        dataset_path=args.dataset,
        iterations=args.iterations,
        warmup=args.warmup,
        batch_size=args.batch_size,
    )
    json_path, md_path = write_report(report)
    print("")
    print(f"JSON report : {json_path}")
    print(f"Markdown    : {md_path}")


if __name__ == "__main__":
    main()
