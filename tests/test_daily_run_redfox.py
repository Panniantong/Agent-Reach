# -*- coding: utf-8
"""Tests for RedFox API client and collector (Path B)."""

from __future__ import annotations

from unittest.mock import patch

from agent_reach.daily_run.redfox_client import (
    expand_keywords,
    fetch_gzh_astock,
    fetch_stock_feed,
    fetch_trending_hub,
    fetch_weibo_search,
    get_api_key,
    redfox_enabled,
)
from agent_reach.daily_run.redfox_collector import (
    RedfoxResult,
    attach_redfox_close_markdown,
    collect_redfox_context,
    cross_validate_emotion,
    merge_portfolio_for_redfox,
    redfox_result_from_snapshot,
    render_redfox_markdown,
)


class TestRedfoxClient:
    def test_expand_keywords_semiconductor(self):
        terms = expand_keywords("半导体")
        assert "半导体" in terms
        assert "芯片" in terms

    def test_redfox_disabled_without_key(self):
        settings = {"redfox": {"enabled": True}}
        with patch.dict("os.environ", {}, clear=True):
            assert redfox_enabled(settings) is False

    def test_redfox_enabled_with_env(self):
        settings = {"redfox": {"enabled": True}}
        with patch.dict("os.environ", {"REDFOX_API_KEY": "ak_test"}):
            assert redfox_enabled(settings) is True
            assert get_api_key(settings) == "ak_test"

    @patch("agent_reach.daily_run.redfox_client._http_post")
    def test_fetch_stock_feed_parses_items(self, mock_post):
        mock_post.return_value = {
            "code": 2000,
            "data": {
                "xhsResult": [
                    {"workTitle": "A股半导体大涨", "workUrl": "https://xhs.example/1"},
                ],
                "dyResult": [],
                "gzhResult": [],
            },
        }
        out = fetch_stock_feed("A股,半导体", api_key="ak_test")
        assert len(out["items"]) == 1
        assert out["items"][0]["platform"] == "xhs"
        assert "半导体" in out["items"][0]["title"]

    @patch("agent_reach.daily_run.redfox_client._http_post")
    def test_fetch_trending_hub_parses_items(self, mock_post):
        mock_post.return_value = {
            "code": 2000,
            "data": {
                "wbList": [{"title": "芯片板块", "url": "https://weibo.example", "hotCount": 50000}],
            },
        }
        out = fetch_trending_hub(platforms=["wb"], api_key="ak_test")
        assert len(out["items"]) == 1
        assert out["items"][0]["title"] == "芯片板块"

    @patch("agent_reach.daily_run.redfox_client._http_post")
    def test_fetch_gzh_astock_dual_category(self, mock_post):
        mock_post.return_value = {
            "code": 2000,
            "data": {
                "accounts": [
                    {
                        "accountName": "央视财经",
                        "avgReadCount": 32000,
                        "works": [{"title": "政策利好", "workUrl": "https://mp.weixin.qq.com/a"}],
                    },
                    {
                        "accountName": "好运哥2008",
                        "avgReadCount": 71000,
                        "works": [{"title": "太强了", "workUrl": "https://mp.weixin.qq.com/b"}],
                    },
                ],
            },
        }
        out = fetch_gzh_astock(api_key="ak_test")
        assert len(out["official"]) == 1
        assert len(out["personal"]) == 1
        assert out["official"][0]["latest_title"] == "政策利好"

    @patch("agent_reach.daily_run.redfox_client._http_post")
    def test_fetch_weibo_search(self, mock_post):
        mock_post.return_value = {
            "code": 2000,
            "data": {"workList": [{"text": "半导体政策解读", "workUrl": "https://weibo.com/1"}]},
        }
        out = fetch_weibo_search("半导体", api_key="ak_test")
        assert len(out["items"]) == 1
        assert out["items"][0]["platform"] == "wb_search"


class TestGzhSubscriptions:
    def test_filter_subscriptions(self, tmp_path):
        from agent_reach.daily_run.redfox_collector import (
            _filter_gzh_accounts,
            load_gzh_subscriptions,
            save_gzh_subscriptions,
        )

        settings = {
            "redfox": {
                "gzh_astock": {"subscriptions_file": str(tmp_path / "subs.json")},
            }
        }
        save_gzh_subscriptions({"official": ["央视财经"], "personal": []}, settings=settings)
        subs = load_gzh_subscriptions(settings)
        assert subs["official"] == ["央视财经"]
        personal, official = _filter_gzh_accounts(
            [{"account_name": "好运哥2008"}],
            [{"account_name": "央视财经"}, {"account_name": "财联社"}],
            subs,
        )
        assert len(personal) == 1
        assert len(official) == 1
        assert official[0]["account_name"] == "央视财经"


