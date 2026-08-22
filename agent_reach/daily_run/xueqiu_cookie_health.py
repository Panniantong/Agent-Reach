# -*- coding: utf-8
"""Xueqiu cookie health probe for Sunday forecast alerts."""

from __future__ import annotations

from typing import Any, Optional


def _cookie_from_config(config=None) -> tuple[str, str]:
    """Return (cookie_string, source_label)."""
    try:
        from agent_reach.config import Config

        cfg = config or Config()
        raw = str(cfg.get("xueqiu_cookie") or "").strip()
        if raw:
            return raw, "config"
    except Exception:
        pass
    import os

    env = str(os.environ.get("XUEQIU_COOKIE") or "").strip()
    if env:
        return env, "env"
    return "", "none"


def _has_xq_a_token(cookie_str: str) -> bool:
    if not cookie_str:
        return False
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if pair.startswith("xq_a_token=") and len(pair) > len("xq_a_token="):
            return True
    return False


def check_xueqiu_cookie_health(
    *,
    config=None,
    macro_signals: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Probe Xueqiu API readiness for daily-run macro/forecast cards.

    Returns dict with keys: status, level, message, cookie_configured, has_xq_a_token, api_status.
    status: ok | missing | expired | degraded
    """
    cookie_str, source = _cookie_from_config(config)
    configured = bool(cookie_str)
    has_token = _has_xq_a_token(cookie_str)

    api_status = "unknown"
    api_message = ""
    try:
        from agent_reach.channels import xueqiu as xq_mod

        ch = xq_mod.XueqiuChannel()
        status, message = ch.check(config)
        api_status = status
        api_message = str(message or "")
    except Exception as exc:
        api_status = "error"
        api_message = str(exc)

    macro = macro_signals or {}
    macro_ok = bool(
        macro.get("sentiment_posts")
        or macro.get("hot_stocks")
        or macro.get("hot_watch_stocks")
        or macro.get("portfolio_hot_stocks")
    )

    if api_status == "ok":
        out_status = "ok"
        level = "info"
        message = "雪球 Cookie 有效，热帖/热股接口正常"
    elif not configured and not has_token:
        out_status = "missing"
        level = "warn"
        message = "未配置雪球 Cookie，周日报告「雪球热门」可能为空"
    elif configured and (not has_token or api_status in {"warn", "error"}):
        out_status = "expired"
        level = "warn"
        message = "雪球 Cookie 可能已过期或无效，请重新导出"
    else:
        out_status = "degraded"
        level = "warn"
        message = api_message or "雪球 API 响应异常"

    if out_status == "ok" and not macro_ok and configured:
        out_status = "degraded"
        level = "warn"
        message = "Cookie 探针通过但未拉到热帖/热股，建议复核登录态"

    return {
        "status": out_status,
        "level": level,
        "message": message,
        "cookie_configured": configured,
        "cookie_source": source,
        "has_xq_a_token": has_token,
        "api_status": api_status,
        "api_message": api_message,
        "macro_signals_ok": macro_ok,
    }


def render_xueqiu_cookie_alert_markdown(health: Optional[dict[str, Any]] = None, *, config=None) -> str:
    """Feishu markdown for Sunday forecast cookie alert (empty when healthy)."""
    data = health or check_xueqiu_cookie_health(config=config)
    status = str(data.get("status") or "ok")
    if status == "ok":
        return ""

    title = {
        "missing": "未配置",
        "expired": "已过期 / 无效",
        "degraded": "异常",
    }.get(status, "需关注")

    lines = [
        "## 🍪 雪球 Cookie 预警",
        "",
        f"**状态：** {title} — {data.get('message', '')}",
        "",
        "**影响：** 周日预测卡「雪球热门」、宏观舆情、部分 MSS 情绪因子可能缺失或降级。",
        "",
        "### 获取 Cookie（推荐 Cookie-Editor）",
        "",
        "1. 在 Chrome 打开并登录 [xueqiu.com](https://xueqiu.com)",
        "2. 安装 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 扩展",
        "3. 点击扩展图标 → **Export** → **Header String**，复制整段 Cookie",
        "4. 写入 Agent Reach 配置（任选其一）：",
        "",
        "**方式 A — 编辑配置文件**",
        "",
        "```yaml",
        "# ~/.agent-reach/config.yaml",
        'xueqiu_cookie: "xq_a_token=...; u=...; ..."',
        "```",
        "",
        "**方式 B — 本地 Chrome 一键提取**（需本机已登录雪球）",
        "",
        "```bash",
        "python3 -m agent_reach.cli configure --from-browser chrome",
        "python3 -m agent_reach.cli doctor",
        "```",
        "",
        "**方式 C — 环境变量**（Cloud Agent / cron）",
        "",
        "```bash",
        "export XUEQIU_COOKIE='xq_a_token=...; u=...; ...'",
        "```",
        "",
        "更新后运行 `python3 -m agent_reach.cli doctor`，确认 **雪球** 渠道为 ✅。",
    ]
    if data.get("api_message") and status != "missing":
        lines.extend(["", f"_API 详情：{str(data['api_message'])[:180]}_"])
    return "\n".join(lines)
