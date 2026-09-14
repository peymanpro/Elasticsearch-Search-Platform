"""
Elasticsearch client lifecycle.

Responsibilities of this module, and nothing else:

    * Build a single, process-wide Elasticsearch client from
      environment-driven settings.
    * Expose it through ``get_client()``.
    * Allow tests and configuration changes to discard the cached client
      via ``reset_client_cache()``.

Cluster-level helpers that ask the client questions -- reachability,
identity -- live in ``health.py``. Keeping them out of this module is a
deliberate Single Responsibility decision, recorded during Phase 3.1.

This module does not create indices, define mappings, or issue queries.
Those responsibilities belong to later phases.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from elasticsearch import Elasticsearch
from infrastructure.elasticsearch.config import ElasticsearchSettings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_client() -> Elasticsearch:
    """
    Return the process-wide Elasticsearch client.

    The client is created lazily on first call and cached for the lifetime
    of the process so that its underlying HTTP connection pool is reused.
    Creating the client does not open a network connection; the first
    request does.
    """
    settings = ElasticsearchSettings.from_env()

    basic_auth: tuple[str, str] | None = None
    if settings.username and settings.password:
        basic_auth = (settings.username, settings.password)
    elif settings.username or settings.password:
        logger.warning(
            "Elasticsearch credentials partially configured; "
            "both ELASTICSEARCH_USERNAME and ELASTICSEARCH_PASSWORD must be set. "
            "Proceeding without authentication."
        )

    logger.info("Creating Elasticsearch client for %s", settings.url)

    return Elasticsearch(
        hosts=[settings.url],
        basic_auth=basic_auth,
        request_timeout=settings.timeout,
        max_retries=settings.max_retries,
    )


def reset_client_cache() -> None:
    """
    Discard the cached client, forcing the next ``get_client()`` call to
    build a new one. Intended for tests and for environments where the
    underlying settings may have changed at runtime.
    """
    get_client.cache_clear()
