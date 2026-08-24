# -*- coding: utf-8 -*-
"""Application service joining evidence, Quant context, contracts, and calibration."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Optional

from agent_reach.narrative.calibration import (
    MODEL_VERSION,
    calibrated_forecast,
    evaluate_published_forecasts,
)
from agent_reach.narrative.ingest import (
    discover,
    ingest_file,
    ingest_text,
    ingest_url,
)
from agent_reach.narrative.quant import QuantAdapter
from agent_reach.narrative.store import NarrativeStore

ARCHETYPES = (
    "liquidity_discount_rate",
    "demand_shock_forced_adoption",
    "inflation_supply_shock",
    "credit_capex_reflexivity",
    "technology_diffusion_capacity",
    "regulation_geopolitics",
    "valuation_crowding",
    "governance_accounting",
)

_EPISODE_SEEDS = (
    (
        "1970s inflation and supply shocks",
        "1975-01-01",
        "1982-12-31",
        ["inflation_supply_shock", "liquidity_discount_rate"],
    ),
    (
        "Dot-com diffusion and valuation cycle",
        "1995-01-01",
        "2002-12-31",
        ["technology_diffusion_capacity", "valuation_crowding"],
    ),
    (
        "Global credit cycle and financial crisis",
        "2003-01-01",
        "2009-12-31",
        ["credit_capex_reflexivity", "liquidity_discount_rate"],
    ),
    (
        "Pandemic forced adoption and liquidity",
        "2020-01-01",
        "2021-12-31",
        ["demand_shock_forced_adoption", "liquidity_discount_rate"],
    ),
    (
        "Inflation and rapid tightening",
        "2021-01-01",
        "2022-12-31",
        ["inflation_supply_shock", "liquidity_discount_rate"],
    ),
    (
        "AI infrastructure diffusion",
        "2022-01-01",
        "2026-12-31",
        ["technology_diffusion_capacity", "credit_capex_reflexivity"],
    ),
)


def _flatten_numeric(value: Any, prefix: str = "", limit: int = 80) -> dict[str, float]:
    out: dict[str, float] = {}
    if len(out) >= limit:
        return out
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            child_rows = _flatten_numeric(child, name, limit=max(0, limit - len(out)))
            out.update(child_rows)
            if len(out) >= limit:
                break
    elif isinstance(value, bool):
        out[prefix] = float(value)
    elif isinstance(value, (int, float)):
        out[prefix] = float(value)
    return out


class NarrativeService:
    def __init__(
        self, store: Optional[NarrativeStore] = None, quant: Optional[QuantAdapter] = None
    ):
        self.store = store or NarrativeStore()
        self.quant = quant or QuantAdapter()
        self._seed_episode_scaffolds()

    def _seed_episode_scaffolds(self) -> None:
        if self.store.list_episodes():
            return
        for title, start_at, end_at, archetypes in _EPISODE_SEEDS:
            self.store.add_episode(
                title=title,
                start_at=start_at,
                end_at=end_at,
                archetypes=archetypes,
                drivers=[],
                outcomes={},
                evidence=[],
                point_in_time_eligible=False,
                post_hoc=True,
                notes="Descriptive scaffold only; requires approved source pack before evidence use.",
            )

    def status(self) -> dict:
        return {
            "store": self.store.status(),
            "quant": self.quant.status(),
            "rules": {
                "claim_tags": ["KNOWN", "COMPUTED", "INFERRED", "COMMON", "FRAME", "GUESS"],
                "frame_guess_confidence_cap": "LOW",
                "probability_gate": {
                    "skill_interval": "90% bootstrap lower bound > 0",
                    "max_interval_width": 0.40,
                    "unqualified_output": "insufficient_data",
                },
                "llm_probability_allowed": False,
                "orders_generated": False,
            },
        }

    def ingest(
        self,
        *,
        text: str = "",
        url: str = "",
        file_path: str = "",
        title: str = "",
        source_id: str = "",
        domain: str = "",
        ticker: str = "",
        published_at: str = "",
        as_of: str = "",
    ) -> dict:
        supplied = sum(bool(v) for v in (text, url, file_path))
        if supplied != 1:
            raise ValueError("provide exactly one of text, url, or file_path")
        if file_path:
            return ingest_file(
                self.store,
                Path(file_path),
                source_id=source_id,
                domain=domain,
                ticker=ticker,
                published_at=published_at,
                as_of=as_of,
            )
        if url:
            return ingest_url(
                self.store,
                url,
                title=title,
                source_id=source_id,
                domain=domain,
                ticker=ticker,
                published_at=published_at,
                as_of=as_of,
            )
        return ingest_text(
            self.store,
            text=text,
            title=title,
            source_id=source_id,
            domain=domain,
            ticker=ticker,
            published_at=published_at,
            as_of=as_of,
        )

    def bootstrap_report_seeds(self, repo_root: Path) -> dict:
        reports_dir = Path(repo_root) / "reports"
        results = []
        for name, domain in (
            ("AIbubble.md", "ai_infrastructure"),
            ("light.md", "optical_networking"),
            ("musk.md", "musk_ecosystem"),
            ("robots.md", "robotics"),
        ):
            path = reports_dir / name
            if path.is_file():
                results.append(self.ingest(file_path=str(path), title=name, domain=domain))
        return {
            "ok": True,
            "documents": [row["document"]["id"] for row in results],
            "created": sum(1 for row in results if row["created"]),
            "quarantined": len(results),
        }

    def discover(self, query: str, *, domain: str = "", num_results: int = 8) -> dict:
        rows = discover(query, domain=domain, num_results=num_results)
        staged = self.store.add_discovery_candidates(query=query, domain=domain, candidates=rows)
        return {"query": query, "domain": domain, "candidates": staged}

    def review_discovery(
        self,
        candidate_id: str,
        *,
        status: str,
        ingest_approved: bool = False,
        source_id: str = "",
        ticker: str = "",
    ) -> dict:
        candidates = self.store.list_discovery_candidates(status="", limit=1000)
        candidate = next((row for row in candidates if row["id"] == candidate_id), None)
        if not candidate:
            raise LookupError(f"unknown discovery candidate: {candidate_id}")
        reviewed = self.store.review_discovery(candidate_id, status)
        imported = None
        if status == "approved" and ingest_approved:
            imported = self.ingest(
                url=candidate["url"],
                title=candidate["title"],
                source_id=source_id,
                domain=candidate["domain"],
                ticker=ticker,
            )
        return {"candidate": reviewed, "import": imported}

    def create_contract(self, payload: dict) -> dict:
        return self.store.add_contract(
            scope_type=str(payload.get("scope_type") or ""),
            resolution_source=str(payload.get("resolution_source") or ""),
            scope_id=str(payload.get("scope_id") or ""),
            domain=str(payload.get("domain") or ""),
            horizon=str(payload.get("horizon") or ""),
            statement=str(payload.get("statement") or ""),
            resolution_date=str(payload.get("resolution_date") or ""),
            criteria=payload.get("criteria") or {},
            source_ids=[str(v) for v in payload.get("source_ids") or []],
            parent_archetypes=[str(v) for v in payload.get("parent_archetypes") or []],
            dependency_ids=[str(v) for v in payload.get("dependency_ids") or []],
        )

    def _contract_evidence(self, contract: dict, cutoff: str = "") -> list[dict]:
        claims = self.store.list_claims(
            ticker=contract["scope_id"] if contract["scope_type"] == "ticker" else "",
            domain=contract["domain"],
            limit=200,
        )
        return [
            {
                "claim_id": claim["id"],
                "tag": claim["tag"],
                "confidence": claim["confidence"],
                "verification_state": claim["verification_state"],
                "text": claim["text"],
                "source_id": claim.get("source_id") or "",
                "source_url": claim.get("source_url") or "",
                "as_of": claim.get("as_of") or claim.get("published_at") or claim["observed_at"],
                "conflict_flags": claim.get("conflict_flags") or [],
                "evidence": claim.get("evidence") or [],
            }
            for claim in claims
            if claim["verification_state"] in {"verified", "reviewed_hypothesis"}
            and (
                not cutoff
                or str(claim.get("as_of") or claim.get("published_at") or claim["observed_at"])[:10]
                <= cutoff[:10]
            )
        ]

    def _current_features(self, contract: dict, cutoff: str = "") -> tuple[dict, dict]:
        if contract["scope_type"] != "ticker":
            dashboard = self.dashboard()
            if cutoff and cutoff[:10] < date.today().isoformat():
                dashboard["issues"] = [
                    "current industry artifacts are after a historical forecast cutoff "
                    "and were excluded from model features"
                ]
                return {}, dashboard
            return _flatten_numeric(dashboard), dashboard
        dossier = self.quant.dossier(contract["scope_id"])
        features = {}
        prices = dossier.get("prices") or {}
        for horizon, value in (prices.get("returns") or {}).items():
            if isinstance(value, (int, float)):
                features[f"price_return_{horizon}"] = float(value)
        if isinstance(prices.get("drawdown_252d"), (int, float)):
            features["price_drawdown_252d"] = float(prices["drawdown_252d"])
        factors = ((dossier.get("artifacts") or {}).get("factors") or {}).get("data") or {}
        features.update(_flatten_numeric(factors.get("factors") or {}, prefix="factor"))
        if cutoff:
            price_as_of = str(prices.get("as_of") or "")[:10]
            if price_as_of and price_as_of > cutoff[:10]:
                features = {
                    key: value for key, value in features.items() if not key.startswith("price_")
                }
                dossier["issues"].append(
                    "prices: artifact is after forecast as_of and was excluded from features"
                )
            factor_as_of = str(factors.get("as_of") or "")[:10]
            if factor_as_of and factor_as_of > cutoff[:10]:
                features = {
                    key: value for key, value in features.items() if not key.startswith("factor.")
                }
                dossier["issues"].append(
                    "factors: artifact is after forecast as_of and was excluded from features"
                )
        return features, dossier

    def forecast(
        self,
        contract_id: str,
        *,
        samples: Optional[list[dict]] = None,
        current_features: Optional[dict] = None,
        as_of: str = "",
    ) -> dict:
        contract = self.store.get_contract(contract_id)
        if not contract:
            raise LookupError(f"unknown contract: {contract_id}")
        forecast_as_of = as_of or date.today().isoformat()
        try:
            date.fromisoformat(forecast_as_of)
        except ValueError as exc:
            raise ValueError("forecast as_of must use YYYY-MM-DD") from exc
        if forecast_as_of > contract["resolution_date"]:
            raise ValueError("forecast as_of cannot be after contract resolution_date")
        derived_features, context = self._current_features(contract, forecast_as_of)
        if current_features:
            feature_as_of = str(current_features.get("_as_of") or forecast_as_of)[:10]
            if feature_as_of > forecast_as_of:
                raise ValueError("current feature snapshot is after forecast as_of")
            derived_features.update(_flatten_numeric(current_features))
        rows = samples or []
        for row in rows:
            observed = str(row.get("outcome_observed_at") or "")[:10]
            if observed and observed > forecast_as_of:
                raise ValueError("historical outcome was not observable by forecast as_of")
        result = calibrated_forecast(rows, derived_features)
        training_cutoff = max(
            (str(row.get("outcome_observed_at") or "") for row in rows),
            default=forecast_as_of,
        )
        evidence = self._contract_evidence(contract, forecast_as_of)
        forecast = self.store.add_forecast(
            contract_id=contract_id,
            as_of=forecast_as_of,
            probability_status=result.probability_status,
            probability=result.probability,
            lower_bound=result.lower_bound,
            upper_bound=result.upper_bound,
            model_name=result.model_name,
            model_version=result.model_version,
            training_cutoff=training_cutoff,
            brier_skill=result.brier_skill,
            skill_ci_low=result.skill_ci_low,
            skill_ci_high=result.skill_ci_high,
            metrics=result.metrics,
            evidence=evidence,
            analogs=[],
            llm_involvement="none",
        )
        return {
            "contract": contract,
            "forecast": forecast,
            "context": context,
            "decision_card": self.decision_card(contract, forecast, context, evidence),
        }

    @staticmethod
    def decision_card(contract: dict, forecast: dict, context: dict, evidence: list[dict]) -> dict:
        quant_issues = list(context.get("issues") or []) if isinstance(context, dict) else []
        verified = [row for row in evidence if row["verification_state"] == "verified"]
        hypotheses = [row for row in evidence if row["verification_state"] == "reviewed_hypothesis"]
        criteria = contract["criteria"]
        supporting_data = [
            item
            for row in verified
            for item in row.get("evidence") or []
            if item.get("kind") in {"quant", "official"}
        ]
        counter_data = [
            item
            for row in evidence
            for item in row.get("evidence") or []
            if item.get("stance") == "counter" or item.get("contradicts") is True
        ]
        calibrated = forecast["probability_status"] == "calibrated"
        return {
            "scope": {"type": contract["scope_type"], "id": contract["scope_id"]},
            "horizon": contract["horizon"],
            "event": contract["statement"],
            "probability_status": forecast["probability_status"],
            "probability": forecast["probability"]
            if forecast["probability_status"] == "calibrated"
            else None,
            "interval": (
                [forecast["lower_bound"], forecast["upper_bound"]]
                if forecast["probability_status"] == "calibrated"
                else None
            ),
            "robustness_score": float(forecast["lower_bound"]) if calibrated else None,
            "opportunity": {
                "beneficiaries": [str(value) for value in criteria.get("beneficiaries") or []],
                "criteria": criteria,
                "verified_support": verified,
                "supporting_data": supporting_data,
            },
            "risk": {
                "victims": [str(value) for value in criteria.get("victims") or []],
                "counterevidence": hypotheses,
                "counter_data": counter_data,
                "quant_issues": quant_issues,
            },
            "watch": criteria.get("leading_indicators") or list(criteria.keys()),
            "triggers": criteria.get("triggers") or criteria,
            "invalidation": {
                "resolution_date": contract["resolution_date"],
                "resolution_source": contract.get("resolution_source") or "",
                "contract_status": contract["status"],
                "conditions": criteria.get("invalidation_conditions") or [],
            },
            "orders_generated": False,
        }

    @staticmethod
    def robust_opportunities(cards: list[dict]) -> list[dict]:
        """Rank beneficiaries that survive more than one independently gated event."""
        grouped: dict[str, dict] = {}
        for card in cards:
            if card["probability_status"] != "calibrated":
                continue
            probability = float(card["probability"])
            lower_bound = float(card["interval"][0])
            if probability < 0.50:
                continue
            for raw_symbol in card["opportunity"].get("beneficiaries") or []:
                symbol = str(raw_symbol).upper()
                row = grouped.setdefault(
                    symbol,
                    {
                        "ticker": symbol,
                        "scenario_count": 0,
                        "min_lower_bound": 1.0,
                        "events": [],
                    },
                )
                row["scenario_count"] += 1
                row["min_lower_bound"] = min(row["min_lower_bound"], lower_bound)
                row["events"].append(card["event"])
        for row in grouped.values():
            breadth_bonus = min(0.5, 0.1 * max(0, row["scenario_count"] - 1))
            row["robustness_score"] = row["min_lower_bound"] * (1 + breadth_bonus)
        return sorted(
            grouped.values(),
            key=lambda row: (row["robustness_score"], row["scenario_count"]),
            reverse=True,
        )

    def _criterion_value(self, contract: dict, criterion: dict) -> tuple[Optional[float], dict]:
        if contract["scope_type"] != "ticker":
            return None, {"reason": "automatic numeric resolution currently requires a ticker"}
        if contract.get("resolution_source") != "quant_prices":
            return None, {"reason": "automatic resolution requires quant_prices"}
        operator = str(criterion.get("operator") or criterion.get("type") or "")
        end_bar = self.quant.price_on_or_before(contract["scope_id"], contract["resolution_date"])
        if end_bar.get("status") != "ok":
            return None, {"end_bar": end_bar}
        if operator in {"price_above", "price_below"}:
            return float(end_bar["close"]), {"end_bar": end_bar}
        if operator in {"return_gte", "return_lte"}:
            start_date = str(criterion.get("start_date") or "")
            start_bar = self.quant.price_on_or_before(contract["scope_id"], start_date)
            if start_bar.get("status") != "ok" or not start_bar.get("close"):
                return None, {"start_bar": start_bar, "end_bar": end_bar}
            realized = float(end_bar["close"]) / float(start_bar["close"]) - 1
            return realized, {
                "start_bar": start_bar,
                "end_bar": end_bar,
                "realized_return": realized,
            }
        return None, {"reason": f"unsupported operator: {operator}", "end_bar": end_bar}

    def auto_resolve(self, contract_id: str, *, actor: str = "narrative-auto") -> dict:
        contract = self.store.get_contract(contract_id)
        if not contract:
            raise LookupError(f"unknown contract: {contract_id}")
        if date.fromisoformat(contract["resolution_date"]) > date.today():
            raise ValueError("contract resolution date has not arrived")
        criterion = contract["criteria"]
        value, details = self._criterion_value(contract, criterion)
        operator = str(criterion.get("operator") or criterion.get("type") or "")
        threshold = criterion.get("threshold")
        outcome: Optional[int] = None
        if value is not None and isinstance(threshold, (int, float)):
            if operator in {"price_above", "return_gte"}:
                outcome = int(value >= float(threshold))
            elif operator in {"price_below", "return_lte"}:
                outcome = int(value <= float(threshold))
        resolution = self.store.add_resolution(
            contract_id=contract_id,
            outcome=outcome,
            reason="automatic event-contract evaluation"
            if outcome is not None
            else "automatic evaluation lacked admissible data",
            actor=actor,
            kind="auto",
            values={"criterion": criterion, **details},
        )
        return {"contract": contract, "resolution": resolution}

    def human_override(
        self,
        contract_id: str,
        *,
        outcome: int,
        reason: str,
        actor: str,
        forecast_id: str = "",
        values: Optional[dict] = None,
    ) -> dict:
        return self.store.add_resolution(
            contract_id=contract_id,
            forecast_id=forecast_id,
            outcome=outcome,
            reason=reason,
            actor=actor,
            kind="human_override",
            values=values or {},
        )

    def calibrate(self, *, domain: str, horizon: str, as_of: str = "") -> dict:
        resolutions = self.store.effective_resolutions()
        contracts = {
            row["id"]: row
            for row in self.store.list_contracts(horizon=horizon)
            if not domain or row["domain"] == domain
        }
        latest: dict[str, dict] = {}
        for forecast in reversed(self.store.list_forecasts(limit=1000)):
            if (
                forecast["contract_id"] in contracts
                and forecast["probability_status"] == "calibrated"
            ):
                latest[forecast["contract_id"]] = forecast
        ys, ps = [], []
        for contract_id, forecast in latest.items():
            resolution = resolutions.get(contract_id)
            contract = contracts.get(contract_id)
            if not resolution or not contract:
                continue
            if str(forecast["as_of"]) > str(contract["resolution_date"]):
                continue
            if str(forecast["created_at"]) > str(resolution["created_at"]):
                continue
            ys.append(int(resolution["outcome"]))
            ps.append(float(forecast["probability"]))
        metrics = evaluate_published_forecasts(ys, ps)
        snapshot = self.store.add_calibration_snapshot(
            domain=domain,
            horizon=horizon,
            as_of=as_of or date.today().isoformat(),
            model_version=MODEL_VERSION,
            eligible=bool(metrics.get("eligible")),
            metrics=metrics,
        )
        return {"snapshot": snapshot, "resolved_forecasts": len(ys)}

    def dashboard(self) -> dict:
        dashboard = self.quant.industry_dashboard()
        claims = self.store.list_claims(limit=1000)
        eligible = [
            claim
            for claim in claims
            if claim["verification_state"] in {"verified", "reviewed_hypothesis"}
        ]
        sector_index = {row["id"]: row for row in dashboard["sectors"]}
        sector_index.update({row["name"].lower(): row for row in dashboard["sectors"]})
        for claim in eligible:
            key = claim["domain"].strip().lower()
            target = sector_index.get(key)
            if target:
                target["hotspots"].append(claim)
            elif key == "macro":
                dashboard["macro"]["hotspots"].append(claim)
            elif key == "crypto":
                dashboard["crypto"]["hotspots"].append(claim)
        dashboard["evidence_updated_at"] = max(
            (claim["observed_at"] for claim in eligible), default=""
        )
        return dashboard

    def company(self, ticker: str) -> dict:
        dossier = self.quant.dossier(ticker)
        contracts = self.store.list_contracts(scope_id=ticker)
        forecasts = self.store.list_forecasts(limit=1000)
        forecasts_by_contract: dict[str, list[dict]] = {}
        for forecast in forecasts:
            forecasts_by_contract.setdefault(forecast["contract_id"], []).append(forecast)
        claims = self.store.list_claims(ticker=ticker, limit=200)
        cards = []
        for contract in contracts:
            contract_forecasts = forecasts_by_contract.get(contract["id"]) or []
            forecast = (
                contract_forecasts[0]
                if contract_forecasts
                else {
                    "probability_status": "insufficient_data",
                    "probability": None,
                    "lower_bound": None,
                    "upper_bound": None,
                }
            )
            cards.append(
                self.decision_card(
                    contract,
                    forecast,
                    dossier,
                    [
                        claim
                        for claim in claims
                        if claim["verification_state"] in {"verified", "reviewed_hypothesis"}
                    ],
                )
            )
        cards.sort(
            key=lambda card: (
                card["probability_status"] == "calibrated",
                card.get("robustness_score") if card.get("robustness_score") is not None else -1,
            ),
            reverse=True,
        )
        return {
            "ticker": ticker.upper(),
            "quant": dossier,
            "claims": claims,
            "contracts": contracts,
            "forecasts": forecasts_by_contract,
            "decision_cards": cards,
            "robust_opportunities": self.robust_opportunities(cards),
        }

    def history(self) -> dict:
        return {
            "archetypes": list(ARCHETYPES),
            "episodes": self.store.list_episodes(),
            "quant_regime_ledger": self.quant.regime_ledger(),
            "training_rule": "post-hoc episodes are descriptive only; only pre-event features may train models",
        }

    def sources(self, *, domain: str = "", horizon: str = "") -> dict:
        return {
            "sources": self.store.list_sources(),
            "track_record": self.store.source_scores(domain=domain, horizon=horizon),
        }
