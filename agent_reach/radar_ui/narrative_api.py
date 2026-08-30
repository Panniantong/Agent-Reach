# -*- coding: utf-8 -*-
"""FastAPI route registration for the local-only narrative workbench."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from agent_reach.narrative.ingest import MAX_IMPORT_BYTES
from agent_reach.narrative.research import ResearchService
from agent_reach.narrative.service import NarrativeService


def register_narrative_routes(app, jobs, service: Optional[NarrativeService] = None) -> None:
    from fastapi import Body, HTTPException, Request

    narrative = service or NarrativeService()
    research = ResearchService(store=narrative.store, quant=narrative.quant)
    app.state.narrative = narrative
    app.state.research = research

    def fail(exc: Exception):
        if isinstance(exc, LookupError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if isinstance(exc, (ValueError, FileNotFoundError)):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise exc

    @app.get("/api/narrative/status")
    def narrative_status():
        return narrative.status()

    @app.get("/api/narrative/imports")
    def narrative_imports(limit: int = 100):
        return {"documents": narrative.store.list_documents(limit=limit)}

    @app.post("/api/narrative/imports")
    def narrative_import(payload: dict = Body(...)):
        try:
            return narrative.ingest(
                text=str(payload.get("text") or ""),
                url=str(payload.get("url") or ""),
                file_path=str(payload.get("file_path") or ""),
                title=str(payload.get("title") or ""),
                source_id=str(payload.get("source_id") or ""),
                domain=str(payload.get("domain") or ""),
                ticker=str(payload.get("ticker") or ""),
                published_at=str(payload.get("published_at") or ""),
                as_of=str(payload.get("as_of") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.post("/api/narrative/imports/file")
    async def narrative_import_file(
        request: Request,
        filename: str,
        source_id: str = "",
        domain: str = "",
        ticker: str = "",
        published_at: str = "",
        as_of: str = "",
    ):
        suffix = Path(filename).suffix.lower()
        if suffix not in {".md", ".txt", ".pdf", ".csv", ".json", ".vtt"}:
            raise HTTPException(status_code=400, detail=f"unsupported file type: {suffix}")
        content = await request.body()
        if len(content) > MAX_IMPORT_BYTES:
            raise HTTPException(status_code=413, detail="file exceeds 25 MiB import limit")
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
                tmp.write(content)
                tmp.flush()
                return narrative.ingest(
                    file_path=tmp.name,
                    source_id=source_id,
                    domain=domain,
                    ticker=ticker,
                    published_at=published_at,
                    as_of=as_of,
                )
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.get("/api/narrative/claims")
    def narrative_claims(ticker: str = "", domain: str = "", state: str = "", limit: int = 200):
        return {
            "claims": narrative.store.list_claims(
                ticker=ticker, domain=domain, state=state, limit=limit
            )
        }

    @app.post("/api/narrative/claims/{claim_id}/review")
    def narrative_claim_review(claim_id: str, payload: dict = Body(...)):
        try:
            return narrative.store.review_claim(
                claim_id,
                verification_state=str(payload.get("verification_state") or ""),
                tag=str(payload.get("tag") or ""),
                confidence=str(payload.get("confidence") or ""),
                reviewer=str(payload.get("reviewer") or "local-user"),
                reason=str(payload.get("reason") or ""),
                evidence=payload.get("evidence") or [],
            )
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.post("/api/narrative/claims/review")
    def narrative_claim_review_alias(payload: dict = Body(...)):
        claim_id = str(payload.get("claim_id") or "")
        if not claim_id:
            raise HTTPException(status_code=400, detail="claim_id is required")
        return narrative_claim_review(claim_id, payload)

    @app.get("/api/narrative/discovery")
    def narrative_discovery_candidates(status: str = "pending", limit: int = 200):
        return {"candidates": narrative.store.list_discovery_candidates(status=status, limit=limit)}

    @app.post("/api/narrative/discovery")
    def narrative_discover(payload: dict = Body(...)):
        query = str(payload.get("query") or "")
        domain = str(payload.get("domain") or "")
        count = int(payload.get("count") or 8)
        job = jobs.submit(
            "narrative_discovery",
            {"query": query, "domain": domain, "count": count},
            lambda: narrative.discover(query, domain=domain, num_results=count),
        )
        return job.to_dict()

    @app.post("/api/narrative/discovery/{candidate_id}/review")
    def narrative_discovery_review(candidate_id: str, payload: dict = Body(...)):
        try:
            return narrative.review_discovery(
                candidate_id,
                status=str(payload.get("status") or ""),
                ingest_approved=bool(payload.get("ingest")),
                source_id=str(payload.get("source_id") or ""),
                ticker=str(payload.get("ticker") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.get("/api/narrative/contracts")
    def narrative_contracts(scope_id: str = "", horizon: str = ""):
        return {"contracts": narrative.store.list_contracts(scope_id=scope_id, horizon=horizon)}

    @app.post("/api/narrative/contracts")
    def narrative_contract(payload: dict = Body(...)):
        try:
            return narrative.create_contract(payload)
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.get("/api/narrative/forecasts")
    def narrative_forecasts(contract_id: str = "", limit: int = 200):
        return {"forecasts": narrative.store.list_forecasts(contract_id=contract_id, limit=limit)}

    @app.post("/api/narrative/forecasts")
    def narrative_forecast(payload: dict = Body(...)):
        contract_id = str(payload.get("contract_id") or "")
        samples = payload.get("samples") or []
        features = payload.get("current_features") or {}
        as_of = str(payload.get("as_of") or "")
        job = jobs.submit(
            "narrative_forecast",
            {"contract_id": contract_id, "sample_count": len(samples), "as_of": as_of},
            lambda: narrative.forecast(
                contract_id,
                samples=samples,
                current_features=features,
                as_of=as_of,
            ),
        )
        return job.to_dict()

    @app.get("/api/narrative/resolutions")
    def narrative_resolutions(contract_id: str = ""):
        return {"resolutions": narrative.store.list_resolutions(contract_id=contract_id)}

    @app.post("/api/narrative/resolutions")
    def narrative_resolution(payload: dict = Body(...)):
        contract_id = str(payload.get("contract_id") or "")
        try:
            if payload.get("kind") == "human_override":
                return narrative.human_override(
                    contract_id,
                    outcome=int(payload.get("outcome")),
                    reason=str(payload.get("reason") or ""),
                    actor=str(payload.get("actor") or "local-user"),
                    forecast_id=str(payload.get("forecast_id") or ""),
                    values=payload.get("values") or {},
                )
            return narrative.auto_resolve(
                contract_id,
                actor=str(payload.get("actor") or "narrative-auto"),
            )
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.get("/api/narrative/sources")
    def narrative_sources(domain: str = "", horizon: str = ""):
        return narrative.sources(domain=domain, horizon=horizon)

    @app.get("/api/narrative/dashboard")
    def narrative_dashboard():
        return narrative.dashboard()

    @app.get("/api/narrative/company/{ticker}")
    def narrative_company(ticker: str):
        try:
            return narrative.company(ticker)
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.get("/api/narrative/board/{ticker}")
    def narrative_board(ticker: str, horizon: str = "1y"):
        try:
            return narrative.scenario_board(ticker, horizon=horizon)
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.get("/api/narrative/history")
    def narrative_history():
        return narrative.history()

    @app.get("/api/narrative/calibration")
    def narrative_calibration_list(domain: str = "", horizon: str = ""):
        return {"snapshots": narrative.store.list_calibration(domain=domain, horizon=horizon)}

    @app.post("/api/narrative/calibration")
    def narrative_calibration_run(payload: dict = Body(...)):
        domain = str(payload.get("domain") or "")
        horizon = str(payload.get("horizon") or "")
        as_of = str(payload.get("as_of") or "")
        job = jobs.submit(
            "narrative_calibration",
            {"domain": domain, "horizon": horizon, "as_of": as_of},
            lambda: narrative.calibrate(domain=domain, horizon=horizon, as_of=as_of),
        )
        return job.to_dict()

    @app.get("/api/narrative/research/themes")
    def narrative_research_themes():
        return {"themes": research.themes()}

    @app.get("/api/narrative/research/packs")
    def narrative_research_packs(slice_id: str = "", limit: int = 100):
        return {"packs": research.packs(slice_id=slice_id, limit=limit)}

    @app.get("/api/narrative/research/packs/{pack_id}")
    def narrative_research_pack(pack_id: str):
        try:
            return research.pack(pack_id)
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.get("/api/narrative/research/packs/{pack_id}/diff")
    def narrative_research_pack_diff(pack_id: str, base: str = ""):
        try:
            return research.pack_diff(pack_id, base_id=base)
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.post("/api/narrative/research/runs")
    def narrative_research_run(payload: dict = Body(...)):
        slice_id = str(payload.get("slice") or payload.get("slice_id") or "")
        as_of = str(payload.get("as_of") or "")
        job = jobs.submit(
            "narrative_research",
            {"slice": slice_id, "as_of": as_of},
            lambda: research.run_research(slice_id, as_of=as_of, freeze=True),
        )
        return job.to_dict()

    @app.post("/api/narrative/research/serenity-backfill")
    def narrative_serenity_backfill(payload: dict = Body(default={})):
        days = int(payload.get("days") or 90)
        count = int(payload.get("count") or 2000)
        translations = payload.get("translations") or {}
        job = jobs.submit(
            "serenity_backfill",
            {"days": days, "count": count},
            lambda: research.serenity_backfill(
                days=days, count=count, translations=translations
            ),
        )
        return job.to_dict()

    @app.get("/api/narrative/research/companies/{ticker}")
    def narrative_research_company(ticker: str):
        try:
            return research.company(ticker)
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.get("/api/narrative/research/graphs/{run_id}")
    def narrative_research_graphs(run_id: str):
        return {
            "graphs": [
                research.store.get_graph(row["id"])
                for row in research.store.list_graphs(run_id=run_id)
            ]
        }

    @app.post("/api/narrative/research/graphs/edges/{edge_id}/review")
    def narrative_research_edge_review(edge_id: str, payload: dict = Body(...)):
        try:
            return research.store.review_graph_edge(
                edge_id,
                state=str(payload.get("state") or ""),
                tag=str(payload.get("tag") or "GUESS"),
                confidence=str(payload.get("confidence") or "LOW"),
                reviewer=str(payload.get("reviewer") or "local-user"),
                reason=str(payload.get("reason") or ""),
                evidence=payload.get("evidence") or [],
            )
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.get("/api/narrative/research/relationships")
    def narrative_research_relationships(run_id: str = "", ticker: str = ""):
        return research.relationships(run_id=run_id, ticker=ticker)

    @app.post("/api/narrative/research/relationships")
    def narrative_research_relationship_contract(payload: dict = Body(...)):
        try:
            return research.create_relationship_contract(payload)
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.get("/api/narrative/research/bottlenecks")
    def narrative_research_bottlenecks(run_id: str = "", status: str = ""):
        try:
            return {"bottlenecks": research.store.list_bottlenecks(run_id=run_id, status=status)}
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.post("/api/narrative/research/bottlenecks/{bottleneck_id}/review")
    def narrative_research_bottleneck_review(
        bottleneck_id: str, payload: dict = Body(...)
    ):
        try:
            return research.store.transition_bottleneck(
                bottleneck_id,
                status=str(payload.get("status") or ""),
                reviewer=str(payload.get("reviewer") or "local-user"),
                reason=str(payload.get("reason") or ""),
                dimensions=payload.get("dimensions") or {},
                evidence_claim_ids=payload.get("evidence_claim_ids") or [],
            )
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.get("/api/narrative/research/live")
    def narrative_research_live(limit: int = 100):
        return research.live(limit=limit)

    @app.get("/api/narrative/research/monitor")
    def narrative_research_monitor():
        return research.monitor()

    @app.get("/api/narrative/research/coverage")
    def narrative_research_coverage(run_id: str = "", source_id: str = ""):
        return research.coverage(run_id=run_id, source_id=source_id)

    @app.post("/api/narrative/research/stress-tests")
    def narrative_research_stress_test(payload: dict = Body(...)):
        try:
            return research.stress_test(
                str(payload.get("pack_id") or ""),
                str(payload.get("question") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            fail(exc)

    @app.post("/api/narrative/research/daily-sync")
    def narrative_research_daily_sync(payload: dict = Body(default={})):
        as_of = str(payload.get("as_of") or "")
        serenity_days = int(payload.get("serenity_days") or 2)
        job = jobs.submit(
            "narrative_daily_sync",
            {"as_of": as_of, "serenity_days": serenity_days},
            lambda: research.daily_sync(as_of=as_of, serenity_days=serenity_days),
        )
        return job.to_dict()

    @app.post("/api/narrative/research/weekly-freeze")
    def narrative_research_weekly_freeze(payload: dict = Body(default={})):
        as_of = str(payload.get("as_of") or "")
        job = jobs.submit(
            "narrative_weekly_freeze",
            {"as_of": as_of},
            lambda: research.weekly_freeze(as_of=as_of),
        )
        return job.to_dict()
