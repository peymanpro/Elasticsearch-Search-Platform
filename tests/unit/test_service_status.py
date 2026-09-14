"""
Unit tests for the domain value object ``ServiceStatus``.

Pure-Python tests. No Django, no DRF, no Elasticsearch. The domain layer
must be testable without any framework or external system.
"""

from __future__ import annotations

from apps.search.domain.service_status import ServiceState, ServiceStatus


def test_from_probe_marks_status_healthy_when_backend_reachable() -> None:
    status = ServiceStatus.from_probe(service_name="svc", elasticsearch_reachable=True)
    assert status.state is ServiceState.HEALTHY
    assert status.elasticsearch_reachable is True
    assert status.service_name == "svc"


def test_from_probe_marks_status_degraded_when_backend_unreachable() -> None:
    status = ServiceStatus.from_probe(service_name="svc", elasticsearch_reachable=False)
    assert status.state is ServiceState.DEGRADED
    assert status.elasticsearch_reachable is False


def test_service_status_is_immutable() -> None:
    status = ServiceStatus.from_probe(service_name="svc", elasticsearch_reachable=True)
    # frozen=True on the dataclass; attempting to mutate must fail.
    try:
        status.service_name = "other"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("ServiceStatus should be immutable")
