# -*- coding: utf-8 -*-
"""FastAPI backend for the radar console. Local tool: bind 127.0.0.1 only.

Endpoints are thin adapters over existing pipeline functions; every trigger
runs as a background job (jobs.py) whose log streams to the UI via SSE.
File access is path-jailed to the known output dirs (plain name only, .md/
.json only).
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_reach.config import Config
from agent_reach.radar import PLATFORMS, RADAR_DIR
from agent_reach.radar_ui.jobs import JobManager

STATIC_DIR = Path(__file__).parent / "static"

FILE_DIRS: dict[str, Path] = {
    "digests": RADAR_DIR,
    "deepdive": RADAR_DIR / "deepdive",
    "reports": RADAR_DIR / "reports",
    "summaries": RADAR_DIR / "summaries",
    "social": RADAR_DIR / "social",
    "wiki": Path(__file__).parent.parent / "knowledge" / "wiki",
    "wiki-drafts": RADAR_DIR / "wiki" / "drafts",
}

# Built-in pipeline actions rendered as trigger cards next to the scenarios.
BUILTIN_ACTIONS = [
    {"id": "deepdive", "label": "arXiv 深讀（tier-2）", "desc": "掃描摘要後全文蒸餾 top 論文",
     "params": [{"name": "topic", "label": "主題", "default": "all",
                 "choices": ["all", "ai", "ee", "rf", "spacetech", "quantum"]}],
     "required_providers": [], "ready": True, "missing": [], "builtin": True},
    {"id": "wiki_update", "label": "Wiki 更新起草", "desc": "把今日材料合併進主題 wiki draft",
     "params": [{"name": "topic", "label": "主題（空=全部）", "default": "", "choices": None}],
     "required_providers": [], "ready": True, "missing": [], "builtin": True},
    {"id": "notebooklm_sync", "label": "NotebookLM 同步", "desc": "推送高分論文+深讀到每主題 notebook",
     "params": [{"name": "dry_run", "label": "dry-run", "default": "true",
                 "choices": ["true", "false"]}],
     "required_providers": ["notebooklm"], "ready": None, "missing": [], "builtin": True},
]


def _jail(dir_key: str, name: str) -> Path:
    """Resolve a file inside a known dir; reject traversal and odd types."""
    base = FILE_DIRS.get(dir_key)
    if base is None:
        raise LookupError(f"unknown dir: {dir_key}")
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise LookupError("bad file name")
    path = (base / name).resolve()
    if path.parent != base.resolve() or path.suffix not in (".md", ".json"):
        raise LookupError("path escapes jail")
    return path


def _run_builtin(action: str, params: dict) -> dict:
    """Execute a built-in action synchronously (called inside a job thread)."""
    topic = str(params.get("topic") or "").strip()
    if action == "deepdive":
        from agent_reach.radar import load_sources
        from agent_reach.radar_arxiv import collect_arxiv, run_deep_dive

        sources = load_sources()
        papers = collect_arxiv(sources, Config())
        if not papers:
            return {"ok": False, "error": "沒有命中論文"}
        paths = run_deep_dive(papers, sources, topic=None if topic in ("", "all") else topic)
        return {"ok": True, "outputs": [str(p) for p in paths],
                "summary": f"深讀 {len(paths)} 篇"}
    if action == "wiki_update":
        from agent_reach.radar_wiki import run_wiki_update

        results = run_wiki_update(topics=[topic] if topic else None)
        drafted = {t: p for t, p in results.items() if p}
        return {"ok": True, "outputs": list(drafted.values()),
                "summary": f"起草 {len(drafted)} 個主題 draft"}
    if action == "notebooklm_sync":
        from agent_reach.integrations.notebooklm_sync import run_sync

        dry = str(params.get("dry_run", "true")).lower() != "false"
        return run_sync(dry_run=dry)
    return {"ok": False, "error": f"unknown builtin: {action}"}


def create_app(narrative_service=None):
    from fastapi import Body, FastAPI, HTTPException
    from fastapi.responses import FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="Agent Reach // Radar Console", docs_url=None, redoc_url=None)
    jobs = JobManager()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.state.jobs = jobs
    from agent_reach.radar_ui.narrative_api import register_narrative_routes

    register_narrative_routes(app, jobs, narrative_service)

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/overview")
    def overview():
        latest = RADAR_DIR / "latest.md"
        sidecar = RADAR_DIR / "latest-items.json"
        info: dict = {"latest_digest": latest.exists(), "generated_at": "", "counts": {}}
        if sidecar.exists():
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                info["generated_at"] = data.get("generated_at", "")
                info["counts"] = {k: len(v) for k, v in (data.get("items") or {}).items()}
            except Exception:  # noqa: BLE001
                pass
        return info

    @app.get("/api/providers")
    def providers():
        from agent_reach.llm import providers_status

        return providers_status(probe=True)

    @app.get("/api/platforms")
    def platforms():
        return [{"name": n, **spec} for n, spec in PLATFORMS.items()]

    @app.get("/api/scenarios")
    def scenarios():
        from agent_reach.llm import providers_status
        from agent_reach.radar_scenarios import scenarios_manifest

        status = providers_status(probe=True)
        cards = scenarios_manifest(status)
        actions = []
        for a in BUILTIN_ACTIONS:
            a = dict(a)
            missing = [p for p in a["required_providers"] if not status.get(p, {}).get("ok")]
            a["missing"] = missing
            a["ready"] = not missing
            actions.append(a)
        return {"scenarios": cards, "actions": actions}

    @app.post("/api/collect")
    def collect(payload: dict = Body(...)):
        platforms_sel = [str(p) for p in (payload.get("platforms") or [])] or None

        def _do():
            from agent_reach.radar import run_radar

            out, grouped = run_radar(platforms=platforms_sel)
            return {"ok": True, "digest": str(out),
                    "counts": {k: len(v) for k, v in grouped.items()}}

        job = jobs.submit("collect", {"platforms": platforms_sel}, _do)
        return job.to_dict()

    @app.post("/api/run")
    def run(payload: dict = Body(...)):
        target = str(payload.get("scenario") or "")
        params = payload.get("params") or {}
        from agent_reach.radar_scenarios import SCENARIOS

        if target in SCENARIOS:
            from agent_reach.radar_scenarios import run_scenario

            job = jobs.submit(target, params, lambda: run_scenario(target, params))
        elif target in {a["id"] for a in BUILTIN_ACTIONS}:
            job = jobs.submit(target, params, lambda: _run_builtin(target, params))
        else:
            raise HTTPException(status_code=404, detail=f"unknown scenario: {target}")
        return job.to_dict()

    @app.get("/api/files")
    def files(dir: str):
        base = FILE_DIRS.get(dir)
        if base is None:
            raise HTTPException(status_code=404, detail=f"unknown dir: {dir}")
        out = []
        if base.is_dir():
            for p in base.iterdir():
                if p.is_file() and p.suffix in (".md", ".json") and not p.name.startswith("."):
                    st = p.stat()
                    out.append({"name": p.name, "mtime": int(st.st_mtime), "size": st.st_size})
        out.sort(key=lambda f: f["mtime"], reverse=True)
        return out

    @app.get("/api/file")
    def file(dir: str, name: str):
        try:
            path = _jail(dir, name)
        except LookupError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return {"name": name, "content": path.read_text(encoding="utf-8")}

    @app.get("/api/jobs")
    def jobs_list():
        return jobs.list()

    @app.get("/api/jobs/{job_id}")
    def job_get(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return job.to_dict(with_log=True)

    @app.get("/api/jobs/{job_id}/log")
    def job_log(job_id: str):
        return StreamingResponse(jobs.stream(job_id), media_type="text/event-stream")

    return app
