# -*- coding: utf-8
"""Tests for context store, cases, and context CLI."""

import json
from pathlib import Path

from agent_reach.daily_run.context_cli import cmd_context
from agent_reach.daily_run.context_store import (
    find_context,
    list_context,
    read_layer,
    record_trade_case,
    resolve_uri,
    should_record_trade_case,
    sync_harness_sidecars,
    trade_case_id,
)
from agent_reach.daily_run.harness import HarnessState


def test_trade_case_id_cash_lot_fail():
    rec = {
        "code": "300308",
        "trade_id": "T7",
        "action": "buy",
        "portfolio_applied": False,
        "portfolio_message": "现金不足以买入 300308 最小单位",
    }
    assert trade_case_id(rec) == "300308-T7-cash-lot-fail"


def test_record_trade_case_writes_layers(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.context_store.cases_root",
        lambda: tmp_path,
    )
    rec = {
        "code": "300308",
        "name": "中际旭创",
        "trade_id": "T7",
        "action": "buy",
        "lookback_mss": 47.07,
        "trend": "rising",
        "reasoning": "条件性建仓",
        "portfolio_applied": False,
        "portfolio_message": "现金不足以买入 300308 最小单位",
        "as_of": "2026-08-21T03:33:22+00:00",
    }
    uri = record_trade_case(
        rec,
        portfolio_snapshot={"cash": 158321.8, "total": 188965.8, "cash_ratio": 0.8378},
        price=928.89,
        settings={
            "harness_runtime": {
                "position_overlay": {"deploy_ratio": {"base": 1.0, "effective": 0.25}},
            }
        },
    )
    assert uri is not None
    case_dir = tmp_path / "300308-T7-cash-lot-fail"
    assert (case_dir / "detail.json").exists()
    assert (case_dir / ".abstract.md").exists()
    assert (case_dir / ".overview.md").exists()
    overview = (case_dir / ".overview.md").read_text(encoding="utf-8")
    assert "deploy_ratio" in overview
    abstract = read_layer(uri, layer="abstract")
    assert "中际旭创" in abstract


def test_sync_harness_sidecars(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.context_store.harness_entries_root",
        lambda: tmp_path,
    )
    state = HarnessState()
    state.upsert(
        "policy",
        "cash_guard",
        title="维持高现金",
        content="MSS 低于 macro_veto 时禁止接飞刀",
        job="close",
        source="test",
        evidence="test",
    )
    n = sync_harness_sidecars(state)
    assert n == 1
    assert (tmp_path / "policy" / "cash_guard.md").exists()
    assert (tmp_path / "policy" / "cash_guard.abstract.md").exists()


def test_find_and_list_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.context_store.cases_root",
        lambda: tmp_path,
    )
    record_trade_case(
        {
            "code": "300308",
            "name": "中际旭创",
            "trade_id": "T7",
            "action": "buy",
            "portfolio_applied": False,
            "portfolio_message": "现金不足以买入 300308 最小单位",
        },
        portfolio_snapshot={"cash": 100},
    )
    rows = list_context("agentreach://daily_run/memory/cases")
    assert len(rows) == 1
    hits = find_context("现金不足", kind="cases", code="300308")
    assert hits
    assert hits[0]["kind"] == "case"


def test_resolve_harness_entry_uri(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.context_store.harness_entries_root",
        lambda: tmp_path / "harness" / "entries",
    )
    path = tmp_path / "harness" / "entries" / "policy" / "x.md"
    path.parent.mkdir(parents=True)
    path.write_text("# x\n\nbody\n", encoding="utf-8")
    resolved = resolve_uri("agentreach://daily_run/harness/entries/policy/x")
    assert resolved == path


def test_context_cli_find_json(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.context_store.cases_root",
        lambda: tmp_path,
    )
    record_trade_case(
        {
            "code": "600584",
            "name": "长电科技",
            "trade_id": "T3",
            "action": "sell",
            "portfolio_applied": False,
            "portfolio_message": "深度套牢不允许卖出",
            "blocked": True,
        },
    )
    import argparse

    args = argparse.Namespace(
        context_action="find",
        query="深度套牢",
        kind="cases",
        code="",
        limit=5,
        json=True,
    )
    cmd_context(args)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data[0]["code"] == "600584"


def test_should_not_record_applied_buy():
    assert should_record_trade_case({"action": "buy", "portfolio_applied": True}) is False
    assert should_record_trade_case({"action": "hold", "portfolio_applied": False}) is False
