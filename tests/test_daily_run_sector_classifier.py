# -*- coding: utf-8
"""Tests for sector classification."""

from agent_reach.daily_run.sector_classifier import (
    attach_sector,
    build_sector_index,
    lookup_sector,
)
from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.symbols import build_enriched_symbols


def _settings_with_sectors():
    cfg = load_settings()
    cfg.setdefault("watchlist", {})
    cfg["watchlist"].setdefault(
        "sector_map",
        {
            "688008": "半导体",
            "603986": "存储",
            "002273": "光通信",
            "300308": "光通信",
            "000725": "面板",
            "002583": "通信设备",
        },
    )
    cfg["watchlist"].setdefault(
        "sector_pools",
        {
            "半导体": [{"code": "688008", "name": "澜起科技", "keywords": ["澜起"]}],
            "存储": [{"code": "603986", "name": "兆易创新", "keywords": ["兆易"]}],
            "光通信": [{"code": "300308", "name": "中际旭创", "keywords": ["中际"]}],
        },
    )
    return cfg


def test_sector_map_lookup():
    settings = _settings_with_sectors()
    assert lookup_sector("688008", "澜起科技", settings=settings) == "半导体"
    assert lookup_sector("300308", "中际旭创", settings=settings) == "光通信"
    assert lookup_sector("000725", "京东方A", settings=settings) == "面板"


def test_name_heuristic_fallback():
    assert lookup_sector("999999", "海康威视") == "安防"


def test_attach_sector_to_row():
    settings = _settings_with_sectors()
    row = attach_sector({"code": "002583", "name": "海能达"}, settings=settings)
    assert row["sector"] == "通信设备"


def test_build_enriched_symbols_includes_sector():
    settings = _settings_with_sectors()
    snap = {
        "code": "688008",
        "portfolio": {
            "holdings": [
                {"code": "688008", "name": "澜起科技", "price": 200, "change_pct": 1.0},
                {"code": "002273", "name": "水晶光电", "price": 26, "change_pct": 0.5},
            ]
        },
        "watchlist": [{"code": "603986", "name": "兆易创新", "change_pct": -1.0}],
    }
    enriched = build_enriched_symbols(snap, settings)
    assert enriched["688008"]["sector"] == "半导体"
    assert enriched["002273"]["sector"] == "光通信"
    assert enriched["603986"]["sector"] == "存储"


def test_sector_index_includes_pools():
    settings = _settings_with_sectors()
    settings["watchlist"]["sector_pools"]["半导体"] = [
        {"code": "688981", "name": "中芯国际", "keywords": ["中芯"]},
    ]
    index = build_sector_index(settings)
    assert index.get("688981") == "半导体"
    assert index.get("601138") == "AI算力"
