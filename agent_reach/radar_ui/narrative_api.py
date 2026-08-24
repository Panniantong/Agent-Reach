# -*- coding: utf-8 -*-
"""FastAPI route registration for the local-only narrative workbench."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from agent_reach.narrative.ingest import MAX_IMPORT_BYTES
from agent_reach.narrative.service import NarrativeService


def register_narrative_routes(app, jobs, service: Optional[NarrativeService] = None) -> None:
    from fastapi import Body, HTTPException, Request

    narrative = service or NarrativeService()
    app.state.narrative = narrative

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
