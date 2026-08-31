# -*- coding: utf-8 -*-
"""CLI contract tests for radar-narrative."""

import json
from unittest.mock import patch

from agent_reach.cli import main


class _NarrativeStub:
    store = object()
    quant = object()

    def status(self):
        return {
            "store": {
                "database": "fixture.sqlite3",
                "counts": {"documents": 0, "claims": 0},
            }
        }

    def create_contract(self, payload):
        return {"id": "evt_fixture", **payload}

    def forecast(self, contract_id, *, samples, current_features, as_of):
        return {
            "forecast": {
                "id": "fcst_fixture",
                "probability_status": "insufficient_data",
                "probability": None,
                "lower_bound": None,
                "upper_bound": None,
            }
        }


class _ResearchStub:
    def run_research(self, slice_id, *, as_of, freeze):
        return {
            "pack": {"id": "pack_fixture"},
            "payload": {
                "slice": slice_id,
                "evidence_grade": "E",
                "as_of": as_of or "2026-08-30",
            },
        }

    def daily_sync(self, *, as_of, serenity_days):
        return {"as_of": as_of, "serenity_days": serenity_days}

    def serenity_backfill(self, *, days, count, source_jsonl):
        return {
            "handle": "aleabitoreddit",
            "retrieved": 3,
            "coverage_complete": False,
            "days": days,
            "count": count,
            "source_jsonl": str(source_jsonl or ""),
        }

    def serenity_methodology(self, *, as_of, min_independent_posts, persist):
        return {
            "as_of": as_of,
            "min_independent_posts": min_independent_posts,
            "persist": persist,
            "candidate_logic": [],
        }


class _OfficialStub:
    def sync_sec_filings(self, ticker, *, cik, as_of, limit, user_agent):
        return {
            "ticker": ticker,
            "cik": cik,
            "as_of": as_of,
            "limit": limit,
            "user_agent": user_agent,
            "claims_created": 0,
        }


def test_narrative_status_json(capsys):
    with patch("agent_reach.narrative.service.NarrativeService", return_value=_NarrativeStub()):
        with patch("sys.argv", ["agent-reach", "radar-narrative", "status", "--json"]):
            main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["store"]["database"] == "fixture.sqlite3"


def test_narrative_contract_loads_json_payload(capsys, tmp_path):
    contract = {
        "scope_type": "ticker",
        "scope_id": "NVDA",
        "horizon": "1y",
        "domain": "information-technology",
        "statement": "NVDA closes above 200.",
        "resolution_date": "2027-06-30",
        "resolution_source": "quant_prices",
        "criteria": {"operator": "price_above", "threshold": 200},
    }
    payload_path = tmp_path / "contract.json"
    payload_path.write_text(json.dumps(contract), encoding="utf-8")

    with patch("agent_reach.narrative.service.NarrativeService", return_value=_NarrativeStub()):
        with patch(
            "sys.argv",
            [
                "agent-reach",
                "radar-narrative",
                "contract",
                "--payload",
                str(payload_path),
                "--json",
            ],
        ):
            main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "evt_fixture"
    assert payload["resolution_source"] == "quant_prices"


def test_narrative_forecast_hides_unqualified_probability(capsys):
    with patch("agent_reach.narrative.service.NarrativeService", return_value=_NarrativeStub()):
        with patch(
            "sys.argv",
            [
                "agent-reach",
                "radar-narrative",
                "forecast",
                "--contract-id",
                "evt_fixture",
            ],
        ):
            main()

    output = capsys.readouterr().out
    assert "資料不足" in output
    assert "校準機率" not in output


def test_research_cli_prints_frozen_pack(capsys):
    with patch("agent_reach.narrative.service.NarrativeService", return_value=_NarrativeStub()):
        with patch("agent_reach.narrative.research.ResearchService", return_value=_ResearchStub()):
            with patch(
                "sys.argv",
                [
                    "agent-reach",
                    "radar-narrative",
                    "research",
                    "--slice",
                    "cpo-external-laser",
                    "--as-of",
                    "2026-08-30",
                ],
            ):
                main()

    output = capsys.readouterr().out
    assert "ResearchPack pack_fixture" in output
    assert "grade=E" in output


def test_daily_sync_has_separate_two_day_default(capsys):
    with patch("agent_reach.narrative.service.NarrativeService", return_value=_NarrativeStub()):
        with patch("agent_reach.narrative.research.ResearchService", return_value=_ResearchStub()):
            with patch(
                "sys.argv",
                ["agent-reach", "radar-narrative", "daily-sync", "--json"],
            ):
                main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["serenity_days"] == 2


def test_serenity_cli_routes_jsonl_and_method_threshold(capsys, tmp_path):
    archive = tmp_path / "posts.jsonl"
    archive.write_text("", encoding="utf-8")
    with patch("agent_reach.narrative.service.NarrativeService", return_value=_NarrativeStub()):
        with patch("agent_reach.narrative.research.ResearchService", return_value=_ResearchStub()):
            with patch(
                "sys.argv",
                [
                    "agent-reach", "radar-narrative", "serenity-backfill",
                    "--serenity-jsonl", str(archive), "--days", "90", "--count", "50",
                    "--json",
                ],
            ):
                main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_jsonl"] == str(archive)
    assert payload["count"] == 50

    with patch("agent_reach.narrative.service.NarrativeService", return_value=_NarrativeStub()):
        with patch("agent_reach.narrative.research.ResearchService", return_value=_ResearchStub()):
            with patch(
                "sys.argv",
                [
                    "agent-reach", "radar-narrative", "serenity-methodology",
                    "--min-posts", "3", "--as-of", "2026-08-31", "--json",
                ],
            ):
                main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["min_independent_posts"] == 3
    assert payload["persist"] is True


def test_sec_sync_routes_explicit_identity_and_as_of(capsys):
    with patch("agent_reach.narrative.service.NarrativeService", return_value=_NarrativeStub()):
        with patch(
            "agent_reach.narrative.official.OfficialSourceAdapter",
            return_value=_OfficialStub(),
        ):
            with patch(
                "sys.argv",
                [
                    "agent-reach", "radar-narrative", "sec-sync", "--ticker", "LITE",
                    "--cik", "1234567", "--as-of", "2026-08-30", "--count", "12",
                    "--user-agent", "Agent Reach analyst@example.com", "--json",
                ],
            ):
                main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["ticker"] == "LITE"
    assert payload["as_of"] == "2026-08-30"
    assert payload["limit"] == 12
    assert payload["claims_created"] == 0