class TestRedfoxCollector:
    @patch("agent_reach.daily_run.redfox_collector.fetch_gzh_astock")
    @patch("agent_reach.daily_run.redfox_collector.fetch_trending_hub")
    @patch("agent_reach.daily_run.redfox_collector.fetch_stock_feed")
    def test_collect_redfox_context_morning(self, mock_feed, mock_trend, mock_gzh):
        mock_feed.return_value = {
            "items": [
                {"platform": "xhs", "title": "澜起科技存储芯片", "source": "redfox_stock_feed"},
            ],
        }
        mock_trend.return_value = {
            "items": [{"platform": "wb", "title": "半导体政策", "source": "redfox_trending_hub"}],
            "platforms": ["wb"],
        }
        mock_gzh.return_value = {
            "personal": [{"account_name": "好运哥2008", "latest_title": "复盘"}],
            "official": [{"account_name": "央视财经", "latest_title": "宏观"}],
        }
        pf = {"holdings": [{"name": "澜起科技", "code": "688008"}]}
        settings = {
            "redfox": {
                "enabled": True,
                "cache_ttl_seconds": 0,
                "stock_feed": {"workflows": ["morning"]},
                "trending_hub": {"workflows": ["morning"]},
                "gzh_astock": {"workflows": ["morning"]},
            },
            "hot_news": {"extra_keywords": ["存储", "芯片"]},
        }
        with patch.dict("os.environ", {"REDFOX_API_KEY": "ak_test"}):
            result = collect_redfox_context(pf, settings=settings, workflow="morning")
        assert result.summary
        assert result.gzh_summary
        assert any("澜起" in str(i.get("title", "")) for i in result.matched)

    def test_cross_validate_emotion_divergence(self):
        review = {"emotion": {"rating": "强"}}
        redfox = RedfoxResult(
            matched=[{"title": "大盘跳水跌停潮"} for _ in range(5)],
        )
        msg = cross_validate_emotion(review, redfox)
        assert "分歧" in msg

    def test_cross_validate_uses_stock_feed_without_matched(self):
        review = {"emotion": {"rating": "强"}}
        redfox = RedfoxResult(
            matched=[],
            stock_feed_items=[{"title": "大盘跳水跌停潮"} for _ in range(5)],
        )
        msg = cross_validate_emotion(review, redfox)
        assert "分歧" in msg

    def test_merge_portfolio_includes_watchlist(self):
        snap = {
            "portfolio": {"holdings": [{"name": "澜起科技", "code": "688008"}]},
            "watchlist": [{"name": "海能达", "code": "002583", "keywords": ["海能达"]}],
        }
        with patch("agent_reach.daily_run.snapshot_builder.load_portfolio") as mock_load:
            mock_load.return_value = {"holdings": [], "watchlist": []}
            merged = merge_portfolio_for_redfox(snap)
        assert merged["holdings"][0]["code"] == "688008"
        assert merged["watchlist"][0]["name"] == "海能达"

    def test_redfox_result_from_snapshot_macro_signals(self):
        snap = {"macro_signals": {"redfox": {"summary": "ok", "matched": []}}}
        result = redfox_result_from_snapshot(snap)
        assert result is not None
        assert result.summary == "ok"

    @patch("agent_reach.daily_run.redfox_collector.collect_redfox_context")
    def test_attach_reuses_snapshot_without_second_fetch(self, mock_collect):
        snap = {
            "redfox": {
                "summary": "cached",
                "gzh_summary": "官媒·测试",
                "matched": [],
                "stock_feed_items": [],
                "trending_items": [],
            }
        }
        md, result = attach_redfox_close_markdown(
            snap,
            {"emotion": {"rating": "中"}},
            settings={"redfox": {"enabled": True}},
        )
        mock_collect.assert_not_called()
        assert "RedFox" in md
        assert result is not None

    def test_render_redfox_markdown(self):
        result = RedfoxResult(
            summary="RedFox 持仓相关：[xhs] 芯片",
            gzh_summary="官媒·央视财经：宏观",
            cross_validation="一致",
        )
        md = render_redfox_markdown(result)
        assert "RedFox 舆情增强" in md
        assert "央视财经" in md

    def test_collect_skipped_when_disabled(self):
        pf = {"holdings": []}
        result = collect_redfox_context(pf, settings={"redfox": {"enabled": False}})
        assert result.summary == ""
        assert result.matched == []
