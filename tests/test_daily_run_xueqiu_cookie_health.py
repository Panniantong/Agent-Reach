# -*- coding: utf-8
"""Tests for Xueqiu cookie health alerts in Sunday forecast."""

from unittest.mock import patch

from agent_reach.daily_run.week_forecast import render_forecast_sections
from agent_reach.daily_run.xueqiu_cookie_health import (
    check_xueqiu_cookie_health,
    render_xueqiu_cookie_alert_markdown,
)


def test_check_missing_cookie():
    with patch(
        "agent_reach.daily_run.xueqiu_cookie_health._cookie_from_config",
        return_value=("", "none"),
    ), patch("agent_reach.channels.xueqiu.XueqiuChannel") as mock_cls:
        mock_cls.return_value.check.return_value = (
            "warn",
            "请先登录雪球后运行：agent-reach configure --from-browser chrome",
        )
        health = check_xueqiu_cookie_health()
    assert health["status"] == "missing"
    assert health["cookie_configured"] is False


def test_check_expired_cookie():
    with patch(
        "agent_reach.daily_run.xueqiu_cookie_health._cookie_from_config",
        return_value=("u=1; acw_tc=abc", "config"),
    ), patch("agent_reach.channels.xueqiu.XueqiuChannel") as mock_cls:
        mock_cls.return_value.check.return_value = ("warn", "API 连接失败")
        health = check_xueqiu_cookie_health()
    assert health["status"] == "expired"
    assert health["has_xq_a_token"] is False


def test_check_ok():
    with patch(
        "agent_reach.daily_run.xueqiu_cookie_health._cookie_from_config",
        return_value=("xq_a_token=abc; u=1", "config"),
    ), patch("agent_reach.channels.xueqiu.XueqiuChannel") as mock_cls:
        mock_cls.return_value.check.return_value = ("ok", "公开 API 可用")
        health = check_xueqiu_cookie_health(macro_signals={"hot_stocks": [{"code": "600519"}]})
    assert health["status"] == "ok"


def test_render_alert_contains_cookie_steps():
    md = render_xueqiu_cookie_alert_markdown(
        {
            "status": "expired",
            "message": "雪球 Cookie 可能已过期或无效，请重新导出",
            "api_message": "401",
        }
    )
    assert "雪球 Cookie 预警" in md
    assert "Cookie-Editor" in md
    assert "xueqiu_cookie" in md
    assert "configure --from-browser chrome" in md


def test_render_alert_empty_when_ok():
    assert render_xueqiu_cookie_alert_markdown({"status": "ok", "message": "ok"}) == ""


def test_forecast_sections_include_cookie_alert():
    sections = render_forecast_sections(
        {
            "week_start": "2026-07-13",
            "week_end": "2026-07-17",
            "mss_daily": {},
            "symbols": {},
            "xueqiu_cookie_health": {
                "status": "expired",
                "message": "雪球 Cookie 可能已过期",
                "api_message": "fail",
            },
        }
    )
    labels = [s.label for s in sections]
    assert "Cookie预警" in labels
    cookie_sec = next(s for s in sections if s.label == "Cookie预警")
    assert "Cookie-Editor" in cookie_sec.markdown
