# -*- coding: utf-8 -*-
"""Tests for the Channel Health Registry."""

from datetime import datetime

import pytest

from agent_reach.health import (
    ChannelStatus,
    ChannelHealth,
    HealthRegistry,
    get_registry,
    update_from_doctor_results,
)


class TestChannelStatus:
    def test_members_have_correct_values(self):
        assert ChannelStatus.HEALTHY.value == "healthy"
        assert ChannelStatus.DEGRADED.value == "degraded"
        assert ChannelStatus.UNAVAILABLE.value == "unavailable"


class TestChannelHealth:
    def test_basic_fields(self):
        now = datetime(2026, 6, 18, 12, 0, 0)
        h = ChannelHealth(
            channel_name="github",
            status=ChannelStatus.HEALTHY,
            last_checked=now,
        )
        assert h.channel_name == "github"
        assert h.status == ChannelStatus.HEALTHY
        assert h.last_checked == now
        assert h.failure_reason is None

    def test_with_failure_reason(self):
        now = datetime.now()
        h = ChannelHealth(
            channel_name="twitter",
            status=ChannelStatus.DEGRADED,
            last_checked=now,
            failure_reason="Cookie expired",
        )
        assert h.failure_reason == "Cookie expired"


class TestHealthRegistry:
    def test_update_and_get(self):
        registry = HealthRegistry()
        now = datetime.now()
        h = ChannelHealth("github", ChannelStatus.HEALTHY, now)
        registry.update_health("github", h)
        assert registry.get_health("github") is h
        assert registry.get_health("unknown") is None

    def test_get_all_health(self):
        registry = HealthRegistry()
        now = datetime.now()
        h1 = ChannelHealth("github", ChannelStatus.HEALTHY, now)
        h2 = ChannelHealth("twitter", ChannelStatus.DEGRADED, now)
        registry.update_health("github", h1)
        registry.update_health("twitter", h2)
        all_h = registry.get_all_health()
        assert all_h == {"github": h1, "twitter": h2}

    def test_update_replaces_existing(self):
        registry = HealthRegistry()
        now = datetime.now()
        h1 = ChannelHealth("github", ChannelStatus.HEALTHY, now)
        h2 = ChannelHealth("github", ChannelStatus.DEGRADED, now, failure_reason="API timeout")
        registry.update_health("github", h1)
        registry.update_health("github", h2)
        assert registry.get_health("github").status == ChannelStatus.DEGRADED

    def test_get_all_returns_copy(self):
        registry = HealthRegistry()
        all_h = registry.get_all_health()
        assert isinstance(all_h, dict)

    def test_singleton_get_registry(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2


class TestDoctorStatusMapping:
    @pytest.mark.parametrize(
        ("doctor_status", "expected"),
        [
            ("ok", ChannelStatus.HEALTHY),
            ("warn", ChannelStatus.DEGRADED),
            ("off", ChannelStatus.UNAVAILABLE),
            ("error", ChannelStatus.DEGRADED),
        ],
    )
    def test_mapping(self, doctor_status, expected):
        results = {
            "ch": {"status": doctor_status, "message": "irrelevant", "name": "...",
                   "tier": 0, "backends": [], "active_backend": None},
        }
        update_from_doctor_results(results)
        assert get_registry().get_health("ch").status == expected

    def test_unknown_status_falls_to_degraded(self):
        results = {
            "ch": {"status": "bogus", "message": "weird", "name": "...",
                   "tier": 0, "backends": [], "active_backend": None},
        }
        update_from_doctor_results(results)
        assert get_registry().get_health("ch").status == ChannelStatus.DEGRADED
