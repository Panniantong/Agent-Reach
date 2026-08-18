# -*- coding: utf-8
"""Verify-before-apply gate, bounded injection, and audit trail for harness refine."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

HarnessKind = Literal["memory", "policy", "playbook", "plan"]
_KINDS: tuple[HarnessKind, ...] = ("memory", "policy", "playbook", "plan")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_path() -> Path:
    from agent_reach.daily_run.harness import harness_dir

    return harness_dir() / "apply_audit.jsonl"


def _harness_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    if settings is None:
        try:
            from agent_reach.daily_run.settings import load_settings

            settings = load_settings()
        except Exception:
            settings = {}
    return dict((settings or {}).get("harness") or {})


def gate_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = _harness_cfg(settings)
    raw = dict(cfg.get("apply_gate") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "block_policy_on_audit_fail": raw.get("block_policy_on_audit_fail", True) is not False,
        "block_policy_on_structured_incomplete": raw.get(
            "block_policy_on_structured_incomplete", True
        )
        is not False,
    }


def injection_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = _harness_cfg(settings)
    raw = dict(cfg.get("injection") or {})
    return {
        "max_per_kind_per_job": int(raw.get("max_per_kind_per_job") or 8),
        "max_chars_per_line": int(raw.get("max_chars_per_line") or 240),
        "max_overlay_claims": int(raw.get("max_overlay_claims") or 3),
        "max_overlay_chars": int(raw.get("max_overlay_chars") or 1200),
    }


def _audit_passed(evidence: dict[str, Any]) -> Optional[bool]:
    for key in ("audit_passed", "passed", "gate_passed"):
        if key in evidence:
            return bool(evidence[key])
    audit = evidence.get("audit")
    if isinstance(audit, dict) and "passed" in audit:
        return bool(audit["passed"])
    if hasattr(audit, "passed"):
        return bool(getattr(audit, "passed"))
    return None


def _structured_complete(evidence: dict[str, Any]) -> Optional[bool]:
    if "structured_review_complete" in evidence:
        return bool(evidence["structured_review_complete"])
    audit = evidence.get("audit")
    if isinstance(audit, dict) and "structured_review_complete" in audit:
        return bool(audit["structured_review_complete"])
    if hasattr(audit, "structured_review_complete"):
        return bool(getattr(audit, "structured_review_complete"))
    return None


def collect_verification_signals(job: str, evidence: dict[str, Any]) -> list[str]:
    """Deterministic verification signals for audit cards (DSH session-audit style)."""
    signals: list[str] = list(evidence.get("verification_signals") or [])
    seen = set(signals)

    def _add(text: str) -> None:
        line = str(text or "").strip()
        if line and line not in seen:
            seen.add(line)
            signals.append(line)

    passed = _audit_passed(evidence)
    if passed is False:
        _add("audit_failed")
    elif passed is True:
        _add("audit_passed")

    structured = _structured_complete(evidence)
    if structured is False:
        _add("structured_review_incomplete")

    if job == "data_audit":
        issues = evidence.get("issues") or []
        warnings = evidence.get("warnings") or []
        if issues:
            _add(f"audit_issues={len(issues)}")
        if warnings:
            _add(f"audit_warnings={len(warnings)}")
    elif job == "verify":
        verify = evidence.get("verify") or evidence
        devs = verify.get("deviations") or []
        if devs:
            _add(f"verify_deviations={len(devs)}")
        if verify.get("recommendations"):
            _add("verify_recommendations")
    elif job == "morning":
        if evidence.get("morning_gate_passed") is False:
            _add("morning_gate_failed")
        if evidence.get("morning_audit_passed") is False:
            _add("morning_audit_failed")
    elif job == "close":
        pf = evidence.get("portfolio_summary") or {}
        pct = pf.get("daily_pnl_pct")
        if pct is not None and abs(float(pct)) >= 0.5:
            _add(f"daily_pnl_pct={float(pct):+.2f}")

    return signals


@dataclass
class ApplyGateResult:
    enabled: bool = True
    passed: bool = True
    blocked_kinds: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    verification_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_apply_gate(
    job: str,
    evidence: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> ApplyGateResult:
    """Rule-evolve style gate: block risky kinds until verification passes."""
    cfg = gate_cfg(settings)
    signals = collect_verification_signals(job, evidence)
    result = ApplyGateResult(
        enabled=cfg["enabled"],
        verification_signals=signals,
    )
    if not cfg["enabled"]:
        return result

    blocked: set[str] = set()
    reasons: list[str] = []

    passed = _audit_passed(evidence)
    if passed is False and cfg["block_policy_on_audit_fail"]:
        blocked.add("policy")
        reasons.append("audit_fail_blocks_policy")

    structured = _structured_complete(evidence)
    if structured is False and cfg["block_policy_on_structured_incomplete"]:
        blocked.add("policy")
        reasons.append("structured_incomplete_blocks_policy")

    result.blocked_kinds = sorted(blocked)
    result.reasons = reasons
    result.passed = not blocked
    return result


def apply_kind_gate(
    kind_texts: dict[str, list[str]],
    gate: ApplyGateResult,
) -> tuple[dict[str, list[str]], list[str]]:
    """Drop blocked kinds; return filtered map + skip notes."""
    if not gate.enabled or not gate.blocked_kinds:
        return kind_texts, []
    skipped: list[str] = []
    filtered = dict(kind_texts)
    for kind in gate.blocked_kinds:
        if filtered.get(kind):
            skipped.append(f"gate_blocked:{kind}:{len(filtered[kind])}")
            filtered[kind] = []
    return filtered, skipped


def bound_kind_texts(
    texts: list[str],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[list[str], dict[str, Any]]:
    """Cap lines per kind and per-line length (memory-gate bounded injection)."""
    limits = injection_cfg(settings)
    max_count = max(1, limits["max_per_kind_per_job"])
    max_chars = max(40, limits["max_chars_per_line"])
    kept: list[str] = []
    dropped = 0
    truncated = 0
    for line in texts:
        text = str(line or "").strip()
        if not text:
            continue
        if len(kept) >= max_count:
            dropped += 1
            continue
        if len(text) > max_chars:
            text = text[: max_chars - 1] + "…"
            truncated += 1
        kept.append(text)
    meta = {
        "input_count": len([x for x in texts if str(x or "").strip()]),
        "kept_count": len(kept),
        "dropped_count": dropped,
        "truncated_count": truncated,
        "max_per_kind": max_count,
        "max_chars": max_chars,
    }
    return kept, meta


def bound_overlay_blobs(blobs: list[str], *, settings: Optional[dict[str, Any]] = None) -> tuple[list[str], dict[str, Any]]:
    """Bound runtime overlay scan to max claims/chars."""
    limits = injection_cfg(settings)
    max_claims = max(1, limits["max_overlay_claims"])
    max_chars = max(200, limits["max_overlay_chars"])
    kept: list[str] = []
    total_chars = 0
    dropped = 0
    for blob in blobs:
        text = str(blob or "").strip()
        if not text:
            continue
        if len(kept) >= max_claims:
            dropped += 1
            continue
        if total_chars + len(text) > max_chars:
            room = max_chars - total_chars
            if room < 40:
                dropped += 1
                continue
            text = text[: room - 1] + "…"
        kept.append(text)
        total_chars += len(text)
    return kept, {
        "input_count": len(blobs),
        "kept_count": len(kept),
        "dropped_count": dropped,
        "total_chars": total_chars,
        "max_claims": max_claims,
        "max_chars": max_chars,
    }


def build_overlay_injection_audit(
    state: Any,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Summarize which harness blobs fed runtime overlay (adopt/ignore trail)."""
    from agent_reach.daily_run.harness_policy import _collect_text_blobs, _overlay_sources

    sources = _overlay_sources(settings or {})
    raw_blobs: list[str] = []
    for kind in ("memory", "policy", "playbook"):
        if kind in sources:
            raw_blobs.extend(_collect_text_blobs(state, sources=sources, kind=kind, bounded=False))
    bounded, meta = bound_overlay_blobs(raw_blobs, settings=settings)
    adopted = [b[:80] for b in bounded]
    ignored = max(0, meta["input_count"] - meta["kept_count"])
    return {
        **meta,
        "adopted_preview": adopted,
        "ignored_count": ignored,
        "sources": sorted(sources),
    }


