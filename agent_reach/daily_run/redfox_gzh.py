# -*- coding: utf-8
"""Manage RedFox gzh subscription lists."""

from __future__ import annotations

from typing import Any, Literal, Optional

from agent_reach.daily_run.redfox_collector import (
    gzh_subscriptions_path,
    load_gzh_subscriptions,
    save_gzh_subscriptions,
)

GzhCategory = Literal["official", "personal"]


def _normalize_category(category: str) -> GzhCategory:
    key = str(category or "").strip().lower()
    if key in {"official", "off", "gov", "机构", "官方"}:
        return "official"
    if key in {"personal", "person", "kol", "个人", "大v"}:
        return "personal"
    raise ValueError(f"未知 gzh 分类：{category}（可用 official / personal）")


def list_gzh_subscriptions(*, settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    subs = load_gzh_subscriptions(settings)
    return {
        "path": str(gzh_subscriptions_path(settings)),
        "official": list(subs.get("official") or []),
        "personal": list(subs.get("personal") or []),
    }


def add_gzh_subscription(
    category: str,
    name: str,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cat = _normalize_category(category)
    account = str(name or "").strip()
    if not account:
        raise ValueError("公众号名称不能为空")

    subs = load_gzh_subscriptions(settings)
    rows = list(subs.get(cat) or [])
    if account in rows:
        return {
            "action": "noop",
            "category": cat,
            "name": account,
            "path": str(gzh_subscriptions_path(settings)),
            "message": "已在订阅列表中",
            **list_gzh_subscriptions(settings=settings),
        }

    rows.append(account)
    subs[cat] = rows
    path = save_gzh_subscriptions(subs, settings=settings)
    return {
        "action": "added",
        "category": cat,
        "name": account,
        "path": str(path),
        "message": f"已添加 {cat} · {account}",
        **list_gzh_subscriptions(settings=settings),
    }


def remove_gzh_subscription(
    category: str,
    name: str,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cat = _normalize_category(category)
    account = str(name or "").strip()
    if not account:
        raise ValueError("公众号名称不能为空")

    subs = load_gzh_subscriptions(settings)
    rows = list(subs.get(cat) or [])
    if account not in rows:
        return {
            "action": "noop",
            "category": cat,
            "name": account,
            "path": str(gzh_subscriptions_path(settings)),
            "message": "不在订阅列表中",
            **list_gzh_subscriptions(settings=settings),
        }

    subs[cat] = [row for row in rows if row != account]
    path = save_gzh_subscriptions(subs, settings=settings)
    return {
        "action": "removed",
        "category": cat,
        "name": account,
        "path": str(path),
        "message": f"已移除 {cat} · {account}",
        **list_gzh_subscriptions(settings=settings),
    }


def render_gzh_subscriptions_markdown(result: dict[str, Any]) -> str:
    lines = [
        "**RedFox 公众号订阅**",
        "",
        f"- 路径：`{result.get('path')}`",
    ]
    if result.get("message"):
        lines.append(f"- 状态：{result.get('message')}")
    for cat, label in (("official", "机构号"), ("personal", "个人号")):
        rows = result.get(cat) or []
        lines.extend(["", f"**{label}** ({len(rows)})"])
        if rows:
            for name in rows:
                lines.append(f"- {name}")
        else:
            lines.append("- （空）")
    return "\n".join(lines)
