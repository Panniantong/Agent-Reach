# -*- coding: utf-8 -*-
"""Read-only adapter for point-in-time Quant artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent_reach.config import Config

DEFAULT_QUANT_DATA_ROOT = Path(r"D:\DOT\Quant\data")
GICS_SECTORS = (
    ("communication-services", "Communication Services"),
    ("consumer-discretionary", "Consumer Discretionary"),
    ("consumer-staples", "Consumer Staples"),
    ("energy", "Energy"),
    ("financials", "Financials"),
    ("health-care", "Health Care"),
    ("industrials", "Industrials"),
    ("information-technology", "Information Technology"),
    ("materials", "Materials"),
    ("real-estate", "Real Estate"),
    ("utilities", "Utilities"),
)
POINTER_KEYS = ("artifact_path", "report_path", "output_path", "target_path", "run_path")


def _parse_date(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 7 and text[4] == "-":
        text += "-01"
    if len(text) == 10:
        text += "T00:00:00+00:00"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _return(closes: list[float], horizon: int) -> Optional[float]:
    if len(closes) <= horizon or closes[-horizon - 1] == 0:
        return None
    return closes[-1] / closes[-horizon - 1] - 1


def _compact(data: dict) -> dict:
    keys = (
        "status",
        "ticker",
        "as_of",
        "observed_at",
        "fetched_at",
        "artifact_id",
        "schema",
        "schema_version",
        "source",
        "sources",
        "regime_label",
        "headline",
        "summary",
        "verdict",
        "grade",
        "is_point_in_time",
        "point_in_time",
        "point_in_time_guard",
        "leakage_checks",
        "availability_contract",
        "admissibility",
        "llm_involvement",
        "human_gate_required",
        "orders_generated",
        "proposal_only",
        "gates_nothing",
        "flags",
        "factors",
        "metrics",
        "honest_notes",
        "not_conditioned_on",
        "survivorship",
        "survivorship_zh",
        "quarters",
        "latest_quarter",
    )
    return {key: data[key] for key in keys if key in data}


class QuantAdapter:
    """Reads approved Quant files and never opens anything for writing."""

    def __init__(self, root: Optional[Path] = None, config: Optional[Config] = None):
        cfg = config or Config()
        configured = cfg.get("quant_data_root")
        self.root = (
            Path(root) if root else Path(str(configured)) if configured else DEFAULT_QUANT_DATA_ROOT
        ).resolve()

    def status(self) -> dict:
        return {
            "root": str(self.root),
            "available": self.root.is_dir(),
            "mode": "read_only",
        }

    def _inside_root(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"Quant path escapes configured root: {resolved}") from exc
        return resolved

    def _pointer_issue(self, path: Path, data: dict) -> Optional[str]:
        for key in POINTER_KEYS:
            target = data.get(key)
            if not isinstance(target, str) or not target.strip():
                continue
            target_path = Path(target)
            candidates = [
                target_path if target_path.is_absolute() else path.parent / target_path,
                self.root / target_path,
            ]
            valid = False
            for candidate in candidates:
                try:
                    safe = self._inside_root(candidate)
                except ValueError:
                    continue
                if safe.is_file():
                    valid = True
                    break
            if not valid:
                return f"{key} points to a missing artifact: {target}"
        return None

    def read_json_artifact(self, path: Path, *, max_age_days: int = 45) -> dict:
        safe = self._inside_root(path)
        result = {
            "path": str(safe),
            "exists": safe.is_file(),
            "freshness": "missing",
            "issues": [],
            "sha256": "",
            "data": {},
        }
        if not safe.is_file():
            result["issues"].append("artifact missing")
            return result
        raw = safe.read_bytes()
        result["sha256"] = hashlib.sha256(raw).hexdigest()
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            result["freshness"] = "invalid"
            result["issues"].append(f"invalid JSON: {exc}")
            return result
        if not isinstance(data, dict):
            result["freshness"] = "invalid"
            result["issues"].append("artifact root must be an object")
            return result
        pointer_issue = self._pointer_issue(safe, data)
        if pointer_issue:
            result["issues"].append(pointer_issue)
        as_of = (
            data.get("as_of")
            or data.get("observed_at")
            or data.get("fetched_at")
            or data.get("generated_at")
        )
        parsed = _parse_date(as_of)
        if parsed:
            age = max(0, (datetime.now(timezone.utc) - parsed).days)
            result["age_days"] = age
            result["freshness"] = "fresh" if age <= max_age_days else "stale"
            if age > max_age_days:
                result["issues"].append(f"artifact is {age} days old")
        else:
            result["freshness"] = "unknown"
            result["issues"].append("artifact has no parseable as_of/observed_at")
        schema_version = data.get("schema_version")
        if schema_version is not None and not isinstance(schema_version, (str, int)):
            result["freshness"] = "invalid"
            result["issues"].append("schema_version must be a string or integer")
        leakage_checks = data.get("leakage_checks")
        if isinstance(leakage_checks, dict):
            if (
                leakage_checks.get("passed") is False
                or leakage_checks.get("leakage_detected") is True
            ):
                result["issues"].append("artifact reports a failed leakage check")
            failed = leakage_checks.get("failed")
            if isinstance(failed, list) and failed:
                result["issues"].append(
                    "failed leakage checks: " + ", ".join(str(item) for item in failed)
                )
        if data.get("llm_involvement") not in (None, "none", "narration_only"):
            result["issues"].append("LLM output is not KPI-eligible")
        if data.get("is_point_in_time") is False or data.get("point_in_time") is False:
            result["issues"].append("artifact declares non-point-in-time data")
        if data.get("orders_generated") is True:
            result["issues"].append("artifact generated orders and is excluded")
        result["data"] = _compact(data)
        return result

    def read_prices(self, ticker: str) -> dict:
        symbol = ticker.upper().strip()
        candidates = (
            self.root / "lake" / "finviz" / "prices" / f"{symbol}.csv",
            self.root / "reports" / "finviz" / "latest" / f"{symbol}_daily.csv",
        )
        path = next((p for p in candidates if p.is_file()), candidates[0])
        safe = self._inside_root(path)
        result = {"path": str(safe), "exists": safe.is_file(), "issues": []}
        if not safe.is_file():
            result["issues"].append("price file missing")
            return result
        dates: list[str] = []
        closes: list[float] = []
        volumes: list[float] = []
        with safe.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                try:
                    close = float(row.get("Close") or row.get("close") or "")
                except (TypeError, ValueError):
                    continue
                dates.append(str(row.get("Date") or row.get("date") or ""))
                closes.append(close)
                try:
                    volumes.append(float(row.get("Volume") or row.get("volume") or 0))
                except (TypeError, ValueError):
                    volumes.append(0.0)
        if not closes:
            result["issues"].append("price file contains no valid close rows")
            return result
        peak = max(closes[-252:] or closes)
        result.update(
            {
                "as_of": dates[-1],
                "observations": len(closes),
                "first_date": dates[0],
                "last_close": closes[-1],
                "returns": {
                    "21d": _return(closes, 21),
                    "63d": _return(closes, 63),
                    "252d": _return(closes, 252),
                },
                "drawdown_252d": closes[-1] / peak - 1 if peak else None,
                "median_volume_21d": sorted(volumes[-21:])[len(volumes[-21:]) // 2]
                if volumes
                else None,
                "freshness": "fresh"
                if (
                    _parse_date(dates[-1])
                    and (datetime.now(timezone.utc) - _parse_date(dates[-1])).days <= 10
                )
                else "stale",
            }
        )
        if result["freshness"] == "stale":
            result["issues"].append("latest price bar is stale")
        return result

    def price_on_or_before(self, ticker: str, target_date: str) -> dict:
        """Return the last valid bar no later than target_date; never reads a later outcome."""
        symbol = ticker.upper().strip()
        candidates = (
            self.root / "lake" / "finviz" / "prices" / f"{symbol}.csv",
            self.root / "reports" / "finviz" / "latest" / f"{symbol}_daily.csv",
        )
        path = next((p for p in candidates if p.is_file()), candidates[0])
        safe = self._inside_root(path)
        if not safe.is_file():
            return {"status": "missing", "ticker": symbol, "target_date": target_date}
        target = _parse_date(target_date)
        if not target:
            raise ValueError("target_date must be ISO formatted")
        chosen: Optional[dict] = None
        with safe.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                row_date = str(row.get("Date") or row.get("date") or "")
                parsed = _parse_date(row_date)
                if not parsed or parsed > target:
                    continue
                try:
                    close = float(row.get("Close") or row.get("close") or "")
                except (TypeError, ValueError):
                    continue
                if chosen is None or row_date > chosen["date"]:
                    chosen = {"date": row_date, "close": close}
        if chosen is None:
            return {
                "status": "missing",
                "ticker": symbol,
                "target_date": target_date,
                "path": str(safe),
            }
        return {
            "status": "ok",
            "ticker": symbol,
            "target_date": target_date,
            "date": chosen["date"],
            "close": chosen["close"],
            "path": str(safe),
            "point_in_time": True,
        }

    def _ticker_artifacts(self, ticker: str) -> dict[str, tuple[Path, int]]:
        symbol = ticker.upper().strip()
        return {
            "fundamentals": (self.root / "lake" / "fundamentals_sec_m25" / f"{symbol}.json", 180),
            "factors": (self.root / "reports" / "factors" / symbol / "latest.json", 45),
            "validation": (
                self.root / "reports" / "validation" / "ticker" / symbol / "latest.json",
                90,
            ),
            "conformal": (
                self.root / "reports" / "validation" / "conformal" / symbol / "latest.json",
                90,
            ),
            "forward_context": (
                self.root
                / "experiments"
                / "ticker_solver"
                / symbol
                / "forward_context"
                / "latest.json",
                45,
            ),
            "deep_dive": (self.root / "reports" / "deep_dive" / symbol / "latest.json", 90),
            "ticker_solver": (self.root / "reports" / "ticker_solver" / symbol / "latest.json", 45),
        }

    def dossier(self, ticker: str) -> dict:
        symbol = ticker.upper().strip()
        if not symbol or not all(ch.isalnum() or ch in ".-" for ch in symbol):
            raise ValueError("invalid ticker")
        artifacts = {
            name: self.read_json_artifact(path, max_age_days=max_age)
            for name, (path, max_age) in self._ticker_artifacts(symbol).items()
        }
        prices = self.read_prices(symbol)
        issues = list(prices.get("issues") or [])
        for name, artifact in artifacts.items():
            issues.extend(f"{name}: {issue}" for issue in artifact.get("issues") or [])
        evidence_grade = "usable"
        if not prices.get("exists"):
            evidence_grade = "insufficient"
        elif any(
            marker in issue
            for issue in issues
            for marker in (
                "non-point-in-time",
                "artifact missing",
                "missing artifact",
                "failed leakage",
                "schema_version",
                "days old",
                "no parseable as_of",
                "LLM output",
                "generated orders",
                "orders and is excluded",
            )
        ):
            evidence_grade = "degraded"
        return {
            "ticker": symbol,
            "quant_root": str(self.root),
            "read_only": True,
            "prices": prices,
            "artifacts": artifacts,
            "issues": issues,
            "evidence_grade": evidence_grade,
        }

    def industry_dashboard(self) -> dict:
        rotation = self.read_json_artifact(
            self.root / "reports" / "sector_rotation" / "latest.json",
            max_age_days=45,
        )
        raw = rotation.get("data") or {}
        sector_rows = raw.get("sectors") if isinstance(raw.get("sectors"), list) else []
        by_name = {
            str(row.get("sector") or row.get("name") or "").lower(): row
            for row in sector_rows
            if isinstance(row, dict)
        }
        sectors = []
        for sector_id, name in GICS_SECTORS:
            quant = by_name.get(name.lower()) or by_name.get(sector_id)
            sectors.append(
                {
                    "id": sector_id,
                    "name": name,
                    "quant": quant or {},
                    "quant_available": bool(quant),
                    "hotspots": [],
                }
            )
        return {
            "as_of": raw.get("as_of") or raw.get("observed_at") or "",
            "sectors": sectors,
            "macro": {"id": "macro", "name": "Macro", "hotspots": []},
            "crypto": {"id": "crypto", "name": "Crypto", "hotspots": []},
            "rotation_artifact": rotation,
        }

    def regime_ledger(self) -> dict:
        return self.read_json_artifact(
            self.root / "reports" / "regime_episode_ledger" / "latest.json",
            max_age_days=120,
        )
