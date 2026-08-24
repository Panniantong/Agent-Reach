# -*- coding: utf-8 -*-
"""Isolated local server for the Narrative Playwright acceptance flow."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

import agent_reach.radar_ui.jobs as jobs_module
from agent_reach.narrative.quant import QuantAdapter
from agent_reach.narrative.service import NarrativeService
from agent_reach.narrative.store import NarrativeStore
from agent_reach.radar_ui.server import create_app


def main() -> None:
    data_root = Path(os.environ["NARRATIVE_E2E_DATA_DIR"]).resolve()
    quant_root = Path(os.environ.get("QUANT_DATA_ROOT", r"D:\DOT\Quant\data")).resolve()
    port = int(os.environ.get("NARRATIVE_E2E_PORT", "8137"))
    data_root.mkdir(parents=True, exist_ok=True)
    jobs_module.JOBS_DIR = data_root / "jobs"
    service = NarrativeService(
        NarrativeStore(data_root / "narrative"),
        QuantAdapter(quant_root),
    )
    uvicorn.run(
        create_app(narrative_service=service),
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
