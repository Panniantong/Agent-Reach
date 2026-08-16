# -*- coding: utf-8
"""Backward-compatible re-exports; see report_narrative.py."""

from agent_reach.daily_run.report_narrative import (
    build_forecast_context,
    build_narrative_context,
    generate_forecast_narrative,
    render_forecast_narrative_markdown,
    render_narrative_markdown,
)

__all__ = [
    "build_forecast_context",
    "build_narrative_context",
    "generate_forecast_narrative",
    "render_forecast_narrative_markdown",
    "render_narrative_markdown",
]
