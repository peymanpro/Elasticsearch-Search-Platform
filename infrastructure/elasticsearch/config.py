"""
Elasticsearch connection settings, loaded from the process environment.

This module is deliberately separate from the client itself: parsing
environment variables is a distinct concern from managing a connection
lifecycle, and keeping them apart allows each to be tested independently
without a running Elasticsearch.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_URL = "http://localhost:9200"
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_RETRIES = 3


@dataclass(frozen=True, slots=True)
class ElasticsearchSettings:
    """Resolved Elasticsearch connection settings."""

    url: str
    username: str | None
    password: str | None
    timeout: float
    max_retries: int

    @classmethod
    def from_env(cls) -> ElasticsearchSettings:
        """
        Build settings from process environment variables.

        Missing optional variables fall back to conservative defaults.
        Empty strings are treated as "not set" so that a placeholder in a
        .env file does not accidentally become a credential.
        """
        url = os.environ.get("ELASTICSEARCH_URL", "").strip() or DEFAULT_URL
        username = os.environ.get("ELASTICSEARCH_USERNAME", "").strip() or None
        password = os.environ.get("ELASTICSEARCH_PASSWORD", "").strip() or None

        timeout_raw = os.environ.get("ELASTICSEARCH_TIMEOUT", "").strip()
        timeout = float(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT

        retries_raw = os.environ.get("ELASTICSEARCH_MAX_RETRIES", "").strip()
        max_retries = int(retries_raw) if retries_raw else DEFAULT_MAX_RETRIES

        return cls(
            url=url,
            username=username,
            password=password,
            timeout=timeout,
            max_retries=max_retries,
        )
