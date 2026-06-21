# -*- coding: utf-8 -*-
"""Channel health state — populated transparently when doctor runs.

Usage::

    from agent_reach.health import get_registry

    registry = get_registry()
    health = registry.get_health("github")
    print(health.status)   # ChannelStatus.HEALTHY
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional


class ChannelStatus(Enum):
    """Current health of a single channel."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass
class ChannelHealth:
    """Health record for one channel at a point in time."""

    channel_name: str
    status: ChannelStatus
    last_checked: datetime
    failure_reason: Optional[str] = None


class HealthRegistry:
    """In-memory store of the latest channel health state."""

    def __init__(self):
        self._health: Dict[str, ChannelHealth] = {}

    def update_health(self, channel_name: str, health: ChannelHealth) -> None:
        self._health[channel_name] = health

    def get_health(self, channel_name: str) -> Optional[ChannelHealth]:
        return self._health.get(channel_name)

    def get_all_health(self) -> Dict[str, ChannelHealth]:
        return dict(self._health)


_registry = HealthRegistry()


def get_registry() -> HealthRegistry:
    return _registry


_STATUS_MAP = {
    "ok": ChannelStatus.HEALTHY,
    "warn": ChannelStatus.DEGRADED,
    "off": ChannelStatus.UNAVAILABLE,
    "error": ChannelStatus.DEGRADED,
}


def update_from_doctor_results(results: Dict[str, dict]) -> None:
    """Populate the registry from a ``doctor.check_all()`` result dict."""
    registry = get_registry()
    for name, data in results.items():
        health = ChannelHealth(
            channel_name=name,
            status=_STATUS_MAP.get(data["status"], ChannelStatus.DEGRADED),
            last_checked=datetime.now(timezone.utc),
            failure_reason=data.get("message") if data.get("status") != "ok" else None,
        )
        registry.update_health(name, health)


__all__ = [
    "ChannelStatus",
    "ChannelHealth",
    "HealthRegistry",
    "get_registry",
    "update_from_doctor_results",
]
