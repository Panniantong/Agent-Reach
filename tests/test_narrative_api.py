# -*- coding: utf-8 -*-
"""FastAPI, background-job, SSE, and Radar narrative UI acceptance tests."""

import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import agent_reach.radar_ui.server as srv  # noqa: E402
from agent_reach.narrative.quant import QuantAdapter  # noqa: E402
from agent_reach.narrative.service import NarrativeService  # noqa: E402
from agent_reach.narrative.store import NarrativeStore  # noqa: E402


@pytest.fixture()
def narrative_client(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_reach.radar_ui.jobs.JOBS_DIR", tmp_path / "jobs")
    service = NarrativeService(
        NarrativeStore(tmp_path / "narrative"),
        QuantAdapter(tmp_path / "quant"),
    )
    return TestClient(srv.create_app(narrative_service=service))


def _wait_for_job(client, job_id):
    for _ in range(100):
        row = client.get(f"/api/jobs/{job_id}").json()
        if row["status"] in {"done", "error"}:
            return row
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {job_id}")


def test_narrative_import_review_contract_and_insufficient_forecast(narrative_client):
    imported = narrative_client.post(
        "/api/narrative/imports",
        json={
            "text": "因為 AI 伺服器需求上升，NVDA 2027 年價格可能上漲，但仍需要 Quant 支持。",
            "title": "Serenity note",
            "ticker": "NVDA",
            "domain": "information-technology",
        },
    )
    assert imported.status_code == 200
    claim = imported.json()["claims"][0]
    assert claim["verification_state"] == "pending"

    denied = narrative_client.post(
        f"/api/narrative/claims/{claim['id']}/review",
        json={
            "verification_state": "verified",
            "tag": "KNOWN",
            "confidence": "HIGH",
            "reviewer": "tester",
            "reason": "no evidence",
            "evidence": [],
        },
    )
    assert denied.status_code == 400

    approved = narrative_client.post(
        "/api/narrative/claims/review",
        json={
            "verification_state": "verified",
            "tag": "COMPUTED",
            "claim_id": claim["id"],
            "confidence": "HIGH",
            "reviewer": "tester",
            "reason": "fixture artifact",
            "evidence": [{"kind": "quant", "verified": True, "artifact": "NVDA.csv"}],
        },
    )
    assert approved.status_code == 200

    contract = narrative_client.post(
        "/api/narrative/contracts",
        json={
            "scope_type": "ticker",
            "scope_id": "NVDA",
            "domain": "information-technology",
            "horizon": "1y",
            "statement": "NVDA closes above 200 at resolution.",
            "resolution_date": "2027-06-30",
            "criteria": {"type": "price_above", "threshold": 200},
            "resolution_source": "quant_prices",
            "dependency_ids": ["unmodelled-demand-event"],
        },
    ).json()

    submitted = narrative_client.post(
        "/api/narrative/forecasts",
        json={"contract_id": contract["id"], "samples": []},
    ).json()
    job = _wait_for_job(narrative_client, submitted["id"])

    assert job["status"] == "done"
    forecast = job["result"]["forecast"]
    assert forecast["probability_status"] == "insufficient_data"
    assert forecast["probability"] is None
    assert forecast["lower_bound"] is None
    assert forecast["upper_bound"] is None

    with narrative_client.stream("GET", f"/api/jobs/{submitted['id']}/log") as response:
        stream_text = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: end" in stream_text


def test_status_industry_company_and_history_endpoints(narrative_client):
    status = narrative_client.get("/api/narrative/status").json()
    dashboard = narrative_client.get("/api/narrative/dashboard").json()
    company = narrative_client.get("/api/narrative/company/NVDA").json()
    board = narrative_client.get("/api/narrative/board/NVDA?horizon=1y").json()
    history = narrative_client.get("/api/narrative/history").json()

    assert status["store"]["schema_version"] == 2
    assert status["quant"]["mode"] == "read_only"
    assert len(dashboard["sectors"]) == 11
    assert dashboard["macro"]["name"] == "Macro"
    assert dashboard["crypto"]["name"] == "Crypto"
    assert company["ticker"] == "NVDA"
    assert company["quant"]["evidence_grade"] == "insufficient"
    assert board["ticker"] == "NVDA"
    assert board["scenarios"]
    assert all(row["probability"] is None for row in board["scenarios"])
    assert history["episodes"]
    assert all(episode["post_hoc"] for episode in history["episodes"])


def test_discovery_results_stay_pending_until_review(narrative_client, monkeypatch):
    service = narrative_client.app.state.narrative
    candidates = service.store.add_discovery_candidates(
        query="NVDA supply chain",
        domain="information-technology",
        candidates=[
            {
                "url": "https://example.com/nvda",
                "title": "Candidate",
                "snippet": "not evidence yet",
                "source": "exa",
            }
        ],
    )

    pending = narrative_client.get("/api/narrative/discovery").json()["candidates"]

    assert pending[0]["id"] == candidates[0]["id"]
    assert pending[0]["status"] == "pending"
    assert service.store.list_claims() == []


def test_narrative_ui_has_eight_workspaces_and_responsive_accessibility(narrative_client):
    index = narrative_client.get("/").text
    script = narrative_client.get("/static/narrative.js").text
    styles = narrative_client.get("/static/narrative.css").text

    assert "/static/narrative.css" in index
    assert "/static/narrative.js" in index
    for label in ("總覽", "產業", "公司", "來源", "歷史", "推演", "結算", "校準"):
        assert label in script
    assert 'role="tablist"' in script
    assert "aria-selected" in script
    assert "LIVE RESEARCH BOARD" in script
    assert "nr-scenario-rail" in styles
    assert "nr-workbench" in styles
    assert "@media (max-width: 680px)" in styles
    assert "prefers-reduced-motion" in styles
