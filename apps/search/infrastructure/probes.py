"""
Infrastructure probes.

**Temporary placeholder.**

Phase 2.2 wires the use case to a stub so that the flow
``presentation -> application -> domain <- infrastructure`` is complete and
testable end-to-end. The stub does not touch Elasticsearch. In Phase 2.4
this module will gain ``ElasticsearchClusterHealthProbe``, which will
delegate to the managed client created in Phase 1.4
(``infrastructure.elasticsearch.client``) and the stub will be removed.
"""

from __future__ import annotations


class StubClusterHealthProbe:
    """
    Placeholder probe that always reports the backend as unreachable.

    Replace in Phase 2.4 with an adapter backed by the real Elasticsearch
    client. The class is intentionally simple and has no dependencies.
    """

    def is_reachable(self) -> bool:
        return False
