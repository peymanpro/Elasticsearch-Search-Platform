"""
Benchmark workload.

The workload is a fixed set of queries that exercises every search
path the platform offers. It exists so that a benchmark run produces a
report about a defined set of operations, not about an arbitrary
sample.

Each query is one of the concrete business scenarios from
docs/01-business-scenario.md. The queries are declared here rather
than inline in the runner so that a reviewer can read the workload
without reading the harness.

See docs/27-benchmarking.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BenchmarkQuery:
    """
    A single query the workload exercises.

    Attributes:
        name: A short label used in the report.
        body: The Elasticsearch query dictionary. This is the actual
            DSL the platform would issue; the benchmark does not go
            through the API layer, because the API adds a fixed,
            measurable overhead that the benchmark is not about.
        is_aggregation: True for the faceted query, which produces
            aggregations in addition to hits. Reported separately so
            that a reader can see the cost of aggregation.
    """

    name: str
    body: dict[str, Any]
    is_aggregation: bool = False


# The exact text of each query. Kept here as a constant so a reader can
# compare the workload against the business scenarios.
QUERY_TEXT_SIMPLE = "wireless headphones"
QUERY_TEXT_PHRASE = "wireless headphones"
QUERY_TEXT_TYPO = "wireles headphnes"
QUERY_TEXT_FACETED = "wireless"

# The Elasticsearch query bodies. These mirror what the platform's
# query composers produce: multi_match over the boosted field set,
# with optional fuzziness and optional aggregations.
WORKLOAD: tuple[BenchmarkQuery, ...] = (
    BenchmarkQuery(
        name="exact_match",
        body={
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": QUERY_TEXT_SIMPLE,
                                "fields": [
                                    "name^3.0",
                                    "brand^2.0",
                                    "category^1.5",
                                    "tags^1.5",
                                    "description^1.0",
                                ],
                            }
                        }
                    ]
                }
            }
        },
    ),
    BenchmarkQuery(
        name="phrase_match",
        body={
            "query": {
                "bool": {
                    "must": [
                        {
                            "match_phrase": {
                                "name": {
                                    "query": QUERY_TEXT_PHRASE,
                                }
                            }
                        }
                    ]
                }
            }
        },
    ),
    BenchmarkQuery(
        name="fuzzy_match",
        body={
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": QUERY_TEXT_TYPO,
                                "fields": [
                                    "name^3.0",
                                    "brand^2.0",
                                    "category^1.5",
                                    "tags^1.5",
                                    "description^1.0",
                                ],
                                "fuzziness": "AUTO",
                                "prefix_length": 2,
                            }
                        }
                    ]
                }
            }
        },
    ),
    BenchmarkQuery(
        name="faceted_search",
        body={
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": QUERY_TEXT_FACETED,
                                "fields": [
                                    "name^3.0",
                                    "brand^2.0",
                                    "category^1.5",
                                    "tags^1.5",
                                    "description^1.0",
                                ],
                            }
                        }
                    ]
                }
            },
            "aggs": {
                "categories": {"terms": {"field": "category.keyword", "size": 20}},
                "brands": {"terms": {"field": "brand.keyword", "size": 20}},
                "availability": {"terms": {"field": "availability", "size": 10}},
                "price_ranges": {
                    "range": {
                        "field": "price",
                        "ranges": [
                            {"key": "0-50", "to": 50.0},
                            {"key": "50-100", "from": 50.0, "to": 100.0},
                            {"key": "100-250", "from": 100.0, "to": 250.0},
                            {"key": "250-500", "from": 250.0, "to": 500.0},
                            {"key": "500+", "from": 500.0},
                        ],
                    }
                },
            },
        },
        is_aggregation=True,
    ),
)


AUTOCOMPLETE_PREFIX = "wire"


__all__ = [
    "AUTOCOMPLETE_PREFIX",
    "BenchmarkQuery",
    "QUERY_TEXT_FACETED",
    "QUERY_TEXT_PHRASE",
    "QUERY_TEXT_SIMPLE",
    "QUERY_TEXT_TYPO",
    "WORKLOAD",
]
