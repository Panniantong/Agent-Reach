# -*- coding: utf-8 -*-
"""Synthetic walk-forward calibration and publication-gate tests."""

from datetime import date, timedelta

import pytest

import agent_reach.narrative.calibration as calibration


def _samples(count=80):
    start = date(2020, 1, 1)
    return [
        {
            "as_of": (start + timedelta(days=index)).isoformat(),
            "outcome_observed_at": (start + timedelta(days=index + 1)).isoformat(),
            "outcome": index % 2,
            "features": {"driver": float(index % 2), "level": float(index)},
        }
        for index in range(count)
    ]


def _perfect_candidates(samples, _current_features):
    outcomes = [row["outcome"] for row in samples]
    predictions = [0.9 if outcome else 0.1 for outcome in outcomes]
    return [("fixture_perfect", list(range(len(samples))), predictions, 0.8)]


def test_probability_is_published_only_after_skill_and_width_gate(monkeypatch):
    monkeypatch.setattr(calibration, "_sklearn_candidates", _perfect_candidates)

    result = calibration.calibrated_forecast(_samples(80), {"driver": 1.0})

    assert result.probability_status == "calibrated"
    assert result.model_name == "fixture_perfect"
    assert result.skill_ci_low > 0
    assert result.upper_bound - result.lower_bound <= 0.40
    assert result.metrics["gate"]["passed"] is True
    assert result.metrics["llm_involvement"] == "none"


def test_wide_interval_hides_numeric_probability(monkeypatch):
    monkeypatch.setattr(calibration, "_sklearn_candidates", _perfect_candidates)

    result = calibration.calibrated_forecast(_samples(8), {"driver": 1.0})
    payload = result.to_dict()

    assert result.metrics["probability_interval_width"] > 0.40
    assert payload["probability_status"] == "insufficient_data"
    assert payload["probability"] is None
    assert payload["lower_bound"] is None
    assert payload["upper_bound"] is None


def test_unskilled_base_rate_never_leaks_a_point_estimate(monkeypatch):
    monkeypatch.setattr(calibration, "_sklearn_candidates", lambda *_args: [])

    result = calibration.calibrated_forecast(_samples(40), {"driver": 1.0})

    assert result.model_name == "smoothed_base_rate"
    assert result.probability_status == "insufficient_data"
    assert result.to_dict()["probability"] is None


@pytest.mark.parametrize("forbidden", sorted(calibration.FORBIDDEN_HISTORICAL_KEYS))
def test_historical_feature_pollution_is_rejected(forbidden):
    samples = _samples(4)
    samples[0]["features"][forbidden] = 0.7

    with pytest.raises(ValueError, match="historical feature pollution"):
        calibration.calibrated_forecast(samples)


def test_outcome_must_be_observed_after_feature_cutoff():
    samples = _samples(4)
    samples[0]["outcome_observed_at"] = samples[0]["as_of"]

    with pytest.raises(ValueError, match="must be later"):
        calibration.calibrated_forecast(samples)
