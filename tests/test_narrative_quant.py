# -*- coding: utf-8 -*-
"""Read-only, point-in-time Quant adapter tests using an NVDA fixture."""

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from agent_reach.narrative.quant import QuantAdapter


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _snapshot(root: Path):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.fixture()
def quant_root(tmp_path):
    root = tmp_path / "quant"
    prices = root / "lake" / "finviz" / "prices" / "NVDA.csv"
    prices.parent.mkdir(parents=True)
    start = date.today() - timedelta(days=39)
    rows = ["Date,Open,High,Low,Close,Volume"]
    for index in range(40):
        day = start + timedelta(days=index)
        close = 100 + index
        rows.append(f"{day.isoformat()},{close},{close},{close},{close},1000000")
    prices.write_text("\n".join(rows), encoding="utf-8")

    _write_json(
        root / "lake" / "fundamentals_sec_m25" / "NVDA.json",
        {
            "as_of": date.today().isoformat(),
            "schema_version": "1",
            "source": "SEC",
            "is_point_in_time": True,
        },
    )
    _write_json(
        root / "reports" / "factors" / "NVDA" / "latest.json",
        {
            "as_of": date.today().isoformat(),
            "schema_version": "1",
            "is_point_in_time": False,
            "artifact_path": "runs/missing.json",
            "leakage_checks": {"passed": False, "failed": ["future_prices"]},
            "factors": {"momentum": 1.2},
        },
    )
    return root


def test_nvda_dossier_detects_pointer_pit_and_leakage_issues_without_writes(quant_root):
    before = _snapshot(quant_root)
    dossier = QuantAdapter(quant_root).dossier("NVDA")
    after = _snapshot(quant_root)

    assert before == after
    assert dossier["read_only"] is True
    assert dossier["prices"]["exists"] is True
    assert dossier["prices"]["observations"] == 40
    assert dossier["evidence_grade"] == "degraded"
    joined = " | ".join(dossier["issues"])
    assert "missing artifact" in joined
    assert "non-point-in-time" in joined
    assert "failed leakage" in joined


def test_price_lookup_never_uses_bar_after_resolution_date(quant_root):
    target = (date.today() - timedelta(days=10)).isoformat()
    result = QuantAdapter(quant_root).price_on_or_before("NVDA", target)

    assert result["status"] == "ok"
    assert result["date"] <= target
    assert result["point_in_time"] is True


def test_invalid_schema_and_root_escape_are_explicit(quant_root, tmp_path):
    malformed = quant_root / "reports" / "validation" / "ticker" / "NVDA" / "latest.json"
    _write_json(
        malformed,
        {"as_of": date.today().isoformat(), "schema_version": [], "is_point_in_time": True},
    )
    adapter = QuantAdapter(quant_root)
    result = adapter.read_json_artifact(malformed)

    assert result["freshness"] == "invalid"
    assert "schema_version must be a string or integer" in result["issues"]

    with pytest.raises(ValueError, match="escapes configured root"):
        adapter.read_json_artifact(tmp_path / "outside.json")


def test_missing_price_artifact_is_insufficient(tmp_path):
    dossier = QuantAdapter(tmp_path / "empty-quant").dossier("NVDA")

    assert dossier["evidence_grade"] == "insufficient"
    assert "price file missing" in dossier["issues"]
