# -*- coding: utf-8 -*-
"""Point-in-time service orchestration and automatic-resolution tests."""

from datetime import date

import pytest

from agent_reach.narrative.ingest import ingest_text
from agent_reach.narrative.quant import QuantAdapter
from agent_reach.narrative.service import NarrativeService
from agent_reach.narrative.store import NarrativeStore


@pytest.fixture()
def service(tmp_path):
    return NarrativeService(
        NarrativeStore(tmp_path / "narrative"),
        QuantAdapter(tmp_path / "quant"),
    )


def _contract(service, *, resolution_date="2027-06-30"):
    return service.create_contract(
        {
            "scope_type": "ticker",
            "scope_id": "NVDA",
            "domain": "information-technology",
            "horizon": "1y",
            "statement": "NVDA closes above 200 at resolution.",
            "resolution_date": resolution_date,
            "resolution_source": "quant_prices",
            "criteria": {"operator": "price_above", "threshold": 200},
            "source_ids": ["serenity_aleabitoreddit"],
        }
    )


def test_forecast_excludes_claim_observed_after_cutoff(service):
    imported = ingest_text(
        service.store,
        text="因為供應限制改善，NVDA 2027 年價格可能上升，但這是較晚才出現的觀點。",
        source_id="serenity_aleabitoreddit",
        ticker="NVDA",
        domain="information-technology",
        as_of="2026-09-01",
    )
    service.store.review_claim(
        imported["claims"][0]["id"],
        verification_state="verified",
        tag="KNOWN",
        confidence="HIGH",
        reviewer="tester",
        reason="official fixture",
        evidence=[{"kind": "official", "verified": True, "url": "https://example.com"}],
    )
    contract = _contract(service)

    result = service.forecast(contract["id"], samples=[], as_of="2026-08-24")

    assert result["forecast"]["probability_status"] == "insufficient_data"
    assert result["forecast"]["evidence"] == []


def test_forecast_rejects_outcome_not_observable_at_issue_time(service):
    contract = _contract(service)
    samples = [
        {
            "as_of": "2025-01-01",
            "outcome_observed_at": "2026-09-01",
            "outcome": 1,
            "features": {"driver": 1.0},
        },
        {
            "as_of": "2025-02-01",
            "outcome_observed_at": "2026-09-02",
            "outcome": 0,
            "features": {"driver": 0.0},
        },
    ]

    with pytest.raises(ValueError, match="not observable"):
        service.forecast(contract["id"], samples=samples, as_of="2026-08-24")


def test_calibration_replay_ignores_forecast_issued_after_resolution(service):
    contract = _contract(service, resolution_date="2026-06-30")
    service.store.add_forecast(
        contract_id=contract["id"],
        as_of="2026-07-01",
        probability_status="calibrated",
        probability=0.9,
        lower_bound=0.8,
        upper_bound=0.95,
        model_name="invalid-future",
        model_version="v1",
        training_cutoff="2026-07-01",
    )
    service.store.add_resolution(
        contract_id=contract["id"],
        outcome=1,
        reason="fixture resolution",
        actor="tester",
    )

    result = service.calibrate(domain="information-technology", horizon="1y")

    assert result["resolved_forecasts"] == 0
    assert result["snapshot"]["metrics"]["eligible"] is False


def test_auto_resolution_uses_last_price_on_or_before_contract_date(tmp_path):
    quant_root = tmp_path / "quant"
    prices = quant_root / "lake" / "finviz" / "prices" / "NVDA.csv"
    prices.parent.mkdir(parents=True)
    prices.write_text(
        "Date,Close,Volume\n2026-08-19,190,10\n2026-08-20,210,10\n2026-08-21,50,10\n",
        encoding="utf-8",
    )
    service = NarrativeService(
        NarrativeStore(tmp_path / "narrative"),
        QuantAdapter(quant_root),
    )
    contract = _contract(service, resolution_date="2026-08-20")

    resolved = service.auto_resolve(contract["id"], actor="tester")

    assert date.fromisoformat(contract["resolution_date"]) <= date.today()
    assert resolved["resolution"]["outcome"] == 1
    assert resolved["resolution"]["values"]["end_bar"]["date"] == "2026-08-20"


def test_robust_opportunities_require_calibrated_high_probability_events():
    base_contract = {
        "scope_type": "ticker",
        "scope_id": "NVDA",
        "horizon": "1y",
        "statement": "AI infrastructure demand remains above threshold.",
        "resolution_date": "2027-06-30",
        "resolution_source": "quant_prices",
        "status": "open",
        "criteria": {
            "operator": "price_above",
            "threshold": 200,
            "beneficiaries": ["NVDA", "AVGO"],
            "victims": ["legacy-vendor"],
            "leading_indicators": ["hyperscaler capex"],
            "invalidation_conditions": ["capex contraction"],
        },
    }
    calibrated = {
        "probability_status": "calibrated",
        "probability": 0.7,
        "lower_bound": 0.6,
        "upper_bound": 0.8,
    }
    first = NarrativeService.decision_card(base_contract, calibrated, {"issues": []}, [])
    second_contract = {
        **base_contract,
        "statement": "Accelerator capacity stays constrained.",
        "criteria": {**base_contract["criteria"], "beneficiaries": ["NVDA"]},
    }
    second = NarrativeService.decision_card(
        second_contract,
        {**calibrated, "probability": 0.65, "lower_bound": 0.55},
        {"issues": []},
        [],
    )
    insufficient = NarrativeService.decision_card(
        base_contract,
        {
            "probability_status": "insufficient_data",
            "probability": None,
            "lower_bound": None,
            "upper_bound": None,
        },
        {"issues": []},
        [],
    )

    rows = NarrativeService.robust_opportunities([first, second, insufficient])

    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["scenario_count"] == 2
    assert rows[0]["min_lower_bound"] == pytest.approx(0.55)
    assert first["risk"]["victims"] == ["legacy-vendor"]
    assert first["watch"] == ["hyperscaler capex"]
    assert first["orders_generated"] is False
