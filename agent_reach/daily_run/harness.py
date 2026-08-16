# -*- coding: utf-8
"""Continual harness for daily-run self-learning (prime-agent inspired, job-boundary refine)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

HarnessKind = Literal["memory", "policy", "playbook"]

_KINDS: tuple[HarnessKind, ...] = ("memory", "policy", "playbook")
_SCHEMA_VERSION = 1


def harness_dir() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "harness"


def _state_path() -> Path:
    return harness_dir() / "harness_state.json"


def _refinements_path() -> Path:
    return harness_dir() / "refinements.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str, *, limit: int = 48) -> str:
    raw = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", str(text).strip()).strip("_")
    if not raw:
        raw = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return raw[:limit]


@dataclass
class HarnessEntry:
    id: str
    kind: HarnessKind
    title: str
    content: str
    source: str = ""
    job: str = ""
    evidence: str = ""
    created_at: str = ""
    updated_at: str = ""
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RefinementEdit:
    action: str
    kind: HarnessKind
    entry_id: str
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RefinementEvent:
    id: str
    job: str
    trigger: str
    changes: list[str] = field(default_factory=list)
    evidence: str = ""
    edits: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HarnessState:
    schema: int = _SCHEMA_VERSION
    entries: dict[str, dict[str, HarnessEntry]] = field(default_factory=dict)
    refinements: list[RefinementEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        for kind in _KINDS:
            self.entries.setdefault(kind, {})

    @classmethod
    def load(cls, path: Optional[Path] = None) -> HarnessState:
        p = path or _state_path()
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        state = cls(schema=int(data.get("schema") or _SCHEMA_VERSION))
        for kind in _KINDS:
            block = (data.get("entries") or {}).get(kind) or {}
            if isinstance(block, dict):
                for entry_id, raw in block.items():
                    if isinstance(raw, dict):
                        state.entries[kind][str(entry_id)] = HarnessEntry(
                            id=str(raw.get("id") or entry_id),
                            kind=kind,
                            title=str(raw.get("title") or entry_id),
                            content=str(raw.get("content") or ""),
                            source=str(raw.get("source") or ""),
                            job=str(raw.get("job") or ""),
                            evidence=str(raw.get("evidence") or ""),
                            created_at=str(raw.get("created_at") or ""),
                            updated_at=str(raw.get("updated_at") or ""),
                            version=int(raw.get("version") or 1),
                        )
        for raw in data.get("refinements") or []:
            if isinstance(raw, dict):
                state.refinements.append(
                    RefinementEvent(
                        id=str(raw.get("id") or ""),
                        job=str(raw.get("job") or ""),
                        trigger=str(raw.get("trigger") or ""),
                        changes=[str(x) for x in (raw.get("changes") or [])],
                        evidence=str(raw.get("evidence") or ""),
                        edits=list(raw.get("edits") or []),
                        created_at=str(raw.get("created_at") or ""),
                    )
                )
        return state

    def save(self, path: Optional[Path] = None) -> Path:
        p = path or _state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": self.schema,
            "updated_at": _now_iso(),
            "entries": {
                kind: {eid: entry.to_dict() for eid, entry in bucket.items()}
                for kind, bucket in self.entries.items()
            },
            "refinements": [event.to_dict() for event in self.refinements[-200:]],
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return p

    def get(self, kind: HarnessKind, entry_id: str) -> Optional[HarnessEntry]:
        return self.entries.get(kind, {}).get(entry_id)

    def upsert(
        self,
        kind: HarnessKind,
        entry_id: str,
        *,
        title: str,
        content: str,
        source: str = "",
        job: str = "",
        evidence: str = "",
    ) -> tuple[HarnessEntry, RefinementEdit]:
        bucket = self.entries.setdefault(kind, {})
        existing = bucket.get(entry_id)
        now = _now_iso()
        if existing:
            before = existing.to_dict()
            if existing.content == content and existing.title == title:
                return existing, RefinementEdit("noop", kind, entry_id, before=before, after=before)
            entry = HarnessEntry(
                id=entry_id,
                kind=kind,
                title=title,
                content=content,
                source=source or existing.source,
                job=job or existing.job,
                evidence=evidence or existing.evidence,
                created_at=existing.created_at or now,
                updated_at=now,
                version=int(existing.version or 1) + 1,
            )
            action = "update"
        else:
            before = None
            entry = HarnessEntry(
                id=entry_id,
                kind=kind,
                title=title,
                content=content,
                source=source,
                job=job,
                evidence=evidence,
                created_at=now,
                updated_at=now,
                version=1,
            )
            action = "create"
        bucket[entry_id] = entry
        return entry, RefinementEdit(action, kind, entry_id, before=before, after=entry.to_dict())

    def delete(self, kind: HarnessKind, entry_id: str) -> Optional[RefinementEdit]:
        bucket = self.entries.get(kind) or {}
        existing = bucket.pop(entry_id, None)
        if existing is None:
            return None
        return RefinementEdit("delete", kind, entry_id, before=existing.to_dict(), after=None)

    def trim(self, limits: dict[str, int]) -> list[str]:
        changes: list[str] = []
        for kind in _KINDS:
            cap = int(limits.get(kind) or limits.get("memory") or 80)
            bucket = self.entries.get(kind) or {}
            if len(bucket) <= cap:
                continue
            ordered = sorted(bucket.values(), key=lambda e: e.updated_at or e.created_at)
            for entry in ordered[: len(bucket) - cap]:
                if self.delete(kind, entry.id):
                    changes.append(f"trim {kind}/{entry.id}")
        return changes

    def record_refinement(
        self,
        *,
        job: str,
        trigger: str,
        changes: list[str],
        evidence: str,
        edits: list[RefinementEdit],
    ) -> RefinementEvent:
        event_id = f"refine_{len(self.refinements) + 1:04d}"
        event = RefinementEvent(
            id=event_id,
            job=job,
            trigger=trigger,
            changes=changes,
            evidence=evidence[:500],
            edits=[e.to_dict() for e in edits if e.action != "noop"],
            created_at=_now_iso(),
        )
        self.refinements.append(event)
        refinements_path = _refinements_path()
        refinements_path.parent.mkdir(parents=True, exist_ok=True)
        with open(refinements_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event

    def overview(self, *, entry_limit: int = 6) -> str:
        lines = ["Harness overview:"]
        for kind in _KINDS:
            bucket = self.entries.get(kind) or {}
            lines.append(f"- {kind}: {len(bucket)}")
            for entry in sorted(bucket.values(), key=lambda e: e.updated_at, reverse=True)[:entry_limit]:
                lines.append(f"  · {entry.title}: {entry.content[:120]}")
        lines.append(f"- refinements: {len(self.refinements)}")
        return "\n".join(lines)


def load_harness() -> HarnessState:
    return HarnessState.load()


def save_harness(state: HarnessState) -> Path:
    return state.save()


def format_harness_for_briefing(*, limit: int = 5, kinds: Optional[list[HarnessKind]] = None) -> str:
    state = load_harness()
    use_kinds = kinds or list(_KINDS)
    lines: list[str] = []
    for kind in use_kinds:
        bucket = state.entries.get(kind) or {}
        if not bucket:
            continue
        label = {"memory": "记忆", "policy": "策略", "playbook": "清单"}.get(kind, kind)
        lines.append(f"**Harness {label}**")
        for entry in sorted(bucket.values(), key=lambda e: e.updated_at, reverse=True)[:limit]:
            lines.append(f"- {entry.content}")
        lines.append("")
    return "\n".join(lines).strip()


def list_refinements(*, limit: int = 20) -> list[dict[str, Any]]:
    state = load_harness()
    return [e.to_dict() for e in reversed(state.refinements[-limit:])]


def rollback_refinement(refinement_id: str) -> dict[str, Any]:
    state = load_harness()
    target = next((e for e in reversed(state.refinements) if e.id == refinement_id), None)
    if target is None:
        raise ValueError(f"未找到 refinement {refinement_id}")
    applied = 0
    for raw in reversed(target.edits):
        action = raw.get("action")
        kind = raw.get("kind")
        entry_id = raw.get("entry_id")
        if kind not in _KINDS or not entry_id:
            continue
        if action == "create":
            state.delete(kind, str(entry_id))
            applied += 1
        elif action == "update" and raw.get("before"):
            before = raw["before"]
            state.upsert(
                kind,
                str(entry_id),
                title=str(before.get("title") or entry_id),
                content=str(before.get("content") or ""),
                source=str(before.get("source") or ""),
                job=str(before.get("job") or ""),
                evidence=str(before.get("evidence") or ""),
            )
            applied += 1
        elif action == "delete" and raw.get("before"):
            before = raw["before"]
            state.upsert(
                kind,
                str(entry_id),
                title=str(before.get("title") or entry_id),
                content=str(before.get("content") or ""),
                source=str(before.get("source") or ""),
                job=str(before.get("job") or ""),
                evidence=str(before.get("evidence") or ""),
            )
            applied += 1
    rollback_event = state.record_refinement(
        job=target.job,
        trigger=f"rollback:{refinement_id}",
        changes=[f"rollback {refinement_id} ({applied} edits)"],
        evidence=target.evidence,
        edits=[],
    )
    state.save()
    return {"rolled_back": refinement_id, "edits_reversed": applied, "rollback_event": rollback_event.id}


def _harness_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    if settings is None:
        try:
            from agent_reach.daily_run.settings import load_settings

            settings = load_settings()
        except Exception:
            settings = {}
    return dict((settings or {}).get("harness") or {})


def _job_enabled(cfg: dict[str, Any], job: str) -> bool:
    jobs = cfg.get("jobs") or {}
    if isinstance(jobs, dict) and job in jobs:
        return bool(jobs[job])
    return True


def _limits(cfg: dict[str, Any]) -> dict[str, int]:
    return {
        "memory": int(cfg.get("max_memory") or 80),
        "policy": int(cfg.get("max_policy") or 30),
        "playbook": int(cfg.get("max_playbook") or 20),
    }


def _upsert_texts(
    state: HarnessState,
    kind: HarnessKind,
    texts: list[str],
    *,
    job: str,
    source: str,
    evidence: str,
) -> tuple[list[str], list[RefinementEdit]]:
    changes: list[str] = []
    edits: list[RefinementEdit] = []
    seen: set[str] = set()
    for text in texts:
        line = str(text or "").strip()
        if not line or line in seen:
            continue
        seen.add(line)
        entry_id = _slug(line[:60]) or hashlib.sha1(line.encode()).hexdigest()[:12]
        _, edit = state.upsert(
            kind,
            entry_id,
            title=line[:48],
            content=line,
            source=source,
            job=job,
            evidence=evidence,
        )
        if edit.action != "noop":
            edits.append(edit)
            changes.append(f"{kind}/{entry_id}: {line[:80]}")
    return changes, edits


def _evidence_from_close(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str], str]:
    memory: list[str] = list(evidence.get("rules") or [])
    if not memory and evidence.get("verify"):
        from agent_reach.daily_run.experience import _distill_rules

        memory = _distill_rules(
            evidence.get("snapshot") or {},
            evidence.get("verify") or {},
            evidence.get("curve"),
            forecast_review=evidence.get("forecast_review"),
        )
    policy: list[str] = []
    playbook: list[str] = []

    verify = evidence.get("verify") or {}
    name = evidence.get("name") or verify.get("code") or ""
    if verify.get("summary"):
        memory.append(str(verify["summary"]))

    pf = evidence.get("portfolio_summary") or {}
    pnl = pf.get("daily_pnl")
    pct = pf.get("daily_pnl_pct")
    if pnl is not None:
        sign = "+" if float(pnl) >= 0 else ""
        pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
        memory.append(f"{name} 收盘组合盈亏 {sign}¥{float(pnl):,.0f}{pct_s}".strip())

    for rec in (verify.get("recommendations") or [])[:2]:
        playbook.append(f"明日：{rec}")

    summary = f"close {name or verify.get('code', '')}".strip()
    return memory, policy, playbook, summary


def _evidence_from_weekly(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str], str]:
    report = evidence.get("report") or evidence
    memory: list[str] = []
    playbook: list[str] = []
    policy: list[str] = []

    pnl = report.get("weekly_pnl")
    pct = report.get("weekly_pnl_pct")
    if pnl is not None:
        sign = "+" if float(pnl) >= 0 else ""
        pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
        memory.append(f"本周组合净值 {sign}¥{float(pnl):,.0f}{pct_s}")

    for item in report.get("process_improvements") or []:
        title = item.get("title") or "改进"
        detail = item.get("detail") or ""
        action = item.get("action") or ""
        playbook.append(f"{title} — {detail}" + (f"；执行：{action}" if action else ""))

    for item in report.get("skill_learning") or []:
        title = item.get("title") or "技能"
        summary = item.get("summary") or ""
        memory.append(f"{title}：{summary}")

    for snippet in report.get("experience_snippets") or []:
        memory.append(str(snippet)[:200])

    for note in evidence.get("applied_config") or report.get("applied_config") or []:
        policy.append(f"已应用参数：{note}")

    ws = report.get("week_start") or ""
    we = report.get("week_end") or ""
    return memory, policy, playbook, f"weekly {ws}~{we}".strip()


def _evidence_from_forecast(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str], str]:
    forecast = evidence.get("forecast") or evidence
    memory: list[str] = []
    playbook: list[str] = []
    policy: list[str] = []

    ws = forecast.get("week_start") or ""
    we = forecast.get("week_end") or ""
    memory.append(f"下周预测窗口 {ws}~{we}")

    for note in forecast.get("notes") or []:
        memory.append(str(note)[:200])

    symbols = forecast.get("symbols") or {}
    bullish: list[str] = []
    bearish: list[str] = []
    for code, row in symbols.items():
        kronos = (row.get("kronos") or {}) if isinstance(row, dict) else {}
        if not kronos.get("available"):
            continue
        cum = kronos.get("cum_change_pct")
        name = row.get("name") or code
        if cum is None:
            continue
        if float(cum) >= 1.0:
            bullish.append(f"{name}({code}) {float(cum):+.1f}%")
        elif float(cum) <= -1.0:
            bearish.append(f"{name}({code}) {float(cum):+.1f}%")
    if bullish:
        playbook.append("Kronos 偏强：" + "、".join(bullish[:4]))
    if bearish:
        playbook.append("Kronos 偏弱：" + "、".join(bearish[:4]))

    mss = forecast.get("mss_daily") or {}
    if mss.get("summary"):
        memory.append(str(mss["summary"])[:200])

    return memory, policy, playbook, f"forecast {ws}~{we}".strip()


def refine_after_job(
    job: str,
    *,
    evidence: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Deterministic harness refine at job boundary (Layer A)."""
    cfg = _harness_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "harness disabled"}
    if not _job_enabled(cfg, job):
        return {"skipped": True, "reason": f"job {job} disabled in harness.jobs"}

    if job == "close":
        memory, policy, playbook, ev_summary = _evidence_from_close(evidence)
    elif job == "weekly":
        memory, policy, playbook, ev_summary = _evidence_from_weekly(evidence)
    elif job == "forecast":
        memory, policy, playbook, ev_summary = _evidence_from_forecast(evidence)
    else:
        memory = [str(x) for x in (evidence.get("memory") or []) if str(x).strip()]
        policy = [str(x) for x in (evidence.get("policy") or []) if str(x).strip()]
        playbook = [str(x) for x in (evidence.get("playbook") or []) if str(x).strip()]
        ev_summary = str(evidence.get("summary") or job)

    state = load_harness()
    all_edits: list[RefinementEdit] = []
    all_changes: list[str] = []

    for kind, texts in (
        ("memory", memory),
        ("policy", policy),
        ("playbook", playbook),
    ):
        changes, edits = _upsert_texts(
            state,
            kind,
            texts,
            job=job,
            source="deterministic",
            evidence=ev_summary,
        )
        all_changes.extend(changes)
        all_edits.extend(edits)

    trim_changes = state.trim(_limits(cfg))
    all_changes.extend(trim_changes)

    event = state.record_refinement(
        job=job,
        trigger=f"job:{job}",
        changes=all_changes,
        evidence=ev_summary,
        edits=all_edits,
    )
    path = state.save()
    return {
        "skipped": False,
        "job": job,
        "refinement_id": event.id,
        "changes": len(all_changes),
        "state_path": str(path),
    }
