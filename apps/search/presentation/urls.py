"""
URL configuration for the search application's presentation layer.

This module is included by ``config/urls.py`` under the root path. As the
API grows, additional path entries will be added here (search, suggest,
explain, reindex, health) in the phases that introduce them.
"""

from __future__ import annotations

from django.urls import path

from apps.search.presentation.views import ServiceRootView

app_name = "search"

urlpatterns = [
    path("", ServiceRootView.as_view(), name="service-root"),
]
