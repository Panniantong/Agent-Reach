# -*- coding: utf-8
"""Tests for watchlist intel harness refinement."""

from unittest.mock import patch

from agent_reach.daily_run.watchlist_intel_harness import (
    apply_watchlist_intel_harness_refinement,
    watchlist_intel_to_harness_evidence,
)


class TestWatchlistIntelHarness:
    def test_evidence_for_negative_announcements(self):
        evidence = watchlist_intel_to_harness_evidence(
            {
                "603986": {
                    "code": "603986",
                    "name": "兆易创新",
                    "sentiment": "negative",
                    "headline": "被证监会立案调查",
                },
                "688981": {
                    "code": "688981",
                    "name": "中芯国际",
                    "sentiment": "negative",
                    "headline": "业绩预告预亏",
                },
            },
            adjust={
                "applied": True,
                "changes": [
                    {
                        "action": "remove",
                        "code": "603986",
                        "name": "兆易创新",
                        "reason": "利空公告：被证监会立案调查",
                    }
                ],
            },
        )
        assert evidence["policy"]
        assert any("利空公告" in line for line in evidence["playbook"])
        assert any("移出 1 只" in line for line in evidence["memory"])

    @patch("agent_reach.daily_run.watchlist_intel_harness.apply_skill_refinement")
    def test_apply_watchlist_intel_harness(self, mock_apply):
        mock_apply.return_value = {"job": "watchlist_intel", "changes": 1}
        out = apply_watchlist_intel_harness_refinement(
            {
                "603986": {
                    "code": "603986",
                    "name": "兆易创新",
                    "sentiment": "negative",
                    "headline": "被证监会立案调查",
                }
            },
            settings={"watchlist": {"intel_harness_evolve": True}},
        )
        mock_apply.assert_called_once()
        assert out["job"] == "watchlist_intel"
