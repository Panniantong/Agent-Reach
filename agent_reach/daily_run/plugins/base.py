# -*- coding: utf-8
"""Plugin base types for daily-run expert modules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginContext:
    snapshot: dict[str, Any]
    settings: dict[str, Any]


@dataclass
class PluginResult:
    name: str
    score: float
    summary: str
    success: bool = True
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "summary": self.summary,
            "success": self.success,
            "details": self.details,
        }


class ExpertPlugin(ABC):
    """Single expert analysis plugin."""

    name: str = "expert"
    description: str = ""

    @abstractmethod
    def run(self, context: PluginContext) -> PluginResult:
        ...


class FilterPlugin(ABC):
    """Pre-expert gate — return False to skip expert execution."""

    name: str = "filter"
    description: str = ""

    @abstractmethod
    def apply(self, context: PluginContext) -> bool:
        ...


class TransformPlugin(ABC):
    """Pre-expert snapshot transform."""

    name: str = "transform"
    description: str = ""

    @abstractmethod
    def transform(self, snapshot: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        ...
