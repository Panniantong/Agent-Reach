# -*- coding: utf-8 -*-
"""Small wrapper around the fork's health checks."""

from __future__ import annotations

from typing import Dict, Optional

from agent_reach.config import Config


class AgentReach:
    """Expose health-check helpers for the local install."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()

    def doctor(self) -> Dict[str, dict]:
        from agent_reach.doctor import check_all

        return check_all(self.config)

    def doctor_report(self) -> str:
        from agent_reach.doctor import check_all, format_report

        return format_report(check_all(self.config))
