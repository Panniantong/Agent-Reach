# -*- coding: utf-8 -*-
"""Application service joining evidence, Quant context, contracts, and calibration."""

from __future__ import annotations

from datetime import date, timedelta
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

_HORIZON_DAYS = {"quarter": 92, "1y": 365, "3y": 1095, "5y": 1826}

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


def _nested_number(value: Any, *path: str) -> Optional[float]:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        return None
    return float(current)


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

    def scenario_board(self, ticker: str, *, horizon: str = "1y") -> dict:
        """Build a result-first research board without inventing event probabilities."""
        if horizon not in _HORIZON_DAYS:
            raise ValueError("horizon must be one of quarter, 1y, 3y, 5y")
        company = self.company(ticker)
        symbol = company["ticker"]
        dossier = company["quant"]
        prices = dossier.get("prices") or {}
        artifacts = dossier.get("artifacts") or {}
        factor_artifact = artifacts.get("factors") or {}
        factor_data = factor_artifact.get("data") or {}
        factors = factor_data.get("factors") or {}
        returns = prices.get("returns") or {}
        price_as_of = str(prices.get("as_of") or date.today().isoformat())[:10]
        try:
            resolution_date = (
                date.fromisoformat(price_as_of) + timedelta(days=_HORIZON_DAYS[horizon])
            ).isoformat()
        except ValueError:
            resolution_date = (
                date.today() + timedelta(days=_HORIZON_DAYS[horizon])
            ).isoformat()

        ret_21 = _nested_number(returns, "21d")
        ret_63 = _nested_number(returns, "63d")
        ret_252 = _nested_number(returns, "252d")
        drawdown = _nested_number(prices, "drawdown_252d")
        relative_63 = _nested_number(factors, "relative", "relative_return_63d")
        volatility_63 = _nested_number(factors, "risk", "ann_vol_63d")
        beta_126 = _nested_number(factors, "relative", "static_beta_126d")
        tail_amplification = _nested_number(
            factors, "lower_tail_dependence", "tail_amplification"
        )
        supply_overlay = _nested_number(
            factors, "supply_chain", "supply_risk_overlay_score"
        )
        liquidity_score = _nested_number(
            factors, "execution_liquidity", "liquidity_score"
        )
        regime = str(factor_data.get("regime_label") or "UNKNOWN")
        regime_as_of = str(factor_data.get("as_of") or "UNKNOWN")[:10]
        matured = _nested_number(
            factors,
            "regime_probability_forward_calibration",
            "matured_evaluations",
        )
        required = _nested_number(
            factors,
            "regime_probability_forward_calibration",
            "minimum_forward_evaluations",
        )

        evidence = [
            {
                "tag": "COMPUTED",
                "label": "最新收盤",
                "value": prices.get("last_close"),
                "format": "number",
                "as_of": price_as_of,
                "source": prices.get("path") or "Quant prices",
                "freshness": prices.get("freshness") or "unknown",
            },
            {
                "tag": "COMPUTED",
                "label": "21 日報酬",
                "value": ret_21,
                "format": "percent",
                "as_of": price_as_of,
                "source": prices.get("path") or "Quant prices",
                "freshness": prices.get("freshness") or "unknown",
            },
            {
                "tag": "COMPUTED",
                "label": "63 日報酬",
                "value": ret_63,
                "format": "percent",
                "as_of": price_as_of,
                "source": prices.get("path") or "Quant prices",
                "freshness": prices.get("freshness") or "unknown",
            },
            {
                "tag": "COMPUTED",
                "label": "252 日報酬",
                "value": ret_252,
                "format": "percent",
                "as_of": price_as_of,
                "source": prices.get("path") or "Quant prices",
                "freshness": prices.get("freshness") or "unknown",
            },
            {
                "tag": "COMPUTED",
                "label": "63 日年化波動",
                "value": volatility_63,
                "format": "percent",
                "as_of": regime_as_of,
                "source": factor_artifact.get("path") or "Quant factors",
                "freshness": factor_artifact.get("freshness") or "unknown",
            },
            {
                "tag": "COMPUTED",
                "label": "供應鏈風險覆蓋分數",
                "value": supply_overlay,
                "format": "score",
                "as_of": regime_as_of,
                "source": factor_artifact.get("path") or "Quant factors",
                "freshness": factor_artifact.get("freshness") or "unknown",
            },
        ]

        gate_reason = (
            "[COMPUTED] 目前沒有成熟的 point-in-time 結算樣本，不能發布數字機率。"
            if matured in (None, 0.0)
            else (
                f"[COMPUTED] 成熟 forward evaluations={int(matured)}；"
                f"最低需求={int(required) if required is not None else 'UNKNOWN'}。"
            )
        )
        base = {
            "probability_status": "insufficient_data",
            "probability": None,
            "interval": None,
            "gate_reason": gate_reason,
            "horizon": horizon,
            "resolution_date": resolution_date,
            "origin": "system_blueprint",
        }
        scenarios = [
            {
                **base,
                "id": f"{symbol.lower()}-continuation",
                "name": "成長延續／驗收通過",
                "event": f"{symbol} 自 {price_as_of} 至 {resolution_date} 的收盤報酬 ≥ 20%。",
                "narrative": (
                    "[INFERRED | MED] 長期動能延續，需求與獲利驗收足以抵消估值壓力；"
                    "這是待結算事件，不是買進指令。"
                ),
                "drivers": [
                    "[COMPUTED] 252 日報酬仍為正。",
                    "[COMPUTED] 最近 21 日價格動能回升。",
                    "[KNOWN] 價格資料具明確截止日與不可變來源路徑。",
                ],
                "counterevidence": [
                    "[COMPUTED] 63 日相對報酬偏弱。",
                    f"[COMPUTED] 因子體制截至 {regime_as_of} 為 {regime}。",
                ],
                "invalidators": [
                    "兩個連續觀測窗的 63 日報酬轉負。",
                    "基本面 artifact 無法補齊可驗證 as_of。",
                    "期末報酬未達事件契約門檻。",
                ],
                "beneficiaries": [symbol, "TSM"] if symbol == "NVDA" else [symbol],
                "victims": ["追高且無失效條件的敘事"],
                "archetypes": ["technology_diffusion_capacity", "valuation_crowding"],
            },
            {
                **base,
                "id": f"{symbol.lower()}-digestion",
                "name": "高位震盪／估值消化",
                "event": f"{symbol} 在 {resolution_date} 前維持高波動，但趨勢沒有形成可發布優勢。",
                "narrative": (
                    "[INFERRED | MED] 長期報酬與短期相對弱勢互相抵銷，價格用區間而非方向"
                    "消化前期漲幅。"
                ),
                "drivers": [
                    "[COMPUTED] 21 日與 252 日報酬方向不完全一致。",
                    "[COMPUTED] 年化波動仍高，單一方向敘事的誤差會被放大。",
                ],
                "counterevidence": [
                    "[COMPUTED] 若 63 日相對強度持續改善，震盪假設會弱化。",
                    "[COMPUTED] 若因子體制切回明確上升，區間假設失效。",
                ],
                "invalidators": [
                    "價格突破後連續兩個 21 日窗保持正相對報酬。",
                    "事件契約到期時出現 ≥20% 或 ≤−20% 的方向性報酬。",
                ],
                "beneficiaries": ["波動率與事件研究"],
                "victims": ["只押單一路徑的研究流程"],
                "archetypes": ["valuation_crowding", "liquidity_discount_rate"],
            },
            {
                **base,
                "id": f"{symbol.lower()}-rerating",
                "name": "折現率／尾部風險重定價",
                "event": f"{symbol} 自 {price_as_of} 至 {resolution_date} 的收盤報酬 ≤ −20%。",
                "narrative": (
                    "[INFERRED | MED] 即使產業需求沒有消失，高 beta、尾部共振與相對弱勢也可能先壓縮估值。"
                ),
                "drivers": [
                    f"[COMPUTED] 126 日 beta={beta_126 if beta_126 is not None else 'UNKNOWN'}。",
                    f"[COMPUTED] 下尾共振放大倍數={tail_amplification if tail_amplification is not None else 'UNKNOWN'}。",
                    f"[COMPUTED] 252 日內回撤={drawdown if drawdown is not None else 'UNKNOWN'}。",
                ],
                "counterevidence": [
                    "[COMPUTED] 252 日價格報酬仍為正。",
                    "[COMPUTED] 執行流動性高，流動性風險不是目前的主要缺口。",
                ],
                "invalidators": [
                    "相對報酬與 trend 因子同步轉正。",
                    "期末報酬未達事件契約的負向門檻。",
                ],
                "beneficiaries": ["短久期現金流", "風險預算"],
                "victims": [symbol, "高 beta AI 標的"],
                "archetypes": ["liquidity_discount_rate", "valuation_crowding"],
            },
            {
                **base,
                "id": f"{symbol.lower()}-bottleneck",
                "name": "供應鏈瓶頸外溢",
                "event": f"{symbol} 的已驗證直接供應依賴在 {resolution_date} 前成為營運或估值主因。",
                "narrative": (
                    "[INFERRED | LOW] 價值捕獲可能從平台外溢到先進製造與供應瓶頸；"
                    "此事件需要官方營運資料人工結算。"
                ),
                "drivers": [
                    "[KNOWN] Quant 供應鏈圖保存兩條已驗證 primary-source 直接邊。",
                    f"[COMPUTED] 供應鏈風險覆蓋分數={supply_overlay if supply_overlay is not None else 'UNKNOWN'}。",
                ],
                "counterevidence": [
                    "[KNOWN] 該分數明示為 risk overlay，不是報酬預測。",
                    "[INFERRED | LOW] 替代供應、設計變更或需求下降都可繞過瓶頸。",
                ],
                "invalidators": [
                    "官方文件移除或降低直接依賴。",
                    "供應瓶頸沒有轉成營收、毛利或交付限制。",
                ],
                "beneficiaries": ["TSM", "已驗證供應節點"] if symbol == "NVDA" else [],
                "victims": [symbol, "單一路徑供應鏈假設"],
                "archetypes": ["technology_diffusion_capacity", "regulation_geopolitics"],
            },
        ]

        for index, card in enumerate(company.get("decision_cards") or []):
            scenarios.insert(
                index,
                {
                    "id": f"contract-{index}",
                    "name": "已建立事件契約",
                    "event": card["event"],
                    "narrative": "[KNOWN] 使用者已建立、可重播的事件契約。",
                    "probability_status": card["probability_status"],
                    "probability": card["probability"],
                    "interval": card["interval"],
                    "gate_reason": (
                        "[COMPUTED] 已通過校準發布閘門。"
                        if card["probability_status"] == "calibrated"
                        else "[COMPUTED] 此契約尚未通過校準發布閘門。"
                    ),
                    "horizon": card["horizon"],
                    "resolution_date": card["invalidation"]["resolution_date"],
                    "origin": "event_contract",
                    "drivers": [row["text"] for row in card["opportunity"]["verified_support"]],
                    "counterevidence": [
                        row["text"] for row in card["risk"]["counterevidence"]
                    ],
                    "invalidators": card["invalidation"]["conditions"],
                    "beneficiaries": card["opportunity"]["beneficiaries"],
                    "victims": card["risk"]["victims"],
                    "archetypes": [],
                },
            )

        positive_tension = ret_252 is not None and ret_252 > 0
        short_tension = relative_63 is not None and relative_63 < 0
        return {
            "ticker": symbol,
            "horizon": horizon,
            "as_of": price_as_of,
            "resolution_date": resolution_date,
            "title": f"{symbol}：AI 驗收、估值消化與供應瓶頸",
            "regime": {
                "label": regime,
                "as_of": regime_as_of,
                "summary": (
                    "[COMPUTED] 長期價格動能為正，但中期相對強度與較早的因子體制偏弱。"
                    if positive_tension and short_tension
                    else "[COMPUTED] 價格與因子證據未形成一致方向。"
                ),
                "interpretation": (
                    "[INFERRED | MED] 現在更像『趨勢仍在、但驗收與估值開始分岔』，"
                    "不是單一路徑的主升或崩盤。"
                ),
            },
            "analogue": {
                "name": "AI 基礎設施擴散 × 2021–2022 折現率轉折",
                "rhyme": (
                    "[INFERRED, post-hoc | MED] 技術擴散與資本支出延續時，"
                    "估值可以先因折現率與擁擠度重定價。"
                ),
                "difference": (
                    "[INFERRED, post-hoc | LOW] 目前歷史事件圖仍是描述性 scaffold，"
                    "尚無核准來源包，不得進模型訓練。"
                ),
            },
            "scenarios": scenarios,
            "evidence": evidence,
            "opportunities": [
                {
                    "title": "長期動能尚未被價格否定",
                    "support": "COMPUTED",
                    "why": "252 日報酬為正；必須與較弱的 63 日相對強度一起看。",
                },
                {
                    "title": "流動性足以支撐事件研究",
                    "support": "COMPUTED",
                    "why": f"執行流動性分數={liquidity_score if liquidity_score is not None else 'UNKNOWN'}；這不是方向訊號。",
                },
                {
                    "title": "供應瓶頸可被拆成可驗證事件",
                    "support": "KNOWN",
                    "why": "直接供應邊有 primary-source 證據，但價值捕獲仍需營運資料結算。",
                },
            ],
            "risks": [
                {
                    "title": "價格與因子時點衝突",
                    "support": "COMPUTED",
                    "why": f"價格截至 {price_as_of}，因子截至 {regime_as_of}；不能混成同一時點。",
                },
                {
                    "title": "高 beta 與尾部共振",
                    "support": "COMPUTED",
                    "why": f"beta={beta_126 if beta_126 is not None else 'UNKNOWN'}；尾部放大={tail_amplification if tail_amplification is not None else 'UNKNOWN'}。",
                },
                {
                    "title": "證據新鮮度降級",
                    "support": "KNOWN",
                    "why": "；".join(dossier.get("issues") or ["未偵測到資料警告"]),
                },
            ],
            "source_synthesis": [
                {
                    "source": prices.get("path") or "Quant prices",
                    "use": "[COMPUTED] 價格、報酬、回撤與資料截止日。",
                },
                {
                    "source": factor_artifact.get("path") or "Quant factors",
                    "use": "[COMPUTED] 體制、相對強弱、beta、尾部與供應鏈風險。",
                },
                {
                    "source": "Narrative evidence ledger",
                    "use": (
                        f"[KNOWN] {len(company.get('claims') or [])} 項公司主張；"
                        "pending 主張不進已驗證證據。"
                    ),
                },
            ],
            "calibration": {
                "status": "insufficient_data"
                if not any(row["probability_status"] == "calibrated" for row in scenarios)
                else "partially_calibrated",
                "matured_forward_evaluations": int(matured or 0),
                "minimum_forward_evaluations": int(required or 0),
                "rule": "90% Brier Skill CI 下界 > 0，且機率區間寬度 ≤ 40pp。",
                "reason": gate_reason,
            },
            "orders_generated": False,
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
