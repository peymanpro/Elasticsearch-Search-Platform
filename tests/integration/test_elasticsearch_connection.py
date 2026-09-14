"""
Integration tests against a real Elasticsearch cluster.

These tests require a running Elasticsearch. The stack is provided by
``docker-compose.yml`` at the repository root:

    docker compose up -d elasticsearch

When no cluster is reachable, the tests are skipped rather than failed,
so that ``pytest`` remains green in environments without Docker. When the
cluster is up, the tests actually exercise the real client path.

Run only the integration tests:

    pytest -m integration

Skip them explicitly:

    pytest -m "not integration"
"""

from __future__ import annotations

import pytest

from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.health import cluster_info, ping

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    """Skip the entire module when no cluster is reachable."""
    if not ping():
        pytest.skip(
            "Elasticsearch is not reachable; start it with `docker compose up -d elasticsearch`."
        )


def test_ping_returns_true_against_real_cluster() -> None:
    assert ping() is True


def test_cluster_info_returns_real_payload() -> None:
    info = cluster_info()
    assert "cluster_name" in info
    assert "version" in info
    assert "number" in info["version"]

    # The compose file pins the 8.15.x server version; assert the major series
    # so that a client/server skew is caught immediately.
    assert info["version"]["number"].startswith("8.")


def test_client_can_reach_the_cluster() -> None:
    # A raw call through the same client instance used by the application.
    health = get_client().cluster.health()
    assert health["status"] in {"green", "yellow", "red"}
    assert health["number_of_nodes"] >= 1
