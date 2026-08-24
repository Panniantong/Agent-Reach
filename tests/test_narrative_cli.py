# -*- coding: utf-8 -*-
"""CLI contract tests for radar-narrative."""

import json
from unittest.mock import patch

from agent_reach.cli import main


class _NarrativeStub:
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
