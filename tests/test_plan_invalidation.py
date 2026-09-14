# -*- coding: utf-8
"""Plan stop invalidation for hold_debounce."""

import pytest

from agent_reach.daily_run.hold_debounce_guards import touch_week_open_hold_debounce
from agent_reach.daily_run.plan_invalidation import (
    hold_debounce_invalidated,
    operation_plan_has_trim,
    symbol_plan_stop_price,
)


@pytest.fixture
def patch_week_open(monkeypatch):
    overlay: dict = {}

    def _set(plans: list[dict]):
        overlay.clear()
        overlay.update({"enabled": True, "operation_plans": plans})

    monkeypatch.setattr(
        "agent_reach.daily_run.week_open_overlay.load_week_open_overlay",
        lambda **_: dict(overlay) if overlay else None,
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.week_open_overlay.week_open_overlay_active",
        lambda settings=None: True,
    )
    return _set


def test_symbol_plan_stop_from_text(patch_week_open):
    patch_week_open(
        [{"code": "688008", "operation_plan": "持有：180企稳 → 止损 170元"}]
    )
    stop = symbol_plan_stop_price("688008", settings={})
    assert stop == 170.0


def test_hold_debounce_invalidated_below_stop(patch_week_open):
    patch_week_open(
        [{"code": "688008", "operation_plan": "持有：180企稳 → 止损 170元"}]
    )
    ok, reason = hold_debounce_invalidated("688008", 169.5, settings={})
    assert ok is True
    assert "计划止损" in reason


def test_touch_skips_debounce_when_plan_stop_hit(patch_week_open):
    patch_week_open(
        [{"code": "688008", "operation_plan": "持有：180企稳 → 止损 170元"}]
    )
    settings = {
        "intraday": {
            "defensive_trim": {
                "hold_debounce": {"enabled": True, "invalidate_below_plan_stop": True},
            }
        },
        "harness_runtime": {
            "hold_debounce_policy": {"required_strikes": 2.0, "hold_sell_ratio_cap": 0.15},
        },
    }
    strikes: dict[str, int] = {"688008": 0}
    block, cap = touch_week_open_hold_debounce(
        settings,
        "688008",
        allow_defensive=True,
        strikes=strikes,
        price=169.0,
    )
    assert block is None
    assert cap is None


def test_operation_plan_has_trim(patch_week_open):
    patch_week_open([{"code": "002583", "operation_plan": "减仓：流动性萎缩 → 18%"}])
    assert operation_plan_has_trim("002583", settings={}) is True
