# -*- coding: utf-8
"""Record and settle Xueqiu portfolio hot-stock/post hits for experience沉淀."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run.xueqiu_hit_outcomes")


def xueqiu_hit_outcomes_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = settings or {}
    macro = cfg.get("macro_collector") or {}
    nested = macro.get("xueqiu_hit_outcomes") or {}
    if nested.get("enabled") is False:
        return False
    if macro.get("xueqiu_hit_outcomes_enabled") is False:
        return False
    exp = cfg.get("experience") or {}
    if exp.get("enabled") is False:
        return False
    return True


def xueqiu_hit_outcomes_dir() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "experience"


def xueqiu_hit_pending_path() -> Path:
    return xueqiu_hit_outcomes_dir() / "xueqiu_hit_pending.json"


def xueqiu_hit_outcomes_path() -> Path:
    return xueqiu_hit_outcomes_dir() / "xueqiu_hit_outcomes.jsonl"


def build_xueqiu_hit_fingerprints(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract pending hit fingerprints from snapshot macro_signals."""
    code = str(snapshot.get("code") or "").strip()
    name = str(snapshot.get("name") or code or "").strip()
    if not code:
        return []

    macro = snapshot.get("macro_signals") or {}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in macro.get("portfolio_hot_stocks") or []:
        if not isinstance(row, dict):
            continue
        hit_code = str(row.get("code") or code).strip()
        board = str(row.get("board") or "人气榜")
        rank = row.get("rank")
        fp = f"hot_stock:{hit_code}:{board}:{rank}"
        if fp in seen:
            continue
        seen.add(fp)
        out.append(
            {
                "fingerprint": fp,
                "hit_type": "hot_stock",
                "code": hit_code,
                "name": str(row.get("name") or name),
                "role": row.get("role"),
                "board": board,
                "rank": rank,
                "percent": row.get("percent"),
            }
        )

    for row in macro.get("portfolio_hot_posts") or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("text") or "")[:80]
        keywords = row.get("matched_keywords") or []
        kw_key = keywords[0] if keywords else title[:16]
        fp = f"hot_post:{code}:{kw_key}"
        if fp in seen:
            continue
        seen.add(fp)
        out.append(
            {
                "fingerprint": fp,
                "hit_type": "hot_post",
                "code": code,
                "name": name,
                "title": title,
                "matched_keywords": keywords[:3],
                "url": row.get("url"),
            }
        )
    return out


