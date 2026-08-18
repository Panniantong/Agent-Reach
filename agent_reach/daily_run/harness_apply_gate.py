# -*- coding: utf-8
"""Verify-before-apply gate, bounded injection, and audit trail for harness refine."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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
        "block_playbook_on_morning_gate_fail": raw.get(
            "block_playbook_on_morning_gate_fail", True
        )
        is not False,
    }


def admission_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = _harness_cfg(settings)
    raw = dict(cfg.get("layer_b_admission") or {})
    return {
        "enabled": raw.get("enabled", True) is not False,
        "max_edits": max(1, int(raw.get("max_edits") or 8)),
        "max_score_drift": float(raw.get("max_score_drift") or 15),
        "max_ratio_drift": float(raw.get("max_ratio_drift") or 0.25),
        "block_threshold_literals": raw.get("block_threshold_literals", True) is not False,
    }


def injection_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = _harness_cfg(settings)
    raw = dict(cfg.get("injection") or {})
    return {
        "max_per_kind_per_job": int(raw.get("max_per_kind_per_job") or 8),
        "max_chars_per_line": int(raw.get("max_chars_per_line") or 240),
        "max_overlay_claims": int(raw.get("max_overlay_claims") or 3),
        "max_overlay_chars": int(raw.get("max_overlay_chars") or 1200),
        "enforce_claim_decisions": raw.get("enforce_claim_decisions", True) is not False,
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

    if evidence.get("morning_gate_passed") is False and cfg["block_playbook_on_morning_gate_fail"]:
        blocked.add("playbook")
        reasons.append("morning_gate_blocks_playbook")

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


_VERIFY_MARKERS = ("待验证", "假设", "TODO", "FIXME", "未证实")


def classify_overlay_claims(
    blobs: list[str],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Per-claim adopt / verify / ignore decisions (memory-gate CBDC style)."""
    limits = injection_cfg(settings)
    max_claims = max(1, limits["max_overlay_claims"])
    max_chars = max(200, limits["max_overlay_chars"])
    claims: list[dict[str, Any]] = []
    kept_count = 0
    kept_chars = 0
    for blob in blobs:
        text = str(blob or "").strip()
        if not text:
            continue
        preview = text[:80]
        if kept_count >= max_claims:
            claims.append({"text": preview, "decision": "ignored", "reason": "over_claim_cap"})
            continue
        if kept_chars + len(text) > max_chars and kept_count > 0:
            claims.append({"text": preview, "decision": "ignored", "reason": "over_char_cap"})
            continue
        if any(marker in text for marker in _VERIFY_MARKERS):
            decision = "verify"
            reason = "needs_verification_marker"
        else:
            decision = "adopted"
            reason = "within_injection_budget"
        claims.append({"text": preview, "decision": decision, "reason": reason})
        kept_count += 1
        kept_chars += len(text)
    return claims


