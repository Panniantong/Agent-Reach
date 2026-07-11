# -*- coding: utf-8 -*-
"""Finviz collector tests — offline: requests + token resolution mocked."""

from types import SimpleNamespace

import agent_reach.radar_finviz as rf
from agent_reach.config import Config
from agent_reach.radar_finviz import _finviz_token, collect_finviz

NEWS_CSV = (
    "Title,Source,Date,Url,Category\n"
    '"NVIDIA earnings beat as AI datacenter capex surges",Reuters,2026-07-11 08:00,https://news/1,Stock News\n'
    '"Celebrity spotted at cafe",TMZ,2026-07-11 08:05,https://news/2,Other\n'
)

GROUPS_CSV = (
    "No.,Name,Change\n"
    '1,Technology,"2.34%"\n'
    '2,Utilities,"0.40%"\n'
    '3,Energy,"-1.80%"\n'
)

SOURCES = {
    "finviz": {"news": True, "groups": True, "sector_alert_pct": 1.5, "news_top_n": 12},
    "topic_keywords": ["ai", "nvidia", "earnings"],
}


def _empty_config(tmp_path) -> Config:
    return Config(config_path=tmp_path / "config.yaml")


def _fake_get(csv_by_path):
    def fake(url, params=None, timeout=30, headers=None):
        assert params and params.get("auth") == "tok123"
        for frag, body in csv_by_path.items():
            if frag in url:
                return SimpleNamespace(content=body.encode("utf-8"), raise_for_status=lambda: None)
        raise AssertionError(f"unexpected url {url}")
    return fake


def test_token_from_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("FINVIZ_AUTH_TOKEN", raising=False)
    envf = tmp_path / ".env"
    envf.write_text("OTHER=1\nFINVIZ_AUTH_TOKEN=\"tok-from-file\"\n", encoding="utf-8")
    tok = _finviz_token(_empty_config(tmp_path), {"finviz_env_paths": [str(envf)]})
    assert tok == "tok-from-file"


def test_token_missing_returns_empty(monkeypatch, tmp_path):
    monkeypatch.delenv("FINVIZ_AUTH_TOKEN", raising=False)
    tok = _finviz_token(_empty_config(tmp_path), {"finviz_env_paths": [str(tmp_path / "nope.env")]})
    assert tok == ""


def test_collect_without_token_is_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(rf, "_finviz_token", lambda c=None, s=None: "")
    assert collect_finviz(SOURCES, _empty_config(tmp_path)) == []


def test_collect_news_topic_gated_and_sector_alerts(monkeypatch, tmp_path):
    monkeypatch.setattr(rf, "_finviz_token", lambda c=None, s=None: "tok123")
    monkeypatch.setattr(rf.requests, "get", _fake_get({
        "export/news": NEWS_CSV,
        "export/groups": GROUPS_CSV,
    }))
    items = collect_finviz(SOURCES, _empty_config(tmp_path))
    news = [i for i in items if i.extra["type"] == "news"]
    sectors = [i for i in items if i.extra["type"] == "sector"]
    # Gossip filtered by the topic gate; NVIDIA passes.
    assert len(news) == 1 and "NVIDIA" in news[0].title
    assert news[0].kind == "market" and news[0].url == "https://news/1"
    # Utilities +0.40% below the 1.5% threshold; Tech and Energy alert.
    assert {s.extra["sector"] for s in sectors} == {"Technology", "Energy"}
    assert any(s.title.startswith("▲") for s in sectors)
    assert any(s.title.startswith("▼") for s in sectors)


def test_collect_never_raises_on_network_error(monkeypatch, tmp_path):
    monkeypatch.setattr(rf, "_finviz_token", lambda c=None, s=None: "tok123")

    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(rf.requests, "get", boom)
    assert collect_finviz(SOURCES, _empty_config(tmp_path)) == []


def test_digest_renders_market_section():
    from datetime import datetime, timezone

    from agent_reach.radar import Item, build_digest

    when = datetime(2026, 7, 11, 8, 0, tzinfo=timezone.utc)
    sec = Item(source="finviz:sector", kind="market", title="▲ Technology 板塊單日 +2.34%",
               url="https://elite.finviz.com/groups.ashx", score=2.34,
               extra={"type": "sector", "sector": "Technology", "change": 2.34})
    news = Item(source="finviz:news", kind="market", title="NVIDIA earnings beat",
                url="https://news/1", text="Reuters", extra={"type": "news"})
    md = build_digest({"market": [sec, news]}, {}, when)
    assert "## 📊 市場訊號（Finviz）" in md
    assert "板塊異動" in md and "Technology" in md
    assert "NVIDIA earnings beat" in md and "市場 2" in md
