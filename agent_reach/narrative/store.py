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
    BOTTLENECK_STATES,
    BOTTLENECK_TRANSITIONS,
    CLAIM_TAGS,
    CONFIDENCE_LEVELS,
    EDGE_STATES,
    EDGE_TRANSITIONS,
    EDGE_TYPES,
    ENTITY_TYPES,
    EVIDENCE_GRADES,
    EVIDENCE_STANCES,
    HORIZONS,
    METHOD_PROFILE_STATES,
    PROBABILITY_STATUSES,
    RESEARCH_RUN_STATES,
    RESOLUTION_KINDS,
    SCOPE_TYPES,
    VALUATION_METHODS,
    VERIFICATION_STATES,
    json_safe,
    require_choice,
    utc_now,
)

SCHEMA_VERSION = 3


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
                version = 2
            if version < 3:
                backup_path = self.root / "narrative.sqlite3.pre-v3.bak"
                if self.db_path.exists() and not backup_path.exists():
                    with sqlite3.connect(backup_path) as backup:
                        conn.backup(backup)
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS research_runs (
                        id TEXT PRIMARY KEY, slice TEXT NOT NULL,
                        universe_scope TEXT NOT NULL DEFAULT '', as_of TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'running',
                        input_manifest_json TEXT NOT NULL DEFAULT '{}',
                        model_version TEXT NOT NULL DEFAULT '', prompt_version TEXT NOT NULL DEFAULT '',
                        started_at TEXT NOT NULL, completed_at TEXT NOT NULL DEFAULT ''
                    );
                    CREATE INDEX IF NOT EXISTS idx_research_runs_slice ON research_runs(slice, as_of);
                    CREATE TABLE IF NOT EXISTS research_packs (
                        id TEXT PRIMARY KEY, version INTEGER NOT NULL, run_id TEXT NOT NULL,
                        previous_pack_id TEXT, slice TEXT NOT NULL,
                        universe_scope TEXT NOT NULL DEFAULT '', as_of TEXT NOT NULL,
                        system_change TEXT NOT NULL DEFAULT '', constraint_type TEXT NOT NULL DEFAULT '',
                        constraint_statement TEXT NOT NULL DEFAULT '', scarce_layer TEXT NOT NULL DEFAULT '',
                        measurement_contract_json TEXT NOT NULL DEFAULT '{}', graph_id TEXT NOT NULL DEFAULT '',
                        tickers_json TEXT NOT NULL DEFAULT '[]', coverage_json TEXT NOT NULL DEFAULT '{}',
                        evidence_grade TEXT NOT NULL DEFAULT 'E', policy_exposure_json TEXT NOT NULL DEFAULT '[]',
                        historical_analogues_json TEXT NOT NULL DEFAULT '[]', next_move TEXT NOT NULL DEFAULT '',
                        failure_conditions_json TEXT NOT NULL DEFAULT '[]', content_hash TEXT NOT NULL UNIQUE,
                        payload_json TEXT NOT NULL DEFAULT '{}', frozen_at TEXT NOT NULL,
                        FOREIGN KEY(run_id) REFERENCES research_runs(id),
                        FOREIGN KEY(previous_pack_id) REFERENCES research_packs(id), UNIQUE(slice, version)
                    );
                    CREATE INDEX IF NOT EXISTS idx_research_packs_slice ON research_packs(slice, frozen_at);
                    CREATE TABLE IF NOT EXISTS source_coverage (
                        id TEXT PRIMARY KEY, run_id TEXT NOT NULL, source_id TEXT NOT NULL,
                        coverage_date TEXT NOT NULL, retrieved INTEGER NOT NULL DEFAULT 0,
                        deduplicated INTEGER NOT NULL DEFAULT 0, unavailable INTEGER NOT NULL DEFAULT 0,
                        rate_limited INTEGER NOT NULL DEFAULT 0, index_only INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'unknown', details_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL, FOREIGN KEY(run_id) REFERENCES research_runs(id),
                        UNIQUE(run_id, source_id, coverage_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_source_coverage_source ON source_coverage(source_id, coverage_date);
                    CREATE TABLE IF NOT EXISTS entities (
                        id TEXT PRIMARY KEY, kind TEXT NOT NULL, canonical_name TEXT NOT NULL,
                        ticker TEXT NOT NULL DEFAULT '', jurisdiction TEXT NOT NULL DEFAULT '',
                        metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
                        UNIQUE(kind, canonical_name, ticker)
                    );
                    CREATE TABLE IF NOT EXISTS entity_aliases (
                        id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, alias TEXT NOT NULL,
                        source_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                        FOREIGN KEY(entity_id) REFERENCES entities(id), UNIQUE(entity_id, alias)
                    );
                    CREATE TABLE IF NOT EXISTS causal_graphs (
                        id TEXT PRIMARY KEY, run_id TEXT NOT NULL, slice TEXT NOT NULL,
                        as_of TEXT NOT NULL, content_hash TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                        FOREIGN KEY(run_id) REFERENCES research_runs(id), UNIQUE(run_id, slice)
                    );
                    CREATE TABLE IF NOT EXISTS graph_nodes (
                        id TEXT PRIMARY KEY, graph_id TEXT NOT NULL, entity_id TEXT,
                        node_type TEXT NOT NULL, label TEXT NOT NULL, tag TEXT NOT NULL DEFAULT 'GUESS',
                        confidence TEXT NOT NULL DEFAULT 'LOW', metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL, FOREIGN KEY(graph_id) REFERENCES causal_graphs(id),
                        FOREIGN KEY(entity_id) REFERENCES entities(id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_graph_nodes_graph ON graph_nodes(graph_id);
                    CREATE TABLE IF NOT EXISTS graph_edges (
                        id TEXT PRIMARY KEY, graph_id TEXT NOT NULL, source_node_id TEXT NOT NULL,
                        target_node_id TEXT NOT NULL, edge_type TEXT NOT NULL,
                        state TEXT NOT NULL DEFAULT 'proposed', tag TEXT NOT NULL DEFAULT 'GUESS',
                        confidence TEXT NOT NULL DEFAULT 'LOW', valid_from TEXT NOT NULL DEFAULT '',
                        valid_to TEXT NOT NULL DEFAULT '', observed_at TEXT NOT NULL, contract_id TEXT,
                        metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
                        FOREIGN KEY(graph_id) REFERENCES causal_graphs(id),
                        FOREIGN KEY(source_node_id) REFERENCES graph_nodes(id),
                        FOREIGN KEY(target_node_id) REFERENCES graph_nodes(id),
                        FOREIGN KEY(contract_id) REFERENCES event_contracts(id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_graph_edges_graph ON graph_edges(graph_id, state);
                    CREATE TABLE IF NOT EXISTS edge_evidence (
                        id TEXT PRIMARY KEY, edge_id TEXT NOT NULL, claim_id TEXT,
                        stance TEXT NOT NULL, grade TEXT NOT NULL, source_id TEXT NOT NULL DEFAULT '',
                        source_url TEXT NOT NULL DEFAULT '', as_of TEXT NOT NULL DEFAULT '',
                        details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
                        FOREIGN KEY(edge_id) REFERENCES graph_edges(id), FOREIGN KEY(claim_id) REFERENCES claims(id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_edge_evidence_edge ON edge_evidence(edge_id, stance);
                    """
                )
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS bottleneck_contracts (
                        id TEXT PRIMARY KEY, run_id TEXT NOT NULL, graph_id TEXT NOT NULL DEFAULT '',
                        resource_entity_id TEXT, title TEXT NOT NULL, unit TEXT NOT NULL DEFAULT '',
                        available_supply REAL, demand_load REAL, alternative_supplier_count INTEGER,
                        expansion_lead_time TEXT NOT NULL DEFAULT '',
                        qualification_lead_time TEXT NOT NULL DEFAULT '',
                        easing_threshold_json TEXT NOT NULL DEFAULT '{}',
                        observation_source_ids_json TEXT NOT NULL DEFAULT '[]',
                        resolution_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidate',
                        dimensions_json TEXT NOT NULL DEFAULT '{}', evidence_claim_ids_json TEXT NOT NULL DEFAULT '[]',
                        created_at TEXT NOT NULL, resolved_at TEXT NOT NULL DEFAULT '',
                        FOREIGN KEY(run_id) REFERENCES research_runs(id),
                        FOREIGN KEY(resource_entity_id) REFERENCES entities(id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_bottleneck_run ON bottleneck_contracts(run_id, status);
                    CREATE TABLE IF NOT EXISTS method_profiles (
                        id TEXT PRIMARY KEY, source_id TEXT NOT NULL, version INTEGER NOT NULL,
                        name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', as_of TEXT NOT NULL,
                        dimensions_json TEXT NOT NULL DEFAULT '{}', signature_signals_json TEXT NOT NULL DEFAULT '[]',
                        invalidators_json TEXT NOT NULL DEFAULT '[]', evidence_claim_ids_json TEXT NOT NULL DEFAULT '[]',
                        content_hash TEXT NOT NULL, created_at TEXT NOT NULL,
                        FOREIGN KEY(source_id) REFERENCES source_identities(id),
                        UNIQUE(source_id, version), UNIQUE(content_hash)
                    );
                    CREATE TABLE IF NOT EXISTS valuation_snapshots (
                        id TEXT PRIMARY KEY, run_id TEXT NOT NULL, ticker TEXT NOT NULL,
                        as_of TEXT NOT NULL, method TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
                        low REAL, mid REAL, high REAL, assumptions_json TEXT NOT NULL DEFAULT '{}',
                        peers_json TEXT NOT NULL DEFAULT '[]', evidence_json TEXT NOT NULL DEFAULT '[]',
                        status TEXT NOT NULL DEFAULT 'insufficient_data', created_at TEXT NOT NULL,
                        FOREIGN KEY(run_id) REFERENCES research_runs(id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_valuation_run ON valuation_snapshots(run_id, ticker, method);
                    PRAGMA user_version=3;
                    """
                )

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
            ("sec_edgar", "SEC EDGAR", [], ["official_filings"], [], "美國公司申報原文"),
            ("congress_gov", "Congress.gov", [], ["official_policy"], [], "美國國會法案狀態"),
            (
                "federal_register",
                "Federal Register",
                [],
                ["official_policy"],
                [],
                "美國 proposed/final/effective 規則",
            ),
            (
                "regulations_gov",
                "Regulations.gov",
                [],
                ["official_policy"],
                [],
                "美國規則 docket 與文件",
            ),
            ("quant_artifacts", "Quant PIT artifacts", [], ["quant"], [], "只讀 PIT artifact"),
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

    def create_research_run(
        self,
        *,
        slice_id: str,
        universe_scope: str,
        as_of: str,
        input_manifest: Optional[dict] = None,
        model_version: str = "",
        prompt_version: str = "",
    ) -> dict:
        if not slice_id.strip() or not as_of.strip():
            raise ValueError("slice_id and as_of are required")
        run_id = _id("run")
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO research_runs
                   (id, slice, universe_scope, as_of, status, input_manifest_json,
                    model_version, prompt_version, started_at)
                   VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?)""",
                (run_id, slice_id, universe_scope, as_of, _dump(input_manifest or {}),
                 model_version, prompt_version, now),
            )
            row = conn.execute("SELECT * FROM research_runs WHERE id=?", (run_id,)).fetchone()
        return self._row(row)

    def finish_research_run(self, run_id: str, *, status: str = "complete") -> dict:
        require_choice(status, RESEARCH_RUN_STATES, "status")
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM research_runs WHERE id=?", (run_id,)).fetchone():
                raise LookupError(f"unknown research run: {run_id}")
            conn.execute(
                "UPDATE research_runs SET status=?, completed_at=? WHERE id=?",
                (status, utc_now(), run_id),
            )
            row = conn.execute("SELECT * FROM research_runs WHERE id=?", (run_id,)).fetchone()
        return self._row(row)

    def get_research_run(self, run_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM research_runs WHERE id=?", (run_id,)).fetchone()
        return self._row(row) if row else None

    def list_research_runs(self, *, slice_id: str = "", limit: int = 100) -> list[dict]:
        where = " WHERE slice=?" if slice_id else ""
        params: list[Any] = [slice_id] if slice_id else []
        params.append(max(1, min(limit, 1000)))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM research_runs{where} ORDER BY started_at DESC, rowid DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row(row) for row in rows]

    def upsert_source_coverage(
        self,
        *,
        run_id: str,
        source_id: str,
        coverage_date: str,
        retrieved: int = 0,
        deduplicated: int = 0,
        unavailable: int = 0,
        rate_limited: int = 0,
        index_only: int = 0,
        status: str = "unknown",
        details: Optional[dict] = None,
    ) -> dict:
        coverage_id = _id("cov")
        values = tuple(max(0, int(value)) for value in (
            retrieved, deduplicated, unavailable, rate_limited, index_only
        ))
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO source_coverage
                   (id, run_id, source_id, coverage_date, retrieved, deduplicated,
                    unavailable, rate_limited, index_only, status, details_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(run_id, source_id, coverage_date) DO UPDATE SET
                    retrieved=excluded.retrieved, deduplicated=excluded.deduplicated,
                    unavailable=excluded.unavailable, rate_limited=excluded.rate_limited,
                    index_only=excluded.index_only, status=excluded.status,
                    details_json=excluded.details_json""",
                (coverage_id, run_id, source_id, coverage_date, *values,
                 status, _dump(details or {}), utc_now()),
            )
            row = conn.execute(
                "SELECT * FROM source_coverage WHERE run_id=? AND source_id=? AND coverage_date=?",
                (run_id, source_id, coverage_date),
            ).fetchone()
        return self._row(row)

    def list_source_coverage(
        self, *, run_id: str = "", source_id: str = "", limit: int = 1000
    ) -> list[dict]:
        clauses, params = [], []
        if run_id:
            clauses.append("run_id=?")
            params.append(run_id)
        if source_id:
            clauses.append("source_id=?")
            params.append(source_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(limit, 5000)))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM source_coverage{where} ORDER BY coverage_date DESC LIMIT ?", params
            ).fetchall()
        return [self._row(row) for row in rows]

    def add_entity(
        self,
        *,
        kind: str,
        canonical_name: str,
        ticker: str = "",
        jurisdiction: str = "",
        metadata: Optional[dict] = None,
    ) -> dict:
        require_choice(kind, ENTITY_TYPES, "kind")
        if not canonical_name.strip():
            raise ValueError("canonical_name is required")
        entity_id = _id("ent")
        normalized_ticker = ticker.upper().strip()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO entities
                   (id, kind, canonical_name, ticker, jurisdiction, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entity_id, kind, canonical_name.strip(), normalized_ticker,
                 jurisdiction, _dump(metadata or {}), utc_now()),
            )
            row = conn.execute(
                "SELECT * FROM entities WHERE kind=? AND canonical_name=? AND ticker=?",
                (kind, canonical_name.strip(), normalized_ticker),
            ).fetchone()
        return self._row(row)

    def add_entity_alias(self, entity_id: str, alias: str, *, source_id: str = "") -> dict:
        if not alias.strip():
            raise ValueError("alias is required")
        alias_id = _id("alias")
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO entity_aliases
                   (id, entity_id, alias, source_id, created_at) VALUES (?, ?, ?, ?, ?)""",
                (alias_id, entity_id, alias.strip(), source_id, utc_now()),
            )
            row = conn.execute(
                "SELECT * FROM entity_aliases WHERE entity_id=? AND alias=?",
                (entity_id, alias.strip()),
            ).fetchone()
        return self._row(row)

    def list_entities(self, *, kind: str = "", ticker: str = "") -> list[dict]:
        clauses, params = [], []
        if kind:
            require_choice(kind, ENTITY_TYPES, "kind")
            clauses.append("kind=?")
            params.append(kind)
        if ticker:
            clauses.append("ticker=?")
            params.append(ticker.upper())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM entities{where} ORDER BY kind, canonical_name", params
            ).fetchall()
        return [self._row(row) for row in rows]

    def create_graph(self, *, run_id: str, slice_id: str, as_of: str) -> dict:
        graph_id = _id("graph")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO causal_graphs
                   (id, run_id, slice, as_of, created_at) VALUES (?, ?, ?, ?, ?)""",
                (graph_id, run_id, slice_id, as_of, utc_now()),
            )
            row = conn.execute("SELECT * FROM causal_graphs WHERE id=?", (graph_id,)).fetchone()
        return self._row(row)

    def add_graph_node(
        self,
        *,
        graph_id: str,
        node_type: str,
        label: str,
        entity_id: str = "",
        tag: str = "GUESS",
        confidence: str = "LOW",
        metadata: Optional[dict] = None,
    ) -> dict:
        require_choice(node_type, ENTITY_TYPES, "node_type")
        require_choice(tag, CLAIM_TAGS, "tag")
        require_choice(confidence, CONFIDENCE_LEVELS, "confidence")
        if tag in {"FRAME", "GUESS"} and confidence not in {"LOW", "VERY LOW", "UNKNOWN"}:
            raise ValueError("FRAME and GUESS confidence cannot exceed LOW")
        node_id = _id("node")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO graph_nodes
                   (id, graph_id, entity_id, node_type, label, tag, confidence,
                    metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (node_id, graph_id, entity_id or None, node_type, label, tag, confidence,
                 _dump(metadata or {}), utc_now()),
            )
            row = conn.execute("SELECT * FROM graph_nodes WHERE id=?", (node_id,)).fetchone()
        return self._row(row)

    def add_graph_edge(
        self,
        *,
        graph_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        state: str = "proposed",
        tag: str = "GUESS",
        confidence: str = "LOW",
        valid_from: str = "",
        valid_to: str = "",
        observed_at: str = "",
        contract_id: str = "",
        metadata: Optional[dict] = None,
    ) -> dict:
        require_choice(edge_type, EDGE_TYPES, "edge_type")
        require_choice(state, EDGE_STATES, "state")
        require_choice(tag, CLAIM_TAGS, "tag")
        require_choice(confidence, CONFIDENCE_LEVELS, "confidence")
        if tag in {"FRAME", "GUESS"} and confidence not in {"LOW", "VERY LOW", "UNKNOWN"}:
            raise ValueError("FRAME and GUESS confidence cannot exceed LOW")
        edge_id = _id("edge")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO graph_edges
                   (id, graph_id, source_node_id, target_node_id, edge_type, state,
                    tag, confidence, valid_from, valid_to, observed_at, contract_id,
                    metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (edge_id, graph_id, source_node_id, target_node_id, edge_type, state,
                 tag, confidence, valid_from, valid_to, observed_at or utc_now(),
                 contract_id or None, _dump(metadata or {}), utc_now()),
            )
            row = conn.execute("SELECT * FROM graph_edges WHERE id=?", (edge_id,)).fetchone()
        return self._row(row)

    def add_edge_evidence(
        self,
        *,
        edge_id: str,
        stance: str,
        grade: str,
        claim_id: str = "",
        source_id: str = "",
        source_url: str = "",
        as_of: str = "",
        details: Optional[dict] = None,
    ) -> dict:
        require_choice(stance, EVIDENCE_STANCES, "stance")
        require_choice(grade, EVIDENCE_GRADES, "grade")
        evidence_id = _id("eev")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO edge_evidence
                   (id, edge_id, claim_id, stance, grade, source_id, source_url,
                    as_of, details_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (evidence_id, edge_id, claim_id or None, stance, grade, source_id,
                 source_url, as_of, _dump(details or {}), utc_now()),
            )
            row = conn.execute("SELECT * FROM edge_evidence WHERE id=?", (evidence_id,)).fetchone()
        return self._row(row)

    def review_graph_edge(
        self,
        edge_id: str,
        *,
        state: str,
        tag: str,
        confidence: str,
        reviewer: str,
        reason: str,
        evidence: Optional[list[dict]] = None,
    ) -> dict:
        """Apply an evidence-gated edge transition and keep an audit note."""
        require_choice(state, EDGE_STATES, "state")
        require_choice(tag, CLAIM_TAGS, "tag")
        require_choice(confidence, CONFIDENCE_LEVELS, "confidence")
        if not reviewer.strip() or not reason.strip():
            raise ValueError("reviewer and reason are required")
        if tag in {"FRAME", "GUESS"} and confidence not in {"LOW", "VERY LOW", "UNKNOWN"}:
            raise ValueError("FRAME and GUESS confidence cannot exceed LOW")
        incoming = evidence or []
        for item in incoming:
            require_choice(str(item.get("stance") or ""), EVIDENCE_STANCES, "stance")
            require_choice(str(item.get("grade") or ""), EVIDENCE_GRADES, "grade")
        now = utc_now()
        with self._connect() as conn:
            current_row = conn.execute(
                "SELECT * FROM graph_edges WHERE id=?", (edge_id,)
            ).fetchone()
            if not current_row:
                raise LookupError(f"unknown graph edge: {edge_id}")
            current = self._row(current_row)
            if state == current["state"]:
                raise ValueError("edge transition must change state")
            if state not in EDGE_TRANSITIONS[current["state"]]:
                raise ValueError(f"invalid edge transition: {current['state']} -> {state}")
            existing_rows = conn.execute(
                "SELECT * FROM edge_evidence WHERE edge_id=? ORDER BY rowid", (edge_id,)
            ).fetchall()
            combined = [self._row(row) for row in existing_rows] + incoming
            claim_ids = sorted({str(row.get("claim_id") or "") for row in combined if row.get("claim_id")})
            verified_claim_ids: set[str] = set()
            if claim_ids:
                marks = ",".join("?" for _ in claim_ids)
                verified_claim_ids = {
                    row["id"]
                    for row in conn.execute(
                        f"SELECT id FROM claims WHERE id IN ({marks}) AND verification_state='verified'",
                        claim_ids,
                    ).fetchall()
                }

            def strong(stance: str) -> bool:
                eligible = [
                    row for row in combined
                    if row.get("stance") == stance
                    and row.get("grade") in {"A", "B"}
                    and row.get("claim_id") in verified_claim_ids
                ]
                if any(row.get("grade") == "A" for row in eligible):
                    return True
                independent_b = {
                    str(row.get("source_id") or "")
                    for row in eligible if row.get("grade") == "B" and row.get("source_id")
                }
                return len(independent_b) >= 2

            if state == "supported" and not any(
                row.get("stance") == "support" and row.get("grade") in {"A", "B", "C", "D"}
                for row in combined
            ):
                raise ValueError("supported edges require supporting evidence")
            if state == "verified" and (not strong("support") or strong("refute")):
                raise ValueError("verified edges require strong reviewed support and no strong refute")
            if state == "refuted" and not strong("refute"):
                raise ValueError("refuted edges require strong reviewed refuting evidence")
            for item in incoming:
                conn.execute(
                    """INSERT INTO edge_evidence
                       (id, edge_id, claim_id, stance, grade, source_id, source_url,
                        as_of, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        _id("eev"), edge_id, str(item.get("claim_id") or "") or None,
                        str(item["stance"]), str(item["grade"]),
                        str(item.get("source_id") or ""), str(item.get("source_url") or ""),
                        str(item.get("as_of") or ""), _dump(item.get("details") or {}), now,
                    ),
                )
            metadata = current.get("metadata") or {}
            metadata.setdefault("reviews", []).append(
                {"from": current["state"], "to": state, "reviewer": reviewer,
                 "reason": reason, "at": now}
            )
            conn.execute(
                "UPDATE graph_edges SET state=?, tag=?, confidence=?, metadata_json=? WHERE id=?",
                (state, tag, confidence, _dump(metadata), edge_id),
            )
            updated = conn.execute("SELECT * FROM graph_edges WHERE id=?", (edge_id,)).fetchone()
            evidence_rows = conn.execute(
                "SELECT * FROM edge_evidence WHERE edge_id=? ORDER BY rowid", (edge_id,)
            ).fetchall()
        result = self._row(updated)
        result["evidence"] = [self._row(row) for row in evidence_rows]
        return result

    def get_graph(self, graph_id: str) -> Optional[dict]:
        with self._connect() as conn:
            graph = conn.execute("SELECT * FROM causal_graphs WHERE id=?", (graph_id,)).fetchone()
            if not graph:
                return None
            nodes = conn.execute(
                "SELECT * FROM graph_nodes WHERE graph_id=? ORDER BY rowid", (graph_id,)
            ).fetchall()
            edges = conn.execute(
                "SELECT * FROM graph_edges WHERE graph_id=? ORDER BY rowid", (graph_id,)
            ).fetchall()
            edge_ids = [row["id"] for row in edges]
            evidence_by_edge: dict[str, list[dict]] = {edge_id: [] for edge_id in edge_ids}
            if edge_ids:
                marks = ",".join("?" for _ in edge_ids)
                evidence = conn.execute(
                    f"SELECT * FROM edge_evidence WHERE edge_id IN ({marks}) ORDER BY rowid",
                    edge_ids,
                ).fetchall()
                for row in evidence:
                    evidence_by_edge[row["edge_id"]].append(self._row(row))
        payload = self._row(graph)
        payload["nodes"] = [self._row(row) for row in nodes]
        payload["edges"] = []
        for row in edges:
            edge = self._row(row)
            edge["evidence"] = evidence_by_edge.get(edge["id"], [])
            payload["edges"].append(edge)
        return payload

    def list_graphs(self, *, run_id: str = "", slice_id: str = "") -> list[dict]:
        clauses, params = [], []
        if run_id:
            clauses.append("run_id=?")
            params.append(run_id)
        if slice_id:
            clauses.append("slice=?")
            params.append(slice_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM causal_graphs{where} ORDER BY created_at DESC", params
            ).fetchall()
        return [self._row(row) for row in rows]

    def add_bottleneck_contract(
        self,
        *,
        run_id: str,
        title: str,
        resolution_date: str,
        graph_id: str = "",
        resource_entity_id: str = "",
        unit: str = "",
        available_supply: Optional[float] = None,
        demand_load: Optional[float] = None,
        alternative_supplier_count: Optional[int] = None,
        expansion_lead_time: str = "",
        qualification_lead_time: str = "",
        easing_threshold: Optional[dict] = None,
        observation_source_ids: Optional[list[str]] = None,
        status: str = "candidate",
        dimensions: Optional[dict] = None,
        evidence_claim_ids: Optional[list[str]] = None,
    ) -> dict:
        require_choice(status, BOTTLENECK_STATES, "status")
        if not title.strip() or not resolution_date.strip():
            raise ValueError("title and resolution_date are required")
        strong_dimensions = [
            key for key, value in (dimensions or {}).items()
            if isinstance(value, dict) and value.get("grade") in {"A", "B"}
        ]
        if status == "observed" and len(strong_dimensions) < 2:
            raise ValueError("observed bottlenecks require A/B evidence in two dimensions")
        bottleneck_id = _id("bnk")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO bottleneck_contracts
                   (id, run_id, graph_id, resource_entity_id, title, unit,
                    available_supply, demand_load, alternative_supplier_count,
                    expansion_lead_time, qualification_lead_time, easing_threshold_json,
                    observation_source_ids_json, resolution_date, status, dimensions_json,
                    evidence_claim_ids_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (bottleneck_id, run_id, graph_id, resource_entity_id or None, title, unit,
                 available_supply, demand_load, alternative_supplier_count,
                 expansion_lead_time, qualification_lead_time, _dump(easing_threshold or {}),
                 _dump(observation_source_ids or []), resolution_date, status,
                 _dump(dimensions or {}), _dump(evidence_claim_ids or []), utc_now()),
            )
            row = conn.execute(
                "SELECT * FROM bottleneck_contracts WHERE id=?", (bottleneck_id,)
            ).fetchone()
        return self._row(row)

    def list_bottlenecks(self, *, run_id: str = "", status: str = "") -> list[dict]:
        clauses, params = [], []
        if run_id:
            clauses.append("run_id=?")
            params.append(run_id)
        if status:
            require_choice(status, BOTTLENECK_STATES, "status")
            clauses.append("status=?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM bottleneck_contracts{where} ORDER BY created_at DESC", params
            ).fetchall()
        return [self._row(row) for row in rows]

    def transition_bottleneck(
        self,
        bottleneck_id: str,
        *,
        status: str,
        reviewer: str,
        reason: str,
        dimensions: Optional[dict] = None,
        evidence_claim_ids: Optional[list[str]] = None,
    ) -> dict:
        require_choice(status, BOTTLENECK_STATES, "status")
        if not reviewer.strip() or not reason.strip():
            raise ValueError("reviewer and reason are required")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bottleneck_contracts WHERE id=?", (bottleneck_id,)
            ).fetchone()
            if not row:
                raise LookupError(f"unknown bottleneck: {bottleneck_id}")
            current = self._row(row)
            if status not in BOTTLENECK_TRANSITIONS[current["status"]]:
                raise ValueError(
                    f"invalid bottleneck transition: {current['status']} -> {status}"
                )
            merged_dimensions = dict(current.get("dimensions") or {})
            merged_dimensions.update(dimensions or {})
            strong_dimensions = [
                key for key, value in merged_dimensions.items()
                if isinstance(value, dict) and value.get("grade") in {"A", "B"}
            ]
            if status == "observed" and len(strong_dimensions) < 2:
                raise ValueError("observed bottlenecks require A/B evidence in two dimensions")
            if status in {"easing", "resolved"} and not current.get("easing_threshold"):
                raise ValueError("easing/resolved bottlenecks require an easing threshold")
            reviews = list(merged_dimensions.get("_reviews") or [])
            reviews.append(
                {"from": current["status"], "to": status, "reviewer": reviewer,
                 "reason": reason, "at": utc_now()}
            )
            merged_dimensions["_reviews"] = reviews
            merged_claim_ids = sorted(set(
                (current.get("evidence_claim_ids") or []) + (evidence_claim_ids or [])
            ))
            resolved_at = utc_now() if status == "resolved" else ""
            conn.execute(
                """UPDATE bottleneck_contracts
                   SET status=?, dimensions_json=?, evidence_claim_ids_json=?, resolved_at=?
                   WHERE id=?""",
                (status, _dump(merged_dimensions), _dump(merged_claim_ids),
                 resolved_at, bottleneck_id),
            )
            updated = conn.execute(
                "SELECT * FROM bottleneck_contracts WHERE id=?", (bottleneck_id,)
            ).fetchone()
        return self._row(updated)

    def add_method_profile(
        self,
        *,
        source_id: str,
        name: str,
        as_of: str,
        dimensions: dict,
        signature_signals: list,
        invalidators: list,
        evidence_claim_ids: Optional[list[str]] = None,
        status: str = "draft",
    ) -> tuple[dict, bool]:
        require_choice(status, METHOD_PROFILE_STATES, "status")
        payload = {
            "source_id": source_id,
            "name": name,
            "as_of": as_of,
            "dimensions": dimensions,
            "signature_signals": signature_signals,
            "invalidators": invalidators,
            "evidence_claim_ids": evidence_claim_ids or [],
        }
        digest = hashlib.sha256(_dump(payload).encode("utf-8")).hexdigest()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM method_profiles WHERE content_hash=?", (digest,)
            ).fetchone()
            if existing:
                return self._row(existing), False
            version = int(conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM method_profiles WHERE source_id=?",
                (source_id,),
            ).fetchone()[0]) + 1
            profile_id = _id("method")
            conn.execute(
                """INSERT INTO method_profiles
                   (id, source_id, version, name, status, as_of, dimensions_json,
                    signature_signals_json, invalidators_json, evidence_claim_ids_json,
                    content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (profile_id, source_id, version, name, status, as_of, _dump(dimensions),
                 _dump(signature_signals), _dump(invalidators), _dump(evidence_claim_ids or []),
                 digest, utc_now()),
            )
            row = conn.execute("SELECT * FROM method_profiles WHERE id=?", (profile_id,)).fetchone()
        return self._row(row), True

    def list_method_profiles(self, *, source_id: str = "") -> list[dict]:
        where = " WHERE source_id=?" if source_id else ""
        params = [source_id] if source_id else []
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM method_profiles{where} ORDER BY source_id, version DESC", params
            ).fetchall()
        return [self._row(row) for row in rows]

    def add_valuation_snapshot(
        self,
        *,
        run_id: str,
        ticker: str,
        as_of: str,
        method: str,
        currency: str = "USD",
        low: Optional[float] = None,
        mid: Optional[float] = None,
        high: Optional[float] = None,
        assumptions: Optional[dict] = None,
        peers: Optional[list] = None,
        evidence: Optional[list] = None,
        status: str = "insufficient_data",
    ) -> dict:
        require_choice(method, VALUATION_METHODS, "method")
        values = [value for value in (low, mid, high) if value is not None]
        if values and len(values) != 3:
            raise ValueError("valuation ranges require low, mid, and high")
        if values and not (float(low) <= float(mid) <= float(high)):
            raise ValueError("valuation range must satisfy low <= mid <= high")
        valuation_id = _id("val")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO valuation_snapshots
                   (id, run_id, ticker, as_of, method, currency, low, mid, high,
                    assumptions_json, peers_json, evidence_json, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (valuation_id, run_id, ticker.upper(), as_of, method, currency,
                 low, mid, high, _dump(assumptions or {}), _dump(peers or []),
                 _dump(evidence or []), status, utc_now()),
            )
            row = conn.execute(
                "SELECT * FROM valuation_snapshots WHERE id=?", (valuation_id,)
            ).fetchone()
        return self._row(row)

    def list_valuations(self, *, run_id: str = "", ticker: str = "") -> list[dict]:
        clauses, params = [], []
        if run_id:
            clauses.append("run_id=?")
            params.append(run_id)
        if ticker:
            clauses.append("ticker=?")
            params.append(ticker.upper())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM valuation_snapshots{where} ORDER BY created_at DESC", params
            ).fetchall()
        return [self._row(row) for row in rows]

    def freeze_research_pack(self, *, run_id: str, payload: dict) -> tuple[dict, bool]:
        run = self.get_research_run(run_id)
        if not run:
            raise LookupError(f"unknown research run: {run_id}")
        required = (
            "slice", "universe_scope", "as_of", "system_change", "constraint_type",
            "constraint_statement", "scarce_layer", "measurement_contract", "tickers",
            "coverage", "evidence_grade", "policy_exposure", "historical_analogues",
            "next_move", "failure_conditions",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError("research pack missing: " + ", ".join(missing))
        require_choice(str(payload["evidence_grade"]), EVIDENCE_GRADES, "evidence_grade")
        normalized = json_safe(payload)
        hash_contract = normalized.get("content_contract") or normalized
        digest = hashlib.sha256(_dump(hash_contract).encode("utf-8")).hexdigest()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM research_packs WHERE content_hash=?", (digest,)
            ).fetchone()
            if existing:
                return self._row(existing), False
            previous = conn.execute(
                "SELECT * FROM research_packs WHERE slice=? ORDER BY version DESC LIMIT 1",
                (str(payload["slice"]),),
            ).fetchone()
            version = int(previous["version"]) + 1 if previous else 1
            pack_id = _id("pack")
            conn.execute(
                """INSERT INTO research_packs
                   (id, version, run_id, previous_pack_id, slice, universe_scope, as_of,
                    system_change, constraint_type, constraint_statement, scarce_layer,
                    measurement_contract_json, graph_id, tickers_json, coverage_json,
                    evidence_grade, policy_exposure_json, historical_analogues_json,
                    next_move, failure_conditions_json, content_hash, payload_json, frozen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pack_id, version, run_id, previous["id"] if previous else None,
                 str(payload["slice"]), str(payload["universe_scope"]), str(payload["as_of"]),
                 str(payload["system_change"]), str(payload["constraint_type"]),
                 str(payload["constraint_statement"]), str(payload["scarce_layer"]),
                 _dump(payload["measurement_contract"]), str(payload.get("graph_id") or ""),
                 _dump(payload["tickers"]), _dump(payload["coverage"]),
                 str(payload["evidence_grade"]), _dump(payload["policy_exposure"]),
                 _dump(payload["historical_analogues"]), str(payload["next_move"]),
                 _dump(payload["failure_conditions"]), digest, _dump(normalized), utc_now()),
            )
            row = conn.execute("SELECT * FROM research_packs WHERE id=?", (pack_id,)).fetchone()
        return self._row(row), True

    def get_research_pack(self, pack_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM research_packs WHERE id=?", (pack_id,)).fetchone()
        return self._row(row) if row else None

    def list_research_packs(self, *, slice_id: str = "", limit: int = 100) -> list[dict]:
        where = " WHERE slice=?" if slice_id else ""
        params: list[Any] = [slice_id] if slice_id else []
        params.append(max(1, min(limit, 1000)))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM research_packs{where} ORDER BY frozen_at DESC, rowid DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row(row) for row in rows]

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
            "research_runs",
            "research_packs",
            "source_coverage",
            "entities",
            "causal_graphs",
            "graph_nodes",
            "graph_edges",
            "edge_evidence",
            "bottleneck_contracts",
            "method_profiles",
            "valuation_snapshots",
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
