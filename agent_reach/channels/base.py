# -*- coding: utf-8 -*-
"""Base types for supported research channels."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple


class Channel(ABC):
    """A research source that Agent Reach can diagnose for availability."""

    name: str = ""
    description: str = ""
    backends: List[str] = []
    tier: int = 0  # 0 = core, 1 = optional login/setup, 2 = advanced/manual

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True when this channel is a natural fit for the URL."""

    def check(self, config=None) -> Tuple[str, str]:
        """Return a health tuple: (status, message)."""

        summary = ", ".join(self.backends) if self.backends else "configured"
        return "ok", summary
