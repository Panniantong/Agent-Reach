# -*- coding: utf-8
"""Continual harness for daily-run self-learning (prime-agent inspired, job-boundary refine)."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

HarnessKind = Literal["memory", "policy", "playbook", "plan"]

_KINDS: tuple[HarnessKind, ...] = ("memory", "policy", "playbook", "plan")
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


PlanStatus = Literal["open", "done"]


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
    status: str = ""

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
                        status = str(raw.get("status") or "")
                        if kind == "plan" and not status:
                            status = "open"
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
                            status=status,
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

    def clone(self) -> HarnessState:
        return deepcopy(self)

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
        status: str = "",
    ) -> tuple[HarnessEntry, RefinementEdit]:
        bucket = self.entries.setdefault(kind, {})
        existing = bucket.get(entry_id)
        now = _now_iso()
        entry_status = status or (existing.status if existing else "")
        if kind == "plan" and not entry_status:
            entry_status = "open"
        if existing:
            before = existing.to_dict()
            if (
                existing.content == content
                and existing.title == title
                and (existing.status or "") == entry_status
            ):
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
                status=entry_status,
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
                status=entry_status,
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
        label = {"memory": "记忆", "policy": "策略", "playbook": "清单", "plan": "计划"}.get(kind, kind)
        lines.append(f"**Harness {label}**")
        entries = sorted(bucket.values(), key=lambda e: e.updated_at, reverse=True)
        if kind == "plan":
            entries = [e for e in entries if (e.status or "open") != "done"]
        for entry in entries[:limit]:
            suffix = f" [{entry.status}]" if kind == "plan" and entry.status else ""
            lines.append(f"- {entry.content}{suffix}")
        lines.append("")
    return "\n".join(lines).strip()


def _xml_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_harness_content(
    *,
    limit: int = 5,
    kinds: Optional[list[HarnessKind]] = None,
    include_done_plans: bool = False,
) -> str:
    """Render harness entries as compact XML (DSH-style agent briefing)."""
    state = load_harness()
    use_kinds = kinds or list(_KINDS)
    lines: list[str] = ["<harness>"]
    has_entries = False
    for kind in use_kinds:
        bucket = state.entries.get(kind) or {}
        if not bucket:
            continue
        entries = sorted(bucket.values(), key=lambda e: e.updated_at, reverse=True)
        if kind == "plan" and not include_done_plans:
            entries = [e for e in entries if (e.status or "open") != "done"]
        for entry in entries[:limit]:
            has_entries = True
            attrs: list[str] = [f'id="{_xml_escape(entry.id)}"']
            if kind == "plan":
                attrs.append(f'status="{_xml_escape(entry.status or "open")}"')
            if entry.job:
                attrs.append(f'job="{_xml_escape(entry.job)}"')
            attr_s = " " + " ".join(attrs)
            lines.append(f"  <{kind}{attr_s}>{_xml_escape(entry.content)}</{kind}>")
    lines.append("</harness>")
    if not has_entries:
        return ""
    return "\n".join(lines)


def close_open_plans(*, settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Mark all open harness plan entries done (typically Monday morning)."""
    cfg = _harness_cfg(settings)
    if cfg.get("close_plans_on_morning") is False:
        return {"skipped": True, "reason": "close_plans_on_morning disabled"}
    state = load_harness()
    closed: list[str] = []
    now = _now_iso()
    bucket = state.entries.get("plan") or {}
    for entry_id, entry in list(bucket.items()):
        if (entry.status or "open") != "open":
            continue
        entry.status = "done"
        entry.updated_at = now
        closed.append(entry_id)
    if closed:
        state.record_refinement(
            job="morning",
            trigger="plan_closeout",
            changes=[f"done plan/{eid}" for eid in closed],
            evidence=f"closed {len(closed)} open plans",
            edits=[],
        )
        state.save()
    return {"skipped": False, "closed": closed, "count": len(closed)}


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
        "plan": int(cfg.get("max_plan") or 10),
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


def _evidence_from_close(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str], list[str], str]:
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
    plan: list[str] = []

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
        plan.append(f"假设：{rec}（待明日 verify）")

    summary = f"close {name or verify.get('code', '')}".strip()
    return memory, policy, playbook, plan, summary