def record_xueqiu_hit_fingerprints(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Persist morning hit fingerprints keyed by date+code for same-day settlement."""
    if not xueqiu_hit_outcomes_enabled(settings):
        return {"skipped": True, "reason": "disabled"}

    hits = build_xueqiu_hit_fingerprints(snapshot)
    code = str(snapshot.get("code") or "").strip()
    if not code:
        return {"skipped": True, "reason": "no code"}

    date_str = str(snapshot.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    out_dir = xueqiu_hit_outcomes_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = xueqiu_hit_pending_path()

    pending: dict[str, Any] = {}
    if path.exists():
        try:
            pending = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pending = {}

    key = f"{date_str}:{code}"
    if hits:
        pending[key] = {
            "date": date_str,
            "code": code,
            "name": snapshot.get("name"),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "hits": hits,
        }
    else:
        pending.pop(key, None)

    path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"recorded": len(hits), "date": date_str, "code": code, "path": str(path)}


def _load_pending_for(baseline: dict[str, Any]) -> tuple[dict[str, Any], str]:
    code = str(baseline.get("code") or "").strip()
    date_str = str(baseline.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    path = xueqiu_hit_pending_path()
    if not path.exists() or not code:
        return {}, f"{date_str}:{code}"
    try:
        pending = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}, f"{date_str}:{code}"
    key = f"{date_str}:{code}"
    return dict(pending.get(key) or {}), key


def _outcome_for_hit(
    hit: dict[str, Any],
    *,
    price_delta_pct: Optional[float],
    mss_delta: Optional[float],
    settings: Optional[dict[str, Any]] = None,
) -> tuple[str, str]:
    cfg = (settings or {}).get("macro_collector") or {}
    nested = cfg.get("xueqiu_hit_outcomes") or {}
    hit_type = hit.get("hit_type") or "hot_stock"
    if hit_type == "hot_post":
        hit_pct = float(nested.get("hot_post_hit_pct", cfg.get("xueqiu_hit_post_hit_pct", 0.003)))
        miss_pct = float(nested.get("hot_post_miss_pct", cfg.get("xueqiu_hit_post_miss_pct", -0.008)))
    else:
        hit_pct = float(nested.get("hot_stock_hit_pct", cfg.get("xueqiu_hit_stock_hit_pct", 0.005)))
        miss_pct = float(nested.get("hot_stock_miss_pct", cfg.get("xueqiu_hit_stock_miss_pct", -0.01)))

    if price_delta_pct is None:
        return "neutral", "缺少价格变动"

    if price_delta_pct >= hit_pct:
        if mss_delta is not None and mss_delta < 0:
            return "neutral", f"价格+{price_delta_pct:.1%}但MSS{mss_delta:+.0f}"
        return "hit", f"价格{price_delta_pct:+.1%}达热榜预期"

    if price_delta_pct <= miss_pct:
        return "miss", f"价格{price_delta_pct:+.1%}弱于热榜信号"

    return "neutral", f"价格{price_delta_pct:+.1%}震荡"


def settle_xueqiu_hits(
    baseline: dict[str, Any],
    current: dict[str, Any],
    verify: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compare morning Xueqiu hits vs close price/MSS and append outcomes."""
    if not xueqiu_hit_outcomes_enabled(settings):
        return {"skipped": True, "reason": "disabled"}

    pending_row, pending_key = _load_pending_for(baseline)
    hits = list(pending_row.get("hits") or [])
    if not hits:
        return {"skipped": True, "reason": "no pending hits", "pending_key": pending_key}

    price_delta_pct = verify.get("price_delta_pct")
    if price_delta_pct is None:
        pb = verify.get("price_baseline")
        pc = verify.get("price_current")
        if pb and pc and float(pb) > 0:
            price_delta_pct = (float(pc) - float(pb)) / float(pb)

    mss_delta = verify.get("mss_delta")
    settled: list[dict[str, Any]] = []
    counts = {"hit": 0, "miss": 0, "neutral": 0}

    for hit in hits:
        outcome, reason = _outcome_for_hit(
            hit,
            price_delta_pct=price_delta_pct,
            mss_delta=mss_delta,
            settings=settings,
        )
        counts[outcome] = counts.get(outcome, 0) + 1
        settled.append(
            {
                **hit,
                "date": pending_row.get("date") or baseline.get("date"),
                "code": hit.get("code") or baseline.get("code"),
                "name": hit.get("name") or baseline.get("name"),
                "outcome": outcome,
                "reason": reason,
                "price_delta_pct": price_delta_pct,
                "mss_delta": mss_delta,
                "settled_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    out_dir = xueqiu_hit_outcomes_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = xueqiu_hit_outcomes_path()
    with open(jsonl_path, "a", encoding="utf-8") as handle:
        for row in settled:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    pending_path = xueqiu_hit_pending_path()
    if pending_path.exists():
        try:
            all_pending = json.loads(pending_path.read_text(encoding="utf-8"))
            all_pending.pop(pending_key, None)
            pending_path.write_text(json.dumps(all_pending, ensure_ascii=False, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("xueqiu hit pending cleanup failed: {}", exc)

    harness_result: dict[str, Any] = {}
    try:
        from agent_reach.daily_run.xueqiu_hit_harness import apply_xueqiu_hit_harness_refinement

        harness_result = apply_xueqiu_hit_harness_refinement(settled, settings=settings)
    except Exception as exc:
        logger.warning("xueqiu hit harness failed: {}", exc)
        harness_result = {"skipped": True, "error": str(exc)}

    return {
        "settled_count": len(settled),
        "counts": counts,
        "entries": settled,
        "path": str(jsonl_path),
        "harness": harness_result,
    }


def load_recent_xueqiu_hit_outcomes(limit: int = 50) -> list[dict[str, Any]]:
    path = xueqiu_hit_outcomes_path()
    if not path.exists() or limit <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarize_xueqiu_hit_outcomes(
    entries: Optional[list[dict[str, Any]]] = None,
    *,
    days: int = 30,
) -> dict[str, Any]:
    rows = entries if entries is not None else load_recent_xueqiu_hit_outcomes(limit=500)
    if not rows:
        return {"total": 0, "hit_rate": 0.0, "by_type": {}, "recent_misses": []}

    by_type: dict[str, dict[str, int]] = {}
    recent_misses: list[str] = []
    for row in rows:
        hit_type = str(row.get("hit_type") or "unknown")
        outcome = str(row.get("outcome") or "neutral")
        bucket = by_type.setdefault(hit_type, {"hit": 0, "miss": 0, "neutral": 0, "total": 0})
        bucket[outcome] = bucket.get(outcome, 0) + 1
        bucket["total"] = bucket.get("total", 0) + 1
        if outcome == "miss" and len(recent_misses) < 3:
            label = row.get("name") or row.get("code") or hit_type
            recent_misses.append(f"{label}:{row.get('reason', '')[:40]}")

    hits = sum(r.get("outcome") == "hit" for r in rows)
    misses = sum(r.get("outcome") == "miss" for r in rows)
    scored = hits + misses
    hit_rate = round(hits / scored, 3) if scored else 0.0

    return {
        "total": len(rows),
        "hit_rate": hit_rate,
        "hits": hits,
        "misses": misses,
        "neutral": sum(r.get("outcome") == "neutral" for r in rows),
        "by_type": by_type,
        "recent_misses": recent_misses,
        "window_days": days,
    }


def render_xueqiu_hit_outcomes_markdown(
    summary: Optional[dict[str, Any]] = None,
    *,
    settled: Optional[list[dict[str, Any]]] = None,
    limit: int = 3,
) -> str:
    stats = summary or summarize_xueqiu_hit_outcomes()
    if not stats.get("total") and not settled:
        return ""

    lines = ["**雪球热榜命中复盘**"]
    if stats.get("total"):
        hr = stats.get("hit_rate")
        hr_pct = f"{hr:.0%}" if isinstance(hr, (int, float)) else "—"
        lines.append(
            f"- 近 {stats.get('window_days', 30)} 日样本 **{stats['total']}** 条，"
            f"命中率 **{hr_pct}**（命中 {stats.get('hits', 0)} / 未中 {stats.get('misses', 0)}）"
        )
        by_type = stats.get("by_type") or {}
        if by_type:
            parts = []
            for hit_type, bucket in by_type.items():
                parts.append(f"{hit_type} {bucket.get('hit', 0)}/{bucket.get('total', 0)}")
            lines.append(f"- 分型：{'；'.join(parts)}")

    rows = settled or []
    if rows:
        lines.append("")
        lines.append("**当日结算**")
        for row in rows[:limit]:
            outcome = row.get("outcome") or "neutral"
            label = row.get("name") or row.get("code") or row.get("hit_type")
            lines.append(f"- [{outcome}] {label}：{row.get('reason', '')}")

    return "\n".join(lines)
