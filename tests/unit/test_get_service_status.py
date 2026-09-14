"""
Unit tests for the application use case ``GetServiceStatusUseCase``.

The use case is exercised against a test double that satisfies the domain
``ClusterHealthProbe`` Protocol. No Elasticsearch is contacted.
"""

from __future__ import annotations

from apps.search.application.get_service_status import SERVICE_NAME, GetServiceStatusUseCase
from apps.search.domain.service_status import ServiceState


class _ProbeStub:
    """Minimal test double implementing the ClusterHealthProbe Protocol."""

    def __init__(self, reachable: bool) -> None:
        self._reachable = reachable
        self.call_count = 0

    def is_reachable(self) -> bool:
        self.call_count += 1
        return self._reachable


def test_use_case_reports_healthy_when_probe_is_reachable() -> None:
    probe = _ProbeStub(reachable=True)
    use_case = GetServiceStatusUseCase(cluster_health_probe=probe)

    status = use_case.execute()

    assert status.service_name == SERVICE_NAME
    assert status.state is ServiceState.HEALTHY
    assert status.elasticsearch_reachable is True
    assert probe.call_count == 1


def test_use_case_reports_degraded_when_probe_is_unreachable() -> None:
    probe = _ProbeStub(reachable=False)
    use_case = GetServiceStatusUseCase(cluster_health_probe=probe)

    status = use_case.execute()

    assert status.state is ServiceState.DEGRADED
    assert status.elasticsearch_reachable is False


def test_use_case_does_not_depend_on_concrete_probe_class() -> None:
    # The use case must accept any object that satisfies the Protocol,
    # including a bare local class unrelated to the infrastructure package.
    class AnyProbe:
        def is_reachable(self) -> bool:
            return True

    status = GetServiceStatusUseCase(cluster_health_probe=AnyProbe()).execute()
    assert status.state is ServiceState.HEALTHY