def enforce_overlay_claims(
    blobs: list[str],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[list[str], dict[str, Any]]:
    """Return only adopted overlay blobs for runtime effective settings."""
    limits = injection_cfg(settings)
    if not limits.get("enforce_claim_decisions"):
        kept, meta = bound_overlay_blobs(blobs, settings=settings)
        meta["enforce_claim_decisions"] = False
        return kept, meta

    max_claims = max(1, limits["max_overlay_claims"])
    max_chars = max(200, limits["max_overlay_chars"])
    adopted: list[str] = []
    verify_count = 0
    ignored_count = 0
    kept_chars = 0
    for blob in blobs:
        text = str(blob or "").strip()
        if not text:
            continue
        slot_used = len(adopted) + verify_count
        if slot_used >= max_claims:
            ignored_count += 1
            continue
        if kept_chars + len(text) > max_chars and slot_used > 0:
            ignored_count += 1
            continue
        if any(marker in text for marker in _VERIFY_MARKERS):
            verify_count += 1
            kept_chars += len(text)
            continue
        adopted.append(text)
        kept_chars += len(text)
    return adopted, {
        "input_count": len(blobs),
        "kept_count": len(adopted),
        "adopted_count": len(adopted),
        "verify_count": verify_count,
        "ignored_count": ignored_count,
        "total_chars": kept_chars,
        "enforce_claim_decisions": True,
    }


_THRESHOLD_LITERAL_RE = re.compile(
    r"(macro_veto|aggressive_entry|min_cash_ratio|max_price_deviation_pct|"
    r"high_position_20d|min_volume_ratio|max_vwap_deviation_pct|"
    r"trade_min_scans|max_holdings|stop_loss_ma20_pct|friction_min_return_pct|"
    r"base_spread|vol_multiplier)\s*(?:=|→|->|:)\s*([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)

_SCORE_KEYS = frozenset({"macro_veto", "aggressive_entry", "base_spread", "vol_multiplier", "trade_min_scans", "max_holdings"})
_RATIO_KEYS = frozenset(
    {
        "min_cash_ratio",
        "max_price_deviation_pct",
        "high_position_20d",
        "min_volume_ratio",
        "max_vwap_deviation_pct",
        "stop_loss_ma20_pct",
        "friction_min_return_pct",
    }
)

_NEUTRAL_DEFAULTS: dict[str, float] = {
    "macro_veto": 40.0,
    "aggressive_entry": 50.0,
    "min_cash_ratio": 0.0,
    "max_price_deviation_pct": 0.08,
    "high_position_20d": 0.7,
    "min_volume_ratio": 1.0,
    "max_vwap_deviation_pct": 0.04,
    "trade_min_scans": 3.0,
    "max_holdings": 10.0,
    "stop_loss_ma20_pct": 0.04,
    "friction_min_return_pct": 0.005,
    "base_spread": 8.0,
    "vol_multiplier": 6.0,
}


@dataclass
class LayerBAdmissionResult:
    passed: bool = True
    accepted_edits: list[dict[str, Any]] = field(default_factory=list)
    rejected_edits: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _threshold_literal_ok(key: str, value: float, cfg: dict[str, Any]) -> Optional[str]:
    base = float(_NEUTRAL_DEFAULTS.get(key, 0.0))
    if key in _SCORE_KEYS:
        if value < 10 or value > 100:
            return f"{key} out of range"
        if abs(value - base) > float(cfg["max_score_drift"]):
            return f"{key} drift {value} vs neutral {base}"
    elif key in _RATIO_KEYS:
        if value < 0 or value > 1.5:
            return f"{key} ratio out of range"
        if abs(value - base) > float(cfg["max_ratio_drift"]):
            return f"{key} drift {value} vs neutral {base}"
    else:
        if value < 0 or value > 100:
            return f"{key} value out of range"
    return None


def evaluate_layer_b_admission(
    proposal: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> LayerBAdmissionResult:
    """Harbor-style admission for Layer B edits before apply."""
    cfg = admission_cfg(settings)
    result = LayerBAdmissionResult()
    raw_edits = proposal.get("edits") or []
    if not isinstance(raw_edits, list):
        result.passed = False
        result.reasons.append("invalid_edits")
        return result
    if not cfg["enabled"]:
        result.accepted_edits = list(raw_edits)
        return result

    if len(raw_edits) > cfg["max_edits"]:
        result.reasons.append(f"too_many_edits:{len(raw_edits)}")

    for raw in raw_edits[: cfg["max_edits"] + 4]:
        if not isinstance(raw, dict):
            result.rejected_edits.append({"raw": raw, "reason": "not_a_dict"})
            continue
        kind = raw.get("kind")
        if kind not in _KINDS:
            result.rejected_edits.append({**raw, "reason": "invalid_kind"})
            continue
        content = str(raw.get("content") or "").strip()
        if not content:
            result.rejected_edits.append({**raw, "reason": "empty_content"})
            continue
        if len(content) > 400:
            result.rejected_edits.append({**raw, "reason": "content_too_long"})
            continue
        if cfg["block_threshold_literals"]:
            bad_literal = False
            for match in _THRESHOLD_LITERAL_RE.finditer(content):
                key = str(match.group(1)).lower()
                try:
                    val = float(match.group(2))
                except ValueError:
                    bad_literal = True
                    result.rejected_edits.append({**raw, "reason": f"bad_literal:{key}"})
                    break
                err = _threshold_literal_ok(key, val, cfg)
                if err:
                    bad_literal = True
                    result.rejected_edits.append({**raw, "reason": err})
                    break
            if bad_literal:
                continue
        if kind == "policy" and "→" in content and any(k in content for k in _NEUTRAL_DEFAULTS):
            result.rejected_edits.append({**raw, "reason": "policy_threshold_arrow_blocked"})
            continue
        result.accepted_edits.append(raw)

    result.passed = bool(result.accepted_edits)
    if result.rejected_edits:
        result.reasons.append(f"rejected={len(result.rejected_edits)}")
    return result


def filter_proposal_for_admission(
    proposal: dict[str, Any],
    admission: LayerBAdmissionResult,
) -> dict[str, Any]:
    out = dict(proposal)
    out["edits"] = list(admission.accepted_edits)
    out["admission"] = admission.to_dict()
    return out


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
    claims = classify_overlay_claims(raw_blobs, settings=settings)
    adopted = [c["text"] for c in claims if c.get("decision") == "adopted"]
    verify = [c["text"] for c in claims if c.get("decision") == "verify"]
    ignored = [c for c in claims if c.get("decision") == "ignored"]
    return {
        "input_count": len(raw_blobs),
        "kept_count": len(adopted) + len(verify),
        "ignored_count": len(ignored),
        "claims": claims,
        "adopted_preview": adopted[:3],
        "verify_preview": verify[:3],
        "sources": sorted(sources),
    }


def record_apply_audit(
    *,
    job: str,
    refinement_id: Optional[str] = None,
    gate: Optional[Any] = None,
    injection_meta: Optional[dict[str, Any]] = None,
    skipped_kinds: Optional[list[str]] = None,
    changes: int = 0,
    snapshot_path: Optional[str] = None,
    admission: Optional[dict[str, Any]] = None,
    status: str = "applied",
    reason: str = "",
    layer: str = "a",
    forge_gate: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    gate_dict: dict[str, Any] = {}
    if gate is not None:
        gate_dict = gate.to_dict() if hasattr(gate, "to_dict") else dict(gate)
    event = {
        "at": _now_iso(),
        "job": job,
        "status": status,
        "reason": reason,
        "layer": layer,
        "refinement_id": refinement_id,
        "gate": gate_dict,
        "injection": injection_meta or {},
        "skipped_kinds": list(skipped_kinds or []),
        "changes": changes,
        "snapshot_path": snapshot_path,
        "admission": admission,
        "forge_gate": forge_gate,
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
    admission = gate.get("admission") or {}
    if admission.get("rejected_edits"):
        lines.append(f"- Layer B Admission：拒绝 {len(admission['rejected_edits'])} 条 edits")
    if gate.get("snapshot_path"):
        lines.append(f"- 改前快照：`{Path(str(gate['snapshot_path'])).name}`")
    return "\n".join(lines)