def record_apply_audit(
    *,
    job: str,
    refinement_id: str,
    gate: ApplyGateResult,
    injection_meta: dict[str, Any],
    skipped_kinds: list[str],
    changes: int,
) -> dict[str, Any]:
    event = {
        "at": _now_iso(),
        "job": job,
        "refinement_id": refinement_id,
        "gate": gate.to_dict(),
        "injection": injection_meta,
        "skipped_kinds": skipped_kinds,
        "changes": changes,
    }
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def load_recent_apply_audit(*, limit: int = 10) -> list[dict[str, Any]]:
    path = _audit_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in reversed(lines[-limit:]):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def format_gate_markdown(gate: dict[str, Any]) -> str:
    """Compact gate section for Feishu harness cards."""
    if not gate:
        return ""
    blocked = gate.get("blocked_kinds") or []
    signals = gate.get("verification_signals") or []
    lines: list[str] = []
    if signals:
        lines.append(f"- 验证信号：{', '.join(str(s) for s in signals[:6])}")
    if blocked:
        reasons = gate.get("reasons") or []
        reason_s = f" ({', '.join(reasons)})" if reasons else ""
        lines.append(f"- 门控拦截：{', '.join(blocked)}{reason_s}")
    injection = gate.get("injection") or {}
    dropped = sum(
        int((injection.get(kind) or {}).get("dropped_count") or 0)
        for kind in _KINDS
    )
    if dropped:
        lines.append(f"- 有界注入：丢弃 {dropped} 条超长/超额 evidence")
    return "\n".join(lines)
