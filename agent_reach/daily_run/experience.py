# -*- coding: utf-8
"""Experience writeback — atomize close review into rule library."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


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
) -> Path:
    """Append one close review atom to experience.jsonl and update rules summary."""
    cfg = (settings or {}).get("experience", {})
    if cfg.get("enabled") is False:
        return experience_dir() / "experience.jsonl"

    out_dir = experience_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "experience.jsonl"

    rules = _distill_rules(snapshot, verify, curve, forecast_review=forecast_review)
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
        "rules": rules,
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

    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _update_rules_summary(out_dir / "rules_summary.json", rules, cfg)
    return jsonl_path


def load_recent_experience(limit: int = 10) -> list[dict[str, Any]]:
    path = experience_dir() / "experience.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def render_experience_markdown(limit: int = 3, *, settings: Optional[dict[str, Any]] = None) -> str:
    recent = load_recent_experience(limit)
    if not recent:
        body = ""
    else:
        lines = ["**📚 经验沉淀（最近）**", ""]
        for e in reversed(recent):
            hit = "✅" if e.get("prediction_hit") else "—"
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
        except Exception:
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
