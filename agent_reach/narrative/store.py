# -*- coding: utf-8 -*-
"""SQLite evidence ledger with immutable blobs and append-only resolutions."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from agent_reach.config import Config
from agent_reach.narrative.models import (
    CLAIM_TAGS,
    CONFIDENCE_LEVELS,
    HORIZONS,
    PROBABILITY_STATUSES,
    RESOLUTION_KINDS,
    SCOPE_TYPES,
    VERIFICATION_STATES,
    json_safe,
    require_choice,
    utc_now,
)

SCHEMA_VERSION = 2


def narrative_root(config: Optional[Config] = None) -> Path:
    cfg = config or Config()
    configured = cfg.get("narrative_data_dir")
    if configured:
        return Path(str(configured)).expanduser()
    return Config.CONFIG_DIR / "radar" / "narrative"


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _dump(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, separators=(",", ":"))


def _load(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


class NarrativeStore:
    """Owns the local narrative database and content-addressed source blobs."""

    def __init__(self, root: Optional[Path] = None, config: Optional[Config] = None):
        self.root = Path(root) if root else narrative_root(config)
        self.db_path = self.root / "narrative.sqlite3"
        self.blob_dir = self.root / "blobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self._migrate()
        self._seed_sources()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _migrate(self) -> None:
        with self._connect() as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"narrative database schema {version} is newer than supported {SCHEMA_VERSION}"
                )
            if version == 0:
                conn.executescript(
                    """
                    CREATE TABLE source_identities (
                        id TEXT PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        handles_json TEXT NOT NULL DEFAULT '[]',
                        domains_json TEXT NOT NULL DEFAULT '[]',
                        conflict_flags_json TEXT NOT NULL DEFAULT '[]',
                        notes TEXT NOT NULL DEFAULT '',
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE documents (
                        id TEXT PRIMARY KEY,
                        sha256 TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL DEFAULT '',
                        source_url TEXT NOT NULL DEFAULT '',
                        source_id TEXT,
                        media_type TEXT NOT NULL,
                        published_at TEXT NOT NULL DEFAULT '',
                        observed_at TEXT NOT NULL,
                        as_of TEXT NOT NULL DEFAULT '',
                        domain TEXT NOT NULL DEFAULT '',
                        verification_state TEXT NOT NULL DEFAULT 'pending',
                        blob_path TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(source_id) REFERENCES source_identities(id)
                    );
                    CREATE TABLE claims (
                        id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        source_id TEXT,
                        text TEXT NOT NULL,
                        excerpt TEXT NOT NULL DEFAULT '',
                        entity TEXT NOT NULL DEFAULT '',
                        ticker TEXT NOT NULL DEFAULT '',
                        domain TEXT NOT NULL DEFAULT '',
                        tag TEXT NOT NULL DEFAULT 'GUESS',
                        confidence TEXT NOT NULL DEFAULT 'LOW',
                        verification_state TEXT NOT NULL DEFAULT 'pending',
                        published_at TEXT NOT NULL DEFAULT '',
                        observed_at TEXT NOT NULL,
                        as_of TEXT NOT NULL DEFAULT '',
                        source_url TEXT NOT NULL DEFAULT '',
                        conflict_flags_json TEXT NOT NULL DEFAULT '[]',
                        evidence_json TEXT NOT NULL DEFAULT '[]',
                        reviewer TEXT NOT NULL DEFAULT '',
                        review_reason TEXT NOT NULL DEFAULT '',
                        reviewed_at TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(document_id) REFERENCES documents(id),
                        FOREIGN KEY(source_id) REFERENCES source_identities(id)
                    );
                    CREATE INDEX idx_claims_scope ON claims(ticker, domain, verification_state);
                    CREATE TABLE discovery_candidates (
                        id TEXT PRIMARY KEY,
                        query TEXT NOT NULL,
                        domain TEXT NOT NULL DEFAULT '',
                        title TEXT NOT NULL DEFAULT '',
                        url TEXT NOT NULL,
                        snippet TEXT NOT NULL DEFAULT '',
                        source TEXT NOT NULL DEFAULT '',
                        observed_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        UNIQUE(query, url)
                    );
                    CREATE TABLE historical_episodes (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        start_at TEXT NOT NULL,
                        end_at TEXT NOT NULL,
                        archetypes_json TEXT NOT NULL,
                        drivers_json TEXT NOT NULL DEFAULT '[]',
                        outcomes_json TEXT NOT NULL DEFAULT '{}',
                        evidence_json TEXT NOT NULL DEFAULT '[]',
                        point_in_time_eligible INTEGER NOT NULL DEFAULT 0,
                        post_hoc INTEGER NOT NULL DEFAULT 1,
                        notes TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE event_contracts (
                        id TEXT PRIMARY KEY,
                        scope_type TEXT NOT NULL,
                        scope_id TEXT NOT NULL,
                        domain TEXT NOT NULL DEFAULT '',
                        horizon TEXT NOT NULL,
                        statement TEXT NOT NULL,
                        resolution_date TEXT NOT NULL,
                        criteria_json TEXT NOT NULL,
                        source_ids_json TEXT NOT NULL DEFAULT '[]',
                        parent_archetypes_json TEXT NOT NULL DEFAULT '[]',
                        dependency_ids_json TEXT NOT NULL DEFAULT '[]',
                        status TEXT NOT NULL DEFAULT 'open',
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX idx_contracts_scope ON event_contracts(scope_type, scope_id, horizon);
                    CREATE TABLE forecasts (
                        id TEXT PRIMARY KEY,
                        contract_id TEXT NOT NULL,
                        as_of TEXT NOT NULL,
                        probability_status TEXT NOT NULL,
                        probability REAL,
                        lower_bound REAL,
                        upper_bound REAL,
                        model_name TEXT NOT NULL,
                        model_version TEXT NOT NULL,
                        training_cutoff TEXT NOT NULL,
                        brier_skill REAL,
                        skill_ci_low REAL,
                        skill_ci_high REAL,
                        metrics_json TEXT NOT NULL DEFAULT '{}',
                        evidence_json TEXT NOT NULL DEFAULT '[]',
                        analogs_json TEXT NOT NULL DEFAULT '[]',
                        llm_involvement TEXT NOT NULL DEFAULT 'none',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(contract_id) REFERENCES event_contracts(id)
                    );
                    CREATE INDEX idx_forecasts_contract ON forecasts(contract_id, as_of);
                    CREATE TABLE resolutions (
                        id TEXT PRIMARY KEY,
                        contract_id TEXT NOT NULL,
                        forecast_id TEXT,
                        kind TEXT NOT NULL,
                        outcome INTEGER,
                        values_json TEXT NOT NULL DEFAULT '{}',
                        reason TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(contract_id) REFERENCES event_contracts(id),
                        FOREIGN KEY(forecast_id) REFERENCES forecasts(id)
                    );
                    CREATE INDEX idx_resolutions_contract ON resolutions(contract_id, created_at);
                    CREATE TABLE calibration_snapshots (
                        id TEXT PRIMARY KEY,
                        domain TEXT NOT NULL,
                        horizon TEXT NOT NULL,
                        as_of TEXT NOT NULL,
                        model_version TEXT NOT NULL,
                        eligible INTEGER NOT NULL,
                        metrics_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    PRAGMA user_version=1;
                    """
                )
                version = 1
            if version < 2:
                conn.execute(
                    "ALTER TABLE event_contracts "
                    "ADD COLUMN resolution_source TEXT NOT NULL DEFAULT ''"
                )
                conn.execute("PRAGMA user_version=2")

    def _seed_sources(self) -> None:
        seeds = [
            (
                "half_latte_liufei",
                "半拿鐵／劉飛",
                ["halflatte"],
                ["business_history"],
                [],
                "公司商業史",
            ),
            ("miula", "Miula／M觀點", ["miula"], ["company_strategy"], [], "公司與科技策略"),
            ("techwav", "科技浪 Tech.wav", ["techwav"], ["company_strategy"], [], "科技與 AI 產業"),
            (
                "stratechery",
                "Stratechery／Ben Thompson",
                ["stratechery"],
                ["company_strategy"],
                ["paid_content"],
                "僅處理使用者有權提供的內容",
            ),
            ("valley101", "矽谷101", ["valley101podcast"], ["technology"], [], "科技技術與產業鏈"),
            (
                "serenity_aleabitoreddit",
                "Serenity",
                ["aleabitoreddit"],
                ["stocks", "semiconductors"],
                [],
                "AI／半導體供應鏈",
            ),
            ("huang_jingzhe", "黃靖哲", [], ["stocks"], [], "與 Serenity 分離的來源身分"),
            (
                "bonnie_blockchain",
                "邦妮區塊鏈",
                [],
                ["crypto"],
                ["affiliate_exchange"],
                "加密內容可能含交易所推薦利益",
            ),
            (
                "youtubercrypto",
                "科幣託",
                ["youtubercrypto_"],
                ["crypto"],
                ["affiliate_exchange"],
                "加密內容可能含交易所推薦利益",
            ),
        ]
        with self._connect() as conn:
            for source_id, name, handles, domains, flags, notes in seeds:
                conn.execute(
                    """INSERT OR IGNORE INTO source_identities
                       (id, display_name, handles_json, domains_json, conflict_flags_json,
                        notes, active, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                    (
                        source_id,
                        name,
                        _dump(handles),
                        _dump(domains),
                        _dump(flags),
                        notes,
                        utc_now(),
                    ),
                )

    @staticmethod
    def _row(row: sqlite3.Row) -> dict:
        out = dict(row)
        object_fields = {
            "metadata_json",
            "outcomes_json",
            "criteria_json",
            "values_json",
            "metrics_json",
        }
        for key in list(out):
            if key.endswith("_json"):
                out[key[:-5]] = _load(out.pop(key), {} if key in object_fields else [])
        for key in ("active", "point_in_time_eligible", "post_hoc", "eligible"):
            if key in out:
                out[key] = bool(out[key])
        return out

    def save_blob(self, content: bytes, suffix: str = ".txt") -> tuple[str, Path]:
        digest = hashlib.sha256(content).hexdigest()
        clean_suffix = (
            suffix.lower()
            if suffix.lower() in {".md", ".txt", ".pdf", ".csv", ".json", ".vtt"}
            else ".txt"
        )
        path = self.blob_dir / f"{digest}{clean_suffix}"
        if not path.exists():
            path.write_bytes(content)
        return digest, path

    def add_document(
        self,
        *,
        content: bytes,
        title: str = "",
        source_url: str = "",
        source_id: str = "",
        media_type: str = "text/plain",
        published_at: str = "",
        observed_at: str = "",
        as_of: str = "",
        domain: str = "",
        metadata: Optional[dict] = None,
        suffix: str = ".txt",
    ) -> tuple[dict, bool]:
        digest, path = self.save_blob(content, suffix)
        now = utc_now()
        document_id = f"doc_{digest[:20]}"
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM documents WHERE sha256=?", (digest,)).fetchone()
            if existing:
                return self._row(existing), False
            conn.execute(
                """INSERT INTO documents
                   (id, sha256, title, source_url, source_id, media_type, published_at,
                    observed_at, as_of, domain, verification_state, blob_path,
                    metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
                (
                    document_id,
                    digest,
                    title,
                    source_url,
                    source_id or None,
                    media_type,
                    published_at,
                    observed_at or now,
                    as_of,
                    domain,
                    str(path),
                    _dump(metadata or {}),
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        return self._row(row), True

    def list_documents(self, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._row(r) for r in rows]

    def get_document(self, document_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        return self._row(row) if row else None

    def add_claim(
        self,
        *,
        document_id: str,
        text: str,
        excerpt: str = "",
        source_id: str = "",
        entity: str = "",
        ticker: str = "",
        domain: str = "",
        tag: str = "GUESS",
        confidence: str = "LOW",
        published_at: str = "",
        observed_at: str = "",
        as_of: str = "",
        source_url: str = "",
        conflict_flags: Optional[list] = None,
        evidence: Optional[list] = None,
    ) -> dict:
        require_choice(tag, CLAIM_TAGS, "tag")
        require_choice(confidence, CONFIDENCE_LEVELS, "confidence")
        if tag in {"FRAME", "GUESS"} and confidence not in {"LOW", "VERY LOW", "UNKNOWN"}:
            raise ValueError("FRAME and GUESS confidence cannot exceed LOW")
        now = utc_now()
        claim_id = _id("clm")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO claims
                   (id, document_id, source_id, text, excerpt, entity, ticker, domain, tag,
                    confidence, verification_state, published_at, observed_at, as_of,
                    source_url, conflict_flags_json, evidence_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    claim_id,
                    document_id,
                    source_id or None,
                    text,
                    excerpt,
                    entity,
                    ticker.upper(),
                    domain,
                    tag,
                    confidence,
                    published_at,
                    observed_at or now,
                    as_of,
                    source_url,
                    _dump(conflict_flags or []),
                    _dump(evidence or []),
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        return self._row(row)

    @staticmethod
    def evidence_allows_verified(evidence: Iterable[dict]) -> bool:
        rows = [e for e in evidence if isinstance(e, dict)]
        if any(e.get("kind") in {"quant", "official"} and e.get("verified") is True for e in rows):
            return True
        independent_secondary = {
            str(e.get("source_id") or e.get("url") or "")
            for e in rows
            if e.get("kind") == "secondary" and e.get("verified") is True
        }
        independent_secondary.discard("")
        return len(independent_secondary) >= 2

    def review_claim(
        self,
        claim_id: str,
        *,
        verification_state: str,
        tag: str,
        confidence: str,
        reviewer: str,
        reason: str,
        evidence: Optional[list] = None,
    ) -> dict:
        require_choice(verification_state, VERIFICATION_STATES, "verification_state")
        require_choice(tag, CLAIM_TAGS, "tag")
        require_choice(confidence, CONFIDENCE_LEVELS, "confidence")
        evidence_rows = evidence or []
        if tag in {"FRAME", "GUESS"} and confidence not in {"LOW", "VERY LOW", "UNKNOWN"}:
            raise ValueError("FRAME and GUESS confidence cannot exceed LOW")
        if verification_state == "verified" and not self.evidence_allows_verified(evidence_rows):
            raise ValueError(
                "verified claims need Quant/official evidence or two independent secondary sources"
            )
        with self._connect() as conn:
            found = conn.execute("SELECT id FROM claims WHERE id=?", (claim_id,)).fetchone()
            if not found:
                raise LookupError(f"unknown claim: {claim_id}")
            conn.execute(
                """UPDATE claims SET verification_state=?, tag=?, confidence=?, reviewer=?,
                   review_reason=?, reviewed_at=?, evidence_json=? WHERE id=?""",
                (
                    verification_state,
                    tag,
                    confidence,
                    reviewer,
                    reason,
                    utc_now(),
                    _dump(evidence_rows),
                    claim_id,
                ),
            )
            row = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        return self._row(row)

    def list_claims(
        self, *, ticker: str = "", domain: str = "", state: str = "", limit: int = 200
    ) -> list[dict]:
        clauses, params = [], []
        if ticker:
            clauses.append("ticker=?")
            params.append(ticker.upper())
        if domain:
            clauses.append("domain=?")
            params.append(domain)
        if state:
            clauses.append("verification_state=?")
            params.append(state)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(limit, 1000)))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM claims{where} ORDER BY created_at DESC LIMIT ?", params
            ).fetchall()
        return [self._row(r) for r in rows]

    def list_sources(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM source_identities ORDER BY display_name").fetchall()
        return [self._row(r) for r in rows]

    def get_source(self, source_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM source_identities WHERE id=?", (source_id,)
            ).fetchone()
        return self._row(row) if row else None

    def add_discovery_candidates(
        self, *, query: str, domain: str, candidates: Iterable[dict]
    ) -> list[dict]:
        now = utc_now()
        ids: list[str] = []
        with self._connect() as conn:
            for candidate in candidates:
                url = str(candidate.get("url") or "").strip()
                if not url:
                    continue
                candidate_id = _id("disc")
                conn.execute(
                    """INSERT OR IGNORE INTO discovery_candidates
                       (id, query, domain, title, url, snippet, source, observed_at,
                        status, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                    (
                        candidate_id,
                        query,
                        domain,
                        str(candidate.get("title") or ""),
                        url,
                        str(candidate.get("snippet") or candidate.get("text") or "")[:4000],
                        str(candidate.get("source") or "exa"),
                        now,
                        _dump(candidate.get("metadata") or {}),
                    ),
                )
                row = conn.execute(
                    "SELECT id FROM discovery_candidates WHERE query=? AND url=?", (query, url)
                ).fetchone()
                if row:
                    ids.append(str(row["id"]))
            if not ids:
                return []
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"SELECT * FROM discovery_candidates WHERE id IN ({placeholders})", ids
            ).fetchall()
        return [self._row(r) for r in rows]

    def list_discovery_candidates(self, *, status: str = "pending", limit: int = 200) -> list[dict]:
        where = " WHERE status=?" if status else ""
        params: list[Any] = [status] if status else []
        params.append(max(1, min(limit, 1000)))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM discovery_candidates{where} ORDER BY observed_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row(r) for r in rows]

    def review_discovery(self, candidate_id: str, status: str) -> dict:
        if status not in {"approved", "rejected"}:
            raise ValueError("discovery status must be approved or rejected")
        with self._connect() as conn:
            if not conn.execute(
                "SELECT 1 FROM discovery_candidates WHERE id=?", (candidate_id,)
            ).fetchone():
                raise LookupError(f"unknown discovery candidate: {candidate_id}")
            conn.execute(
                "UPDATE discovery_candidates SET status=? WHERE id=?", (status, candidate_id)
            )
            row = conn.execute(
                "SELECT * FROM discovery_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
        return self._row(row)

    def add_contract(
        self,
        *,
        scope_type: str,
        scope_id: str,
        domain: str,
        horizon: str,
        statement: str,
        resolution_date: str,
        criteria: dict,
        resolution_source: str,
        source_ids: Optional[list[str]] = None,
        parent_archetypes: Optional[list[str]] = None,
        dependency_ids: Optional[list[str]] = None,
    ) -> dict:
        require_choice(scope_type, SCOPE_TYPES, "scope_type")
        require_choice(horizon, HORIZONS, "horizon")
        if not statement.strip() or not resolution_date.strip() or not criteria:
            raise ValueError("statement, resolution_date, and criteria are required")
        if not resolution_source.strip():
            raise ValueError("resolution_source is required")
        try:
            datetime.strptime(resolution_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("resolution_date must use YYYY-MM-DD") from exc
        contract_id = _id("evt")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO event_contracts
                   (id, scope_type, scope_id, domain, horizon, statement, resolution_date,
                    criteria_json, resolution_source, source_ids_json, parent_archetypes_json,
                    dependency_ids_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    contract_id,
                    scope_type,
                    scope_id.upper() if scope_type == "ticker" else scope_id,
                    domain,
                    horizon,
                    statement,
                    resolution_date,
                    _dump(criteria),
                    resolution_source,
                    _dump(source_ids or []),
                    _dump(parent_archetypes or []),
                    _dump(dependency_ids or []),
                    utc_now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM event_contracts WHERE id=?", (contract_id,)
            ).fetchone()
        return self._row(row)

    def get_contract(self, contract_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM event_contracts WHERE id=?", (contract_id,)
            ).fetchone()
        return self._row(row) if row else None

    def list_contracts(self, scope_id: str = "", horizon: str = "") -> list[dict]:
        clauses, params = [], []
        if scope_id:
            clauses.append("scope_id=?")
            params.append(scope_id.upper())
        if horizon:
            clauses.append("horizon=?")
            params.append(horizon)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM event_contracts{where} ORDER BY created_at DESC", params
            ).fetchall()
        return [self._row(r) for r in rows]

    def add_forecast(
        self,
        *,
        contract_id: str,
        as_of: str,
        probability_status: str,
        probability: Optional[float],
        lower_bound: Optional[float],
        upper_bound: Optional[float],
        model_name: str,
        model_version: str,
        training_cutoff: str,
        brier_skill: Optional[float] = None,
        skill_ci_low: Optional[float] = None,
        skill_ci_high: Optional[float] = None,
        metrics: Optional[dict] = None,
        evidence: Optional[list] = None,
        analogs: Optional[list] = None,
        llm_involvement: str = "none",
    ) -> dict:
        require_choice(probability_status, PROBABILITY_STATUSES, "probability_status")
        if llm_involvement not in {"none", "narration_only"}:
            raise ValueError("forecast KPI path only allows llm_involvement none/narration_only")
        if probability_status != "calibrated":
            probability = lower_bound = upper_bound = None
        elif any(v is None for v in (probability, lower_bound, upper_bound)):
            raise ValueError("calibrated forecasts require probability and bounds")
        elif not (0 <= float(lower_bound) <= float(probability) <= float(upper_bound) <= 1):
            raise ValueError("probability bounds must satisfy 0 <= lower <= p <= upper <= 1")
        forecast_id = _id("fcst")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO forecasts
                   (id, contract_id, as_of, probability_status, probability, lower_bound,
                    upper_bound, model_name, model_version, training_cutoff, brier_skill,
                    skill_ci_low, skill_ci_high, metrics_json, evidence_json, analogs_json,
                    llm_involvement, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    forecast_id,
                    contract_id,
                    as_of,
                    probability_status,
                    probability,
                    lower_bound,
                    upper_bound,
                    model_name,
                    model_version,
                    training_cutoff,
                    brier_skill,
                    skill_ci_low,
                    skill_ci_high,
                    _dump(metrics or {}),
                    _dump(evidence or []),
                    _dump(analogs or []),
                    llm_involvement,
                    utc_now(),
                ),
            )
            row = conn.execute("SELECT * FROM forecasts WHERE id=?", (forecast_id,)).fetchone()
        return self._row(row)

    def list_forecasts(self, contract_id: str = "", limit: int = 200) -> list[dict]:
        where = " WHERE contract_id=?" if contract_id else ""
        params: list[Any] = [contract_id] if contract_id else []
        params.append(max(1, min(limit, 1000)))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM forecasts{where} ORDER BY created_at DESC, rowid DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row(r) for r in rows]

    def add_resolution(
        self,
        *,
        contract_id: str,
        outcome: Optional[int],
        reason: str,
        actor: str,
        kind: str = "auto",
        forecast_id: str = "",
        values: Optional[dict] = None,
    ) -> dict:
        require_choice(kind, RESOLUTION_KINDS, "kind")
        if outcome not in (0, 1, None):
            raise ValueError("outcome must be 0, 1, or null")
        if not reason.strip() or not actor.strip():
            raise ValueError("append-only resolutions require reason and actor")
        resolution_id = _id("res")
        with self._connect() as conn:
            if not conn.execute(
                "SELECT 1 FROM event_contracts WHERE id=?", (contract_id,)
            ).fetchone():
                raise LookupError(f"unknown contract: {contract_id}")
            conn.execute(
                """INSERT INTO resolutions
                   (id, contract_id, forecast_id, kind, outcome, values_json, reason, actor, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    resolution_id,
                    contract_id,
                    forecast_id or None,
                    kind,
                    outcome,
                    _dump(values or {}),
                    reason,
                    actor,
                    utc_now(),
                ),
            )
            row = conn.execute("SELECT * FROM resolutions WHERE id=?", (resolution_id,)).fetchone()
        return self._row(row)

    def list_resolutions(self, contract_id: str = "") -> list[dict]:
        where = " WHERE contract_id=?" if contract_id else ""
        params = [contract_id] if contract_id else []
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM resolutions{where} ORDER BY created_at, rowid", params
            ).fetchall()
        return [self._row(r) for r in rows]

    def effective_resolutions(self) -> dict[str, dict]:
        """Return the effective append-only resolution row for every contract."""
        grouped: dict[str, list[dict]] = {}
        for row in self.list_resolutions():
            if row["outcome"] in (0, 1):
                grouped.setdefault(row["contract_id"], []).append(row)
        out: dict[str, dict] = {}
        for contract_id, items in grouped.items():
            humans = [row for row in items if row["kind"] == "human_override"]
            out[contract_id] = humans[-1] if humans else items[-1]
        return out

    def effective_outcomes(self) -> dict[str, int]:
        """Latest human override wins; otherwise the latest automatic resolution wins."""
        return {
            contract_id: int(row["outcome"])
            for contract_id, row in self.effective_resolutions().items()
        }

    def add_calibration_snapshot(
        self,
        *,
        domain: str,
        horizon: str,
        as_of: str,
        model_version: str,
        eligible: bool,
        metrics: dict,
    ) -> dict:
        require_choice(horizon, HORIZONS, "horizon")
        snapshot_id = _id("cal")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO calibration_snapshots
                   (id, domain, horizon, as_of, model_version, eligible, metrics_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_id,
                    domain,
                    horizon,
                    as_of,
                    model_version,
                    int(eligible),
                    _dump(metrics),
                    utc_now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM calibration_snapshots WHERE id=?", (snapshot_id,)
            ).fetchone()
        return self._row(row)

    def list_calibration(self, domain: str = "", horizon: str = "") -> list[dict]:
        clauses, params = [], []
        if domain:
            clauses.append("domain=?")
            params.append(domain)
        if horizon:
            clauses.append("horizon=?")
            params.append(horizon)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM calibration_snapshots{where} ORDER BY created_at DESC", params
            ).fetchall()
        return [self._row(r) for r in rows]

    def add_episode(
        self,
        *,
        title: str,
        start_at: str,
        end_at: str,
        archetypes: list[str],
        drivers: Optional[list] = None,
        outcomes: Optional[dict] = None,
        evidence: Optional[list] = None,
        point_in_time_eligible: bool = False,
        post_hoc: bool = True,
        notes: str = "",
    ) -> dict:
        episode_id = _id("ep")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO historical_episodes
                   (id, title, start_at, end_at, archetypes_json, drivers_json,
                    outcomes_json, evidence_json, point_in_time_eligible, post_hoc,
                    notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode_id,
                    title,
                    start_at,
                    end_at,
                    _dump(archetypes),
                    _dump(drivers or []),
                    _dump(outcomes or {}),
                    _dump(evidence or []),
                    int(point_in_time_eligible),
                    int(post_hoc),
                    notes,
                    utc_now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM historical_episodes WHERE id=?", (episode_id,)
            ).fetchone()
        return self._row(row)

    def list_episodes(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM historical_episodes ORDER BY start_at DESC"
            ).fetchall()
        return [self._row(r) for r in rows]

    def source_scores(
        self, *, domain: str = "", horizon: str = "", half_life_days: float = 365.0
    ) -> list[dict]:
        resolutions = self.effective_resolutions()
        contracts = {c["id"]: c for c in self.list_contracts(horizon=horizon)}
        forecasts = self.list_forecasts(limit=1000)
        now = datetime.now(timezone.utc)
        per_source: dict[str, list[tuple[float, float, int]]] = {}
        all_outcomes: list[int] = []
        for forecast in forecasts:
            contract = contracts.get(forecast["contract_id"])
            resolution = resolutions.get(forecast["contract_id"])
            if not contract or not resolution or forecast["probability_status"] != "calibrated":
                continue
            if str(forecast["as_of"]) > str(contract["resolution_date"]):
                continue
            if str(forecast["created_at"]) > str(resolution["created_at"]):
                continue
            outcome = int(resolution["outcome"])
            if domain and contract["domain"] != domain:
                continue
            p = float(forecast["probability"])
            created = datetime.fromisoformat(forecast["created_at"].replace("Z", "+00:00"))
            age_days = max(0.0, (now - created.astimezone(timezone.utc)).total_seconds() / 86400)
            weight = math.exp(-math.log(2) * age_days / max(1.0, half_life_days))
            all_outcomes.append(outcome)
            for source_id in contract.get("source_ids", []):
                per_source.setdefault(source_id, []).append((p, weight, outcome))
        base_rate = sum(all_outcomes) / len(all_outcomes) if all_outcomes else 0.5
        base_brier = (
            max(1e-9, sum((base_rate - y) ** 2 for y in all_outcomes) / len(all_outcomes))
            if all_outcomes
            else 0.25
        )
        rows = []
        source_names = {s["id"]: s["display_name"] for s in self.list_sources()}
        for source_id, samples in per_source.items():
            total_w = sum(w for _, w, _ in samples) or 1.0
            brier = sum(w * (p - y) ** 2 for p, w, y in samples) / total_w
            log_loss = (
                -sum(
                    w
                    * (
                        y * math.log(min(1 - 1e-6, max(1e-6, p)))
                        + (1 - y) * math.log(min(1 - 1e-6, max(1e-6, 1 - p)))
                    )
                    for p, w, y in samples
                )
                / total_w
            )
            raw_skill = 1 - brier / base_brier
            shrink = total_w / (total_w + 10.0)
            shrunk_skill = raw_skill * shrink
            rows.append(
                {
                    "source_id": source_id,
                    "display_name": source_names.get(source_id, source_id),
                    "domain": domain,
                    "horizon": horizon,
                    "resolved": len(samples),
                    "effective_n": round(total_w, 4),
                    "brier": round(brier, 6),
                    "log_loss": round(log_loss, 6),
                    "brier_skill": round(raw_skill, 6),
                    "shrunk_skill": round(shrunk_skill, 6),
                    "weight": round(max(0.5, min(1.5, 1 + 0.5 * shrunk_skill)), 6),
                }
            )
        return sorted(rows, key=lambda r: (r["shrunk_skill"], r["effective_n"]), reverse=True)

    def status(self) -> dict:
        tables = (
            "documents",
            "claims",
            "discovery_candidates",
            "source_identities",
            "historical_episodes",
            "event_contracts",
            "forecasts",
            "resolutions",
            "calibration_snapshots",
        )
        with self._connect() as conn:
            counts = {
                t: int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in tables
            }
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        return {
            "root": str(self.root),
            "database": str(self.db_path),
            "schema_version": version,
            "counts": counts,
        }
