# -*- coding: utf-8
"""Tests for RedFox gzh subscription CLI helpers."""

from __future__ import annotations

import agent_reach.daily_run.redfox_collector as redfox_collector_mod
from agent_reach.daily_run.redfox_gzh import (
    add_gzh_subscription,
    list_gzh_subscriptions,
    remove_gzh_subscription,
    render_gzh_subscriptions_markdown,
)


def test_gzh_add_list_remove(tmp_path, monkeypatch):
    subs_path = tmp_path / "gzh_subscriptions.json"
    monkeypatch.setattr(
        redfox_collector_mod,
        "gzh_subscriptions_path",
        lambda settings=None: subs_path,
    )
    settings = {"redfox": {"gzh_astock": {"subscriptions_file": str(subs_path)}}}

    added = add_gzh_subscription("official", "央视财经", settings=settings)
    assert added["action"] == "added"
    assert "央视财经" in added["official"]

    noop = add_gzh_subscription("official", "央视财经", settings=settings)
    assert noop["action"] == "noop"

    listed = list_gzh_subscriptions(settings=settings)
    assert listed["official"] == ["央视财经"]

    removed = remove_gzh_subscription("official", "央视财经", settings=settings)
    assert removed["action"] == "removed"
    assert removed["official"] == []


def test_gzh_category_aliases():
    from agent_reach.daily_run.redfox_gzh import _normalize_category

    assert _normalize_category("机构") == "official"
    assert _normalize_category("personal") == "personal"


def test_render_gzh_subscriptions_markdown():
    md = render_gzh_subscriptions_markdown(
        {
            "path": "/tmp/gzh.json",
            "message": "已添加",
            "official": ["央视财经"],
            "personal": [],
        }
    )
    assert "RedFox" in md
    assert "央视财经" in md
