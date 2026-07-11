# -*- coding: utf-8 -*-
"""Console server tests. Whole file skips when the [ui] extra isn't installed
(fastapi/httpx) so the core suite — and evolve's pytest gate — stay green."""

import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import agent_reach.radar_ui.server as srv  # noqa: E402
from agent_reach.radar_ui.jobs import JobManager  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "ee.md").write_text("# EE wiki", encoding="utf-8")
    (tmp_path / "latest.md").write_text("# digest", encoding="utf-8")
    monkeypatch.setitem(srv.FILE_DIRS, "digests", tmp_path)
    monkeypatch.setitem(srv.FILE_DIRS, "wiki", wiki)
    return TestClient(srv.create_app())


def test_platforms_and_scenarios_serializable(client, monkeypatch):
    import agent_reach.llm as llm_mod

    monkeypatch.setattr(llm_mod, "providers_status",
                        lambda config=None, probe=False: {"ollama": {"ok": True, "detail": ""}})
    plats = client.get("/api/platforms").json()
    assert {p["name"] for p in plats} >= {"twitter", "arxiv", "finviz"}
    data = client.get("/api/scenarios").json()
    assert {s["id"] for s in data["scenarios"]} == {
        "arxiv_expert_report", "x_guru_summary", "github_trending_post", "market_signal_post"}
    assert {a["id"] for a in data["actions"]} == {"deepdive", "wiki_update", "notebooklm_sync"}


def test_files_listing_and_read(client):
    names = [f["name"] for f in client.get("/api/files", params={"dir": "wiki"}).json()]
    assert names == ["ee.md"]
    body = client.get("/api/file", params={"dir": "wiki", "name": "ee.md"}).json()
    assert body["content"] == "# EE wiki"


def test_path_jail_rejects_traversal(client):
    for bad in ("../secrets.md", "..\\x.md", ".hidden.md", "x.py"):
        r = client.get("/api/file", params={"dir": "wiki", "name": bad})
        assert r.status_code == 400, bad
    assert client.get("/api/files", params={"dir": "nope"}).status_code == 404
    assert client.get("/api/file", params={"dir": "nope", "name": "a.md"}).status_code == 400


def test_run_unknown_scenario_404(client):
    r = client.post("/api/run", json={"scenario": "nope", "params": {}})
    assert r.status_code == 404


def test_job_lifecycle_and_log_capture(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_reach.radar_ui.jobs.JOBS_DIR", tmp_path / "jobs")
    mgr = JobManager(workers=1)

    def work():
        from loguru import logger
        logger.info("步驟一")
        return {"ok": True, "outputs": ["x.md"]}

    job = mgr.submit("test", {}, work)
    for _ in range(50):
        if job.status == "done":
            break
        time.sleep(0.05)
    assert job.status == "done"
    assert any("步驟一" in ln for ln in job.log)
    assert (tmp_path / "jobs" / f"{job.id}.json").exists()

    # error path: fn raising must mark error, never propagate
    bad = mgr.submit("boom", {}, lambda: (_ for _ in ()).throw(RuntimeError("炸")))
    for _ in range(50):
        if bad.status == "error":
            break
        time.sleep(0.05)
    assert bad.status == "error" and "炸" in bad.error


def test_collect_endpoint_spawns_job(client, monkeypatch):
    import agent_reach.radar as radar_mod

    monkeypatch.setattr(radar_mod, "run_radar",
                        lambda platforms=None, **k: (srv.FILE_DIRS["digests"] / "latest.md", {}))
    job = client.post("/api/collect", json={"platforms": ["arxiv"]}).json()
    assert job["kind"] == "collect" and job["params"]["platforms"] == ["arxiv"]
    for _ in range(50):
        got = client.get(f"/api/jobs/{job['id']}").json()
        if got["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert got["status"] == "done"