def _evidence_from_weekly(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str], list[str], str]:
    report = evidence.get("report") or evidence
    memory: list[str] = []
    playbook: list[str] = []
    policy: list[str] = []
    plan: list[str] = []

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
        if str(item.get("priority") or "") in ("high", "medium"):
            plan.append(f"下周：{title}" + (f" → {action}" if action else ""))

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
    return memory, policy, playbook, plan, f"weekly {ws}~{we}".strip()


def _evidence_from_forecast(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str], list[str], str]:
    forecast = evidence.get("forecast") or evidence
    memory: list[str] = []
    playbook: list[str] = []
    policy: list[str] = []
    plan: list[str] = []

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
        line = "Kronos 偏强：" + "、".join(bullish[:4])
        playbook.append(line)
        plan.append(f"偏多验证：{line}")
    if bearish:
        line = "Kronos 偏弱：" + "、".join(bearish[:4])
        playbook.append(line)
        plan.append(f"偏空验证：{line}")

    mss = forecast.get("mss_daily") or {}
    if mss.get("summary"):
        memory.append(str(mss["summary"])[:200])

    return memory, policy, playbook, plan, f"forecast {ws}~{we}".strip()


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
        memory, policy, playbook, plan, ev_summary = _evidence_from_close(evidence)
    elif job == "weekly":
        memory, policy, playbook, plan, ev_summary = _evidence_from_weekly(evidence)
    elif job == "forecast":
        memory, policy, playbook, plan, ev_summary = _evidence_from_forecast(evidence)
    else:
        memory = [str(x) for x in (evidence.get("memory") or []) if str(x).strip()]
        policy = [str(x) for x in (evidence.get("policy") or []) if str(x).strip()]
        playbook = [str(x) for x in (evidence.get("playbook") or []) if str(x).strip()]
        plan = [str(x) for x in (evidence.get("plan") or []) if str(x).strip()]
        ev_summary = str(evidence.get("summary") or job)

    state = load_harness()
    all_edits: list[RefinementEdit] = []
    all_changes: list[str] = []

    for kind, texts in (
        ("memory", memory),
        ("policy", policy),
        ("playbook", playbook),
        ("plan", plan),
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


def _llm_refine_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    cfg = _harness_cfg(settings)
    return dict(cfg.get("llm_refine") or {})


def _llm_job_enabled(llm_cfg: dict[str, Any], job: str) -> bool:
    jobs = llm_cfg.get("jobs") or {}
    if isinstance(jobs, dict) and job in jobs:
        return bool(jobs[job])
    return job in {"close", "weekly", "forecast"}


def _parse_iso(ts: str) -> Optional[datetime]:
    raw = str(ts or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _within_llm_cooldown(state: HarnessState, llm_cfg: dict[str, Any]) -> bool:
    hours = float(llm_cfg.get("cooldown_hours") or 24)
    if hours <= 0:
        return False
    cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
    for event in reversed(state.refinements):
        if not str(event.trigger or "").startswith("llm:"):
            continue
        created = _parse_iso(event.created_at)
        if created and created.timestamp() >= cutoff:
            return True
    return False


def _collect_refine_signals(job: str, evidence: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    if job == "close":
        pf = evidence.get("portfolio_summary") or {}
        pct = pf.get("daily_pnl_pct")
        if pct is not None and abs(float(pct)) >= 0.5:
            signals.append(f"收盘组合波动 {float(pct):+.2f}%")
        verify = evidence.get("verify") or {}
        if verify.get("recommendations"):
            signals.append("verify 含明日建议")
        if verify.get("deviations"):
            signals.append("verify 出现偏差项")
        rules = evidence.get("rules") or []
        if rules:
            signals.append(f"规则 {len(rules)} 条待沉淀")
    elif job == "weekly":
        report = evidence.get("report") or evidence
        pct = report.get("weekly_pnl_pct")
        if pct is not None and abs(float(pct)) >= 0.3:
            signals.append(f"本周净值波动 {float(pct):+.2f}%")
        improvements = report.get("process_improvements") or []
        if improvements:
            signals.append(f"流程改进 {len(improvements)} 项")
        if report.get("skill_learning"):
            signals.append("周六技能学习非空")
    elif job == "forecast":
        forecast = evidence.get("forecast") or evidence
        symbols = forecast.get("symbols") or {}
        kronos_hits = 0
        for row in symbols.values():
            kronos = (row.get("kronos") or {}) if isinstance(row, dict) else {}
            if kronos.get("available") and kronos.get("cum_change_pct") is not None:
                kronos_hits += 1
        if kronos_hits:
            signals.append(f"Kronos 覆盖 {kronos_hits} 只")
        if forecast.get("notes"):
            signals.append("预测备注待提炼")
    return signals


def review_harness_refine(
    job: str,
    evidence: dict[str, Any],
    state: HarnessState,
    *,
    settings: Optional[dict[str, Any]] = None,
    skip_review: bool = False,
) -> dict[str, Any]:
    """Review gate before Layer B refine (deterministic; optional LLM assist)."""
    llm_cfg = _llm_refine_cfg(settings)
    if skip_review:
        return {"should_refine": True, "rationale": "manual refine", "instructions": ""}

    if _within_llm_cooldown(state, llm_cfg):
        return {"should_refine": False, "rationale": "llm refine cooldown active"}

    signals = _collect_refine_signals(job, evidence)
    if not signals:
        return {"should_refine": False, "rationale": "no actionable signals"}

    instructions = "优先合并重复 memory、将流程改进写入 playbook、policy 仅保留可执行参数。"
    if llm_cfg.get("use_llm_review"):
        from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

        if resolve_chat_provider(str(llm_cfg.get("provider") or "auto")):
            payload = chat_json(
                system=(
                    "你是 daily-run harness 审查员。仅输出 JSON："
                    '{"should_refine": bool, "rationale": "...", "instructions": "..."}。'
                    "仅在出现可沉淀的模式/流程改进/预测校准时 should_refine=true。"
                ),
                user=json.dumps(
                    {
                        "job": job,
                        "signals": signals,
                        "harness_overview": state.overview(entry_limit=4),
                        "recent_refinements": [e.to_dict() for e in state.refinements[-5:]],
                    },
                    ensure_ascii=False,
                ),
                provider=str(llm_cfg.get("provider") or "auto"),
                model=llm_cfg.get("model") or None,
                timeout=int(llm_cfg.get("timeout_seconds") or 45),
            )
            if isinstance(payload, dict) and "should_refine" in payload:
                return {
                    "should_refine": bool(payload.get("should_refine")),
                    "rationale": str(payload.get("rationale") or ""),
                    "instructions": str(payload.get("instructions") or instructions),
                }

    return {
        "should_refine": True,
        "rationale": "；".join(signals[:4]),
        "instructions": instructions,
    }


def _plan_from_signals(
    job: str,
    evidence: dict[str, Any],
    state: HarnessState,
    *,
    instructions: str = "",
) -> dict[str, Any]:
    """Deterministic Layer B planner when LLM is unavailable."""
    edits: list[dict[str, Any]] = []
    if job == "weekly":
        report = evidence.get("report") or evidence
        for idx, item in enumerate(report.get("process_improvements") or []):
            title = str(item.get("title") or "改进").strip()
            detail = str(item.get("detail") or "").strip()
            action = str(item.get("action") or "").strip()
            content = f"[P{idx + 1}] {title} — {detail}" + (f"；执行：{action}" if action else "")
            edits.append(
                {
                    "action": "create",
                    "kind": "playbook",
                    "entry_id": _slug(f"weekly_{title}") or f"weekly_{idx}",
                    "title": title[:48],
                    "content": content[:240],
                }
            )
        for note in evidence.get("applied_config") or report.get("applied_config") or []:
            line = f"已应用参数：{note}"
            edits.append(
                {
                    "action": "create",
                    "kind": "policy",
                    "entry_id": _slug(line[:60]),
                    "title": line[:48],
                    "content": line[:240],
                }
            )
    elif job == "forecast":
        forecast = evidence.get("forecast") or evidence
        symbols = forecast.get("symbols") or {}
        strong: list[str] = []
        weak: list[str] = []
        for code, row in symbols.items():
            kronos = (row.get("kronos") or {}) if isinstance(row, dict) else {}
            if not kronos.get("available"):
                continue
            cum = kronos.get("cum_change_pct")
            if cum is None:
                continue
            name = row.get("name") or code
            tag = f"{name}({code}) {float(cum):+.1f}%"
            if float(cum) >= 1.0:
                strong.append(tag)
            elif float(cum) <= -1.0:
                weak.append(tag)
        if strong:
            edits.append(
                {
                    "action": "create",
                    "kind": "playbook",
                    "entry_id": "forecast_kronos_bull",
                    "title": "Kronos 偏强",
                    "content": "Kronos 偏强：" + "、".join(strong[:4]),
                }
            )
        if weak:
            edits.append(
                {
                    "action": "create",
                    "kind": "playbook",
                    "entry_id": "forecast_kronos_bear",
                    "title": "Kronos 偏弱",
                    "content": "Kronos 偏弱：" + "、".join(weak[:4]),
                }
            )
    elif job == "close":
        verify = evidence.get("verify") or {}
        for idx, rec in enumerate((verify.get("recommendations") or [])[:3]):
            content = f"明日：{rec}"
            edits.append(
                {
                    "action": "create",
                    "kind": "playbook",
                    "entry_id": _slug(content[:60]) or f"close_play_{idx}",
                    "title": content[:48],
                    "content": content[:240],
                }
            )

    # Dedupe near-duplicate memory entries (keep shorter)
    memory_entries = list((state.entries.get("memory") or {}).values())
    memory_entries.sort(key=lambda e: e.updated_at or e.created_at, reverse=True)
    seen_prefix: set[str] = set()
    for entry in memory_entries:
        prefix = entry.content[:24]
        if prefix in seen_prefix:
            edits.append({"action": "delete", "kind": "memory", "entry_id": entry.id})
        else:
            seen_prefix.add(prefix)

    summary = f"deterministic {job}"
    if instructions:
        summary += f" ({instructions[:60]})"
    return {"summary": summary, "rationale": "rule-based planner", "edits": edits}


def plan_harness_refinement(
    job: str,
    evidence: dict[str, Any],
    state: HarnessState,
    *,
    settings: Optional[dict[str, Any]] = None,
    instructions: str = "",
) -> dict[str, Any]:
    """Layer B planner — LLM when configured, else deterministic fallback."""
    llm_cfg = _llm_refine_cfg(settings)
    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(llm_cfg.get("provider") or "auto")
    if resolve_chat_provider(provider):
        memory, policy, playbook, plan, ev_summary = _evidence_from_job(job, evidence)
        payload = chat_json(
            system=(
                "你是 daily-run harness 规划器。输出 JSON："
                '{"summary":"...", "rationale":"...", "edits":[{'
                '"action":"create|update|delete", "kind":"memory|policy|playbook|plan", '
                '"entry_id":"optional", "title":"...", "content":"..."}]}。'
                "每次最多 8 条 edits；content 必须中文且可执行；避免与 Layer A 完全重复。"
            ),
            user=json.dumps(
                {
                    "job": job,
                    "instructions": instructions,
                    "evidence_summary": ev_summary,
                    "layer_a": {"memory": memory, "policy": policy, "playbook": playbook, "plan": plan},
                    "harness_overview": state.overview(entry_limit=8),
                    "recent_refinements": [e.to_dict() for e in state.refinements[-8:]],
                },
                ensure_ascii=False,
            ),
            provider=provider,
            model=llm_cfg.get("model") or None,
            timeout=int(llm_cfg.get("timeout_seconds") or 60),
        )
        if isinstance(payload, dict) and isinstance(payload.get("edits"), list):
            payload["planner"] = "llm"
            return payload

    plan = _plan_from_signals(job, evidence, state, instructions=instructions)
    plan["planner"] = "deterministic"
    return plan


def _evidence_from_job(job: str, evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str], list[str], str]:
    if job == "close":
        return _evidence_from_close(evidence)
    if job == "weekly":
        return _evidence_from_weekly(evidence)
    if job == "forecast":
        return _evidence_from_forecast(evidence)
    memory = [str(x) for x in (evidence.get("memory") or []) if str(x).strip()]
    policy = [str(x) for x in (evidence.get("policy") or []) if str(x).strip()]
    playbook = [str(x) for x in (evidence.get("playbook") or []) if str(x).strip()]
    plan = [str(x) for x in (evidence.get("plan") or []) if str(x).strip()]
    return memory, policy, playbook, plan, str(evidence.get("summary") or job)


def apply_harness_proposal(
    state: HarnessState,
    proposal: dict[str, Any],
    *,
    job: str,
    baseline_state: HarnessState,
    evidence: str,
) -> tuple[list[RefinementEdit], list[str]]:
    """Apply planner edits with baseline conflict detection."""
    edits_out: list[RefinementEdit] = []
    changes: list[str] = []
    raw_edits = proposal.get("edits") or []
    if not isinstance(raw_edits, list):
        return edits_out, changes

    for raw in raw_edits[:12]:
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action") or "").strip().lower()
        kind = raw.get("kind")
        if kind not in _KINDS:
            continue
        entry_id = str(raw.get("entry_id") or _slug(str(raw.get("content") or raw.get("title") or "")) or "")
        if not entry_id and action != "delete":
            continue

        baseline_entry = baseline_state.get(kind, entry_id)
        current_entry = state.get(kind, entry_id)
        if action in {"update", "delete"} and baseline_entry and current_entry:
            if (current_entry.version or 1) != (baseline_entry.version or 1):
                if current_entry.updated_at != baseline_entry.updated_at:
                    continue

        if action == "delete":
            edit = state.delete(kind, entry_id)
            if edit:
                edits_out.append(edit)
                changes.append(f"delete {kind}/{entry_id}")
            continue

        title = str(raw.get("title") or entry_id)[:48]
        content = str(raw.get("content") or "").strip()
        if not content:
            continue
        _, edit = state.upsert(
            kind,
            entry_id,
            title=title,
            content=content[:400],
            source="llm_refine",
            job=job,
            evidence=evidence,
        )
        if edit.action != "noop":
            edits_out.append(edit)
            changes.append(f"{edit.action} {kind}/{entry_id}: {content[:80]}")

    return edits_out, changes


def refine_after_job_llm(
    job: str,
    *,
    evidence: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
    skip_review: bool = False,
) -> dict[str, Any]:
    """Layer B: review gate → plan → apply (prime-agent style)."""
    cfg = _harness_cfg(settings)
    llm_cfg = _llm_refine_cfg(settings)
    if cfg.get("enabled") is False or llm_cfg.get("enabled") is False:
        return {"skipped": True, "reason": "llm_refine disabled"}
    if not _llm_job_enabled(llm_cfg, job):
        return {"skipped": True, "reason": f"llm job {job} disabled"}

    state = load_harness()
    review = review_harness_refine(job, evidence, state, settings=settings, skip_review=skip_review)
    if not review.get("should_refine"):
        return {"skipped": True, "reason": review.get("rationale") or "review rejected", "review": review}

    baseline = state.clone()
    proposal = plan_harness_refinement(
        job,
        evidence,
        baseline,
        settings=settings,
        instructions=str(review.get("instructions") or ""),
    )
    _, _, _, _, ev_summary = _evidence_from_job(job, evidence)
    edits, changes = apply_harness_proposal(
        state,
        proposal,
        job=job,
        baseline_state=baseline,
        evidence=ev_summary,
    )
    if not changes:
        return {"skipped": True, "reason": "empty proposal", "review": review, "proposal": proposal}

    trim_changes = state.trim(_limits(cfg))
    changes.extend(trim_changes)
    event = state.record_refinement(
        job=job,
        trigger=f"llm:{job}",
        changes=changes,
        evidence=str(proposal.get("summary") or ev_summary),
        edits=edits,
    )
    path = state.save()
    return {
        "skipped": False,
        "job": job,
        "refinement_id": event.id,
        "changes": len(changes),
        "review": review,
        "proposal_summary": proposal.get("summary"),
        "planner": proposal.get("planner") or "deterministic",
        "state_path": str(path),
    }
