# -*- coding: utf-8
"""Experience writeback — atomize close review into rule library."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run.experience")


@dataclass
class ExperienceAppendResult:
    path: Path
    harness: dict[str, Any] = field(default_factory=dict)


def experience_dir() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "experience"


def append_experience_entry(
    snapshot: dict[str, Any],
    verify: dict[str, Any],
    *,
    curve: Optional[dict[str, Any]] = None,
    research: Optional[list[dict[str, Any]]] = None,
    settings: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
    xueqiu_hit_settle: Optional[dict[str, Any]] = None,
) -> ExperienceAppendResult:
    """Append one close review atom to experience.jsonl and update rules summary."""
    cfg = (settings or {}).get("experience", {})
    if cfg.get("enabled") is False:
        return ExperienceAppendResult(path=experience_dir() / "experience.jsonl")

    out_dir = experience_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "experience.jsonl"

    rules = _distill_rules(snapshot, verify, curve, forecast_review=forecast_review)

    harness_result: dict[str, Any] = {}
    try:
        from agent_reach.daily_run.experience_harness import (
            apply_experience_harness_refinement,
            experience_harness_enabled,
        )

        if experience_harness_enabled(settings):
            harness_result = apply_experience_harness_refinement(
                snapshot,
                verify,
                rules=rules,
                curve=curve,
                forecast_review=forecast_review,
                settings=settings,
            )
    except Exception as exc:
        logger.warning("daily-run experience harness failed: {}", exc)
        harness_result = {"skipped": True, "error": str(exc), "job": "experience"}

    entry = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "at": datetime.now(timezone.utc).isoformat(),
        "code": snapshot.get("code"),
        "name": snapshot.get("name"),
        "mss_final": snapshot.get("mss_final") or verify.get("mss_current"),
        "verdict": verify.get("verdict_current"),
        "mss_delta": verify.get("mss_delta"),
        "prediction_hit": verify.get("mss_within_prediction"),
        "deviations": verify.get("deviations") or [],
        "recommendations": verify.get("recommendations") or [],
        "curve_trend": (curve or {}).get("trend"),
        "research_count": len(research or []),
    }
    if forecast_review:
        entry["forecast_review"] = {
            "date": forecast_review.get("date"),
            "accuracy": forecast_review.get("accuracy"),
            "symbol_hits": forecast_review.get("symbol_hits"),
            "symbol_total": forecast_review.get("symbol_total"),
            "mss_hit": forecast_review.get("mss_hit"),
            "optimization_notes": forecast_review.get("optimization_notes") or [],
        }

    if xueqiu_hit_settle and not xueqiu_hit_settle.get("skipped"):
        entry["xueqiu_hit_settle"] = {
            "settled_count": xueqiu_hit_settle.get("settled_count"),
            "counts": xueqiu_hit_settle.get("counts"),
            "harness_refinement_id": (xueqiu_hit_settle.get("harness") or {}).get("refinement_id"),
        }

    if harness_result and not harness_result.get("skipped"):
        entry["harness_refinement_id"] = harness_result.get("refinement_id")

    consolidated = False
    try:
        from agent_reach.daily_run.experience_harness import experience_consolidated_mode

        consolidated = experience_consolidated_mode(settings)
    except Exception as exc:
        logger.debug("daily-run experience consolidated_mode check failed: {}", exc)
        consolidated = False

    if consolidated:
        entry["rules"] = []
        entry["rules_in_harness"] = True
    else:
        entry["rules"] = rules

    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if not consolidated:
        _update_rules_summary(out_dir / "rules_summary.json", rules, cfg)
    return ExperienceAppendResult(path=jsonl_path, harness=harness_result)


def _tail_jsonl_lines(path: Path, limit: int) -> list[str]:
    if not path.exists() or limit <= 0:
        return []
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size == 0:
        return []
    chunk = min(size, 65536)
    with open(path, "rb") as handle:
        handle.seek(max(0, size - chunk))
        data = handle.read().decode("utf-8", errors="replace")
    lines = data.splitlines()
    return lines[-limit:] if len(lines) > limit else lines


def load_recent_experience(limit: int = 10) -> list[dict[str, Any]]:
    path = experience_dir() / "experience.jsonl"
    if not path.exists():
        return []
    out = []
    for line in _tail_jsonl_lines(path, limit):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _experience_recency(entry: dict[str, Any]) -> tuple[str, str]:
    return (str(entry.get("date") or ""), str(entry.get("at") or ""))


def _date_in_experience_range(ds: str, start: date, end: date) -> bool:
    try:
        d = date.fromisoformat(ds[:10])
    except ValueError:
        return False
    return start <= d <= end


def load_experience_in_range(start: date, end: date) -> list[dict[str, Any]]:
    """All experience entries whose ``date`` falls in ``[start, end]`` (inclusive)."""
    path = experience_dir() / "experience.jsonl"
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ds = str(entry.get("date") or "")
            if _date_in_experience_range(ds, start, end):
                out.append(entry)
    return out


def format_experience_snippet(entry: dict[str, Any]) -> str:
    ds = str(entry.get("date") or "")
    hit = "✅" if entry.get("prediction_hit") else "—"
    rules = "；".join((entry.get("rules") or [])[:2])
    return f"{ds} {entry.get('name')} MSS={entry.get('mss_final')} {hit} {rules}".strip()


def load_weekly_experience_snippets(start: date, end: date, limit: int = 5) -> list[str]:
    """
    Weekly report snippets: latest entry per symbol in range, most recent symbols first.
    """
    latest_by_code: dict[str, dict[str, Any]] = {}
    for entry in load_experience_in_range(start, end):
        code = str(entry.get("code") or "").strip() or str(entry.get("name") or "unknown")
        prev = latest_by_code.get(code)
        if prev is None or _experience_recency(entry) > _experience_recency(prev):
            latest_by_code[code] = entry
    ranked = sorted(latest_by_code.values(), key=_experience_recency, reverse=True)
    return [format_experience_snippet(entry) for entry in ranked[: max(limit, 0)]]


def load_experience_rules(limit: int = 5, *, settings: Optional[dict[str, Any]] = None) -> list[str]:
    """Rules from harness memory when consolidated, else rules_summary.json."""
    cfg = settings
    if cfg is None:
        try:
            from agent_reach.daily_run.settings import load_settings

            cfg = load_settings()
        except Exception as exc:
            logger.debug("daily-run experience load_settings failed: {}", exc)
            cfg = {}

    try:
        from agent_reach.daily_run.experience_harness import experience_consolidated_mode

        if experience_consolidated_mode(cfg):
            from agent_reach.daily_run.harness import load_harness

            state = load_harness()
            memories = list((getattr(state, "entries", {}) or {}).get("memory", {}).values())
            memories.sort(key=lambda e: str(getattr(e, "updated_at", "") or ""), reverse=True)
            rules: list[str] = []
            seen: set[str] = set()
            for entry in memories:
                job = str(getattr(entry, "job", "") or "")
                if job and job not in ("experience", "verify", "close_improve", "skill_closure"):
                    continue
                content = str(getattr(entry, "content", "") or "").strip()
                if not content or content in seen:
                    continue
                seen.add(content)
                rules.append(content)
                if len(rules) >= limit:
                    break
            return rules
    except Exception as exc:
        logger.warning("daily-run load_experience_rules harness path failed: {}", exc)

    path = experience_dir() / "rules_summary.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = list(data.get("rules") or [])
        return rules[-limit:]
    except (json.JSONDecodeError, OSError):
        return []


def render_experience_markdown(limit: int = 3, *, settings: Optional[dict[str, Any]] = None) -> str:
    recent = load_recent_experience(limit)
    consolidated = False
    try:
        from agent_reach.daily_run.experience_harness import experience_consolidated_mode

        consolidated = experience_consolidated_mode(settings)
    except Exception as exc:
        logger.debug("daily-run render_experience consolidated check failed: {}", exc)
        consolidated = False

    if not recent:
        body = ""
    else:
        lines = ["**📚 经验沉淀（最近）**", ""]
        for e in reversed(recent):
            hit = "✅" if e.get("prediction_hit") else "—"
            if consolidated or e.get("rules_in_harness"):
                lines.append(
                    f"- {e.get('date')} {e.get('name')} MSS={e.get('mss_final')} {hit} verdict={e.get('verdict')}"
                )
            else:
                lines.append(
                    f"- {e.get('date')} {e.get('name')} MSS={e.get('mss_final')} {hit} "
                    + "；".join((e.get("rules") or [])[:2])
                )
        body = "\n".join(lines)

    cfg = settings
    if cfg is None:
        try:
            from agent_reach.daily_run.settings import load_settings

            cfg = load_settings()
        except Exception as exc:
            logger.debug("daily-run experience load_settings failed: {}", exc)
            cfg = {}
    harness_cfg = (cfg or {}).get("harness") or {}
    if harness_cfg.get("enabled") is False or harness_cfg.get("inject_in_experience_card") is False:
        return body

    from agent_reach.daily_run.harness import render_harness_content

    harness_xml = render_harness_content(limit=int(harness_cfg.get("briefing_limit") or 3))
    if not harness_xml:
        return body
    harness_block = f"```xml\n{harness_xml}\n```"
    if body:
        return body + "\n\n" + harness_block
    return "**📚 Harness 记忆**\n\n" + harness_block


def _distill_rules(
    snapshot: dict[str, Any],
    verify: dict[str, Any],
    curve: Optional[dict[str, Any]],
    *,
    forecast_review: Optional[dict[str, Any]] = None,
) -> list[str]:
    rules: list[str] = []
    vc = verify.get("verdict_current")
    if vc == "回避":
        rules.append("宏观一票否决生效：维持高现金，禁止接飞刀")
    elif vc == "观察":
        cash = (snapshot.get("portfolio") or {}).get("cash_ratio")
        if cash is not None and float(cash) >= 0.4:
            rules.append(f"观察态下现金 {float(cash):.0%} 符合风控")

    if verify.get("mss_within_prediction") is False:
        rules.append("MSS 预测偏离：下日调低进攻阈值或缩窄仓位")
    elif verify.get("mss_within_prediction") is True:
        rules.append("MSS 预测命中：维持当前权重配置")

    if curve and curve.get("trend") in ("加速杀跌", "震荡走弱"):
        rules.append(f"尾盘曲线 {curve['trend']}：次日早盘偏防御")
    elif curve and curve.get("trend") in ("加速反弹", "震荡走强"):
        rules.append(f"尾盘曲线 {curve['trend']}：可保留观察池条件性机会")

    for d in (verify.get("deviations") or [])[:2]:
        rules.append(f"偏差：{d}")
    for r in (verify.get("recommendations") or [])[:2]:
        rules.append(f"建议：{r}")

    if forecast_review:
        acc = forecast_review.get("accuracy")
        total = forecast_review.get("symbol_total") or 0
        if total and acc is not None:
            if float(acc) < 0.4:
                rules.append(f"下周预测命中率 {float(acc):.0%} 偏低：扩大 change_pct_range 或提高 vol_scale")
            elif float(acc) >= 0.7:
                rules.append(f"下周预测命中率 {float(acc):.0%} 良好：维持当前校准参数")
        if forecast_review.get("mss_hit") is False:
            rules.append("MSS 日预测未命中：收盘复盘时关注 mss_forecast.base_spread")

    return rules[:6]


def _update_rules_summary(path: Path, new_rules: list[str], cfg: dict[str, Any]) -> None:
    data: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat(), "rules": []}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    existing = list(data.get("rules") or [])
    for rule in new_rules:
        if rule not in existing:
            existing.append(rule)
    max_rules = int(cfg.get("max_rules", 50))
    data["rules"] = existing[-max_rules:]
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
