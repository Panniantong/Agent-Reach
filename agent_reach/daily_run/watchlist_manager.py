# -*- coding: utf-8
"""Watchlist adjustments — allowed only at morning and close."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from agent_reach.daily_run.portfolio_manager import (
    max_total_symbols,
    unique_symbol_count,
    watchlist_capacity,
)
from agent_reach.daily_run.symbols import build_enriched_symbols, copy_portfolio
from agent_reach.daily_run.snapshot_builder import _normalize_code

WatchlistPhase = Literal["morning", "close"]

ALLOWED_WATCHLIST_PHASES = frozenset({"morning", "close"})


@dataclass
class WatchlistChange:
    action: str  # add | remove | reorder
    code: str
    name: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "code": self.code,
            "name": self.name,
            "reason": self.reason,
        }


@dataclass
class WatchlistAdjustResult:
    applied: bool
    portfolio: dict[str, Any]
    changes: list[WatchlistChange] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "message": self.message,
            "changes": [c.to_dict() for c in self.changes],
        }


def watchlist_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return settings.get("watchlist") or {}


def is_watchlist_adjust_enabled(settings: dict[str, Any]) -> bool:
    return bool(watchlist_settings(settings).get("auto_adjust_enabled", True))


def can_adjust_watchlist(phase: str) -> bool:
    return phase in ALLOWED_WATCHLIST_PHASES


def watchlist_min_size(settings: dict[str, Any]) -> int:
    return int(watchlist_settings(settings).get("min_size", 5))


def watchlist_max_size(settings: dict[str, Any]) -> int:
    return int(watchlist_settings(settings).get("max_size", 10))


def max_watchlist_size(settings: dict[str, Any], portfolio: Optional[dict[str, Any]] = None) -> int:
    """Max non-held watchlist entries (capped by portfolio total symbol limit)."""
    cap = watchlist_max_size(settings)
    if portfolio is not None:
        cap = min(cap, watchlist_capacity(settings, portfolio))
    return cap


def effective_watchlist_min(settings: dict[str, Any], portfolio: dict[str, Any]) -> int:
    """Min watchlist size, never above what total cap allows."""
    minimum = watchlist_min_size(settings)
    if minimum <= 0:
        return 0
    return min(minimum, max_watchlist_size(settings, portfolio))


def adjust_watchlist(
    portfolio: dict[str, Any],
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    phase: WatchlistPhase,
    *,
    verify: Optional[dict[str, Any]] = None,
    sold_codes: Optional[list[dict[str, Any]]] = None,
) -> WatchlistAdjustResult:
    """Update watchlist membership — only valid for morning or close."""
    if not can_adjust_watchlist(phase):
        return WatchlistAdjustResult(
            applied=False,
            portfolio=portfolio,
            message=f"观察池仅可在早盘/复盘调整，当前 phase={phase}",
        )
    if not is_watchlist_adjust_enabled(settings):
        return WatchlistAdjustResult(applied=False, portfolio=portfolio, message="watchlist.auto_adjust 未启用")

    pf = copy_portfolio(portfolio)
    enriched = build_enriched_symbols(snapshot)
    changes: list[WatchlistChange] = []
    thresholds = settings.get("thresholds", {})
    macro_veto = float(thresholds.get("macro_veto", 40))
    held_codes = {_normalize_code(str(h.get("code", ""))) for h in pf.get("holdings") or []}
    base_mss = _snapshot_base_mss(snapshot, settings)
    wl_cfg = watchlist_settings(settings)

    if phase == "close" and sold_codes:
        for item in sold_codes:
            code = _normalize_code(str(item.get("code", "")))
            if not code or code in held_codes:
                continue
            if _has_code(pf.get("watchlist") or [], code):
                continue
            if _watchlist_only_count(pf, held_codes) >= max_watchlist_size(settings, pf):
                break
            if unique_symbol_count(pf) >= max_total_symbols(settings):
                break
            name = str(item.get("name") or code)
            pf.setdefault("watchlist", []).append({"code": code, "name": name})
            changes.append(WatchlistChange("add", code, name, "盘中卖出，收盘复盘回收入观察池"))

    # Remove: already held, missing quote, or weak momentum
    kept: list[dict[str, Any]] = []
    for w in pf.get("watchlist") or []:
        code = _normalize_code(str(w.get("code", "")))
        row = {**w, **enriched.get(code, {})}
        if code in held_codes:
            changes.append(
                WatchlistChange("remove", code, str(w.get("name", code)), "已持仓，移出观察池")
            )
            continue
        chg = row.get("change_pct")
        score = _symbol_score(row, base_mss=base_mss)
        if chg is not None and float(chg) <= -8:
            changes.append(
                WatchlistChange("remove", code, str(w.get("name", code)), f"跌幅 {float(chg):.1f}% 过大")
            )
            continue
        if score < macro_veto:
            changes.append(
                WatchlistChange("remove", code, str(w.get("name", code)), f"评分 {score:.0f} 低于否决线")
            )
            continue
        kept.append(dict(w))

    pf["watchlist"] = kept

    if phase == "close" and wl_cfg.get("hot_topic_adjust_enabled", True):
        _apply_close_hot_topic_adjust(
            pf,
            snapshot,
            settings,
            enriched,
            changes,
            held_codes=held_codes,
            base_mss=base_mss,
        )

    # Morning: optionally add candidates from config
    if phase == "morning":
        _add_candidates(
            pf,
            settings,
            held_codes,
            changes,
            reason="早盘候选纳入观察池",
            prefer_hot=False,
            snapshot=snapshot,
            enriched=enriched,
            base_mss=base_mss,
        )

    if phase == "close":
        _fill_watchlist_to_min(
            pf,
            snapshot,
            settings,
            enriched,
            changes,
            held_codes=held_codes,
            base_mss=base_mss,
        )

    # Trim to watchlist max (non-held count)
    pf["watchlist"] = _trim_by_score(
        pf["watchlist"],
        enriched,
        settings,
        max_watchlist_size(settings, pf),
        changes,
        base_mss=base_mss,
    )

    if verify and verify.get("verdict_current") == "回避":
        # Macro risk-off: keep only top 3 watchlist names
        pf["watchlist"] = _trim_by_score(
            pf["watchlist"],
            enriched,
            settings,
            min(3, max_watchlist_size(settings, pf)),
            changes,
            reason_prefix="宏观回避，收缩观察池",
            base_mss=base_mss,
        )

    if phase == "close" and wl_cfg.get("close_reorder_by_performance", True):
        reordered = _sort_watchlist_by_performance(pf["watchlist"], enriched)
        if [w.get("code") for w in reordered] != [w.get("code") for w in pf["watchlist"]]:
            pf["watchlist"] = reordered
            top = reordered[0] if reordered else {}
            changes.append(
                WatchlistChange(
                    "reorder",
                    str(top.get("code", "")),
                    str(top.get("name", "")),
                    "收盘按涨跌幅由高到低重排观察池",
                )
            )

    if not changes:
        return WatchlistAdjustResult(applied=False, portfolio=pf, message="观察池无变更")

    return WatchlistAdjustResult(
        applied=True,
        portfolio=pf,
        changes=changes,
        message=f"观察池调整 {len(changes)} 项（{phase}）",
    )


def render_watchlist_adjust_markdown(result: WatchlistAdjustResult) -> str:
    if not result.applied:
        return f"**观察池：** 未调整 — {result.message}"
    lines = [f"**观察池调整（{result.message}）：**"]
    for c in result.changes:
        if c.action == "reorder":
            lines.append(f"- 重排观察池 — {c.reason}")
            continue
        verb = "纳入" if c.action == "add" else "移出"
        lines.append(f"- {verb} **{c.name}** ({c.code}) — {c.reason}")
    return "\n".join(lines)


def _watchlist_only_count(portfolio: dict[str, Any], held_codes: set[str]) -> int:
    return len(
        [
            w
            for w in portfolio.get("watchlist") or []
            if _normalize_code(str(w.get("code", ""))) not in held_codes
        ]
    )


def _sort_watchlist_by_performance(
    watchlist: list[dict[str, Any]],
    enriched: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    def perf(w: dict[str, Any]) -> float:
        code = _normalize_code(str(w.get("code", "")))
        row = {**w, **enriched.get(code, {})}
        chg = row.get("change_pct")
        if chg is None:
            return -999.0
        return float(chg)

    return sorted(watchlist, key=perf, reverse=True)


def _extract_hot_titles(snapshot: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()

    def add(text: Any) -> None:
        t = str(text or "").strip()
        if not t or t in seen:
            return
        seen.add(t)
        titles.append(t)

    for key in ("hot_topics_matched", "hot_topics"):
        for item in snapshot.get(key) or []:
            if isinstance(item, dict):
                add(item.get("title"))
            elif isinstance(item, str):
                add(item)

    hot_src = (snapshot.get("sources") or {}).get("hot_news") or {}
    add(hot_src.get("summary"))
    for line in str(hot_src.get("text_feed") or "").splitlines():
        cleaned = line.strip().lstrip("0123456789. ").strip()
        if cleaned and not cleaned.startswith("📰") and not cleaned.startswith("🔥"):
            add(cleaned)
    return titles


def _hot_titles_for_adjust(
    snapshot: dict[str, Any],
    portfolio: dict[str, Any],
    settings: dict[str, Any],
) -> list[str]:
    titles = _extract_hot_titles(snapshot)
    if titles:
        return titles
    wl_cfg = watchlist_settings(settings)
    if wl_cfg.get("hot_topic_fetch_if_missing", True) is False:
        return titles
    try:
        from agent_reach.daily_run.hot_news_collector import collect_hot_news

        hot = collect_hot_news(portfolio, settings=settings)
        for item in (hot.matched or hot.items)[:40]:
            if isinstance(item, dict):
                titles.append(str(item.get("title") or ""))
        titles.extend(hot.daily_headlines or [])
    except Exception:
        pass
    return [t for t in titles if t.strip()]


def _candidate_keywords(cand: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for kw in cand.get("keywords") or []:
        token = str(kw).strip()
        if token and token not in seen:
            seen.add(token)
            keys.append(token)
    name = str(cand.get("name") or "").strip()
    if name:
        for token in (name, name[:4]):
            if token and token not in seen:
                seen.add(token)
                keys.append(token)
    code = str(cand.get("code") or "").strip()
    if code and code not in seen:
        keys.append(code)
    return keys


def _matches_hot_topics(keywords: list[str], hot_titles: list[str]) -> bool:
    if not hot_titles or not keywords:
        return False
    from agent_reach.daily_run.hot_news_collector import _matches_keywords

    for title in hot_titles:
        if _matches_keywords(title, keywords):
            return True
    return False


def _symbol_hot_keywords(row: dict[str, Any]) -> list[str]:
    name = str(row.get("name") or "").strip()
    keys: list[str] = []
    if name:
        keys.extend([name, name[:4]])
    code = str(row.get("code") or "").strip()
    if code:
        keys.append(code)
    return keys


def _apply_close_hot_topic_adjust(
    pf: dict[str, Any],
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    changes: list[WatchlistChange],
    *,
    held_codes: set[str],
    base_mss: float,
) -> None:
    wl_cfg = watchlist_settings(settings)
    hot_titles = _hot_titles_for_adjust(snapshot, pf, settings)
    remove_floor = float(wl_cfg.get("hot_topic_remove_change_pct", -2.0))

    kept: list[dict[str, Any]] = []
    for w in pf.get("watchlist") or []:
        code = _normalize_code(str(w.get("code", "")))
        if code in held_codes:
            continue
        row = {**w, **enriched.get(code, {})}
        if _matches_hot_topics(_symbol_hot_keywords(row), hot_titles):
            kept.append(dict(w))
            continue
        chg = row.get("change_pct")
        score = _symbol_score(row, base_mss=base_mss)
        if chg is not None and float(chg) < remove_floor:
            changes.append(
                WatchlistChange(
                    "remove",
                    code,
                    str(w.get("name", code)),
                    f"无热点关联且跌幅 {float(chg):.1f}%",
                )
            )
            continue
        if score < base_mss - 8:
            changes.append(
                WatchlistChange(
                    "remove",
                    code,
                    str(w.get("name", code)),
                    "无热点关联且相对大盘走弱",
                )
            )
            continue
        kept.append(dict(w))
    pf["watchlist"] = kept

    _add_candidates(
        pf,
        settings,
        held_codes,
        changes,
        reason="热点匹配，收盘纳入观察池",
        prefer_hot=True,
        snapshot=snapshot,
        enriched=enriched,
        base_mss=base_mss,
        hot_titles=hot_titles,
    )


def _add_candidates(
    pf: dict[str, Any],
    settings: dict[str, Any],
    held_codes: set[str],
    changes: list[WatchlistChange],
    *,
    reason: str,
    prefer_hot: bool,
    snapshot: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    base_mss: float,
    hot_titles: Optional[list[str]] = None,
) -> None:
    titles = hot_titles if hot_titles is not None else _hot_titles_for_adjust(snapshot, pf, settings)
    candidates = list(watchlist_settings(settings).get("candidates") or [])
    if prefer_hot:
        hot_cands = [
            c
            for c in candidates
            if _matches_hot_topics(_candidate_keywords(c), titles)
        ]
        other_cands = [c for c in candidates if c not in hot_cands]
        candidates = hot_cands + other_cands
    else:
        candidates = sorted(
            candidates,
            key=lambda c: _symbol_score(
                enriched.get(_normalize_code(str(c.get("code", ""))), {}),
                base_mss=base_mss,
            ),
            reverse=True,
        )

    for cand in candidates:
        code = _normalize_code(str(cand.get("code", "")))
        if not code or code in held_codes or _has_code(pf.get("watchlist") or [], code):
            continue
        if _watchlist_only_count(pf, held_codes) >= max_watchlist_size(settings, pf):
            break
        if unique_symbol_count(pf) >= max_total_symbols(settings):
            break
        if prefer_hot and not _matches_hot_topics(_candidate_keywords(cand), titles):
            continue
        name = str(cand.get("name") or code)
        pf.setdefault("watchlist", []).append({"code": code, "name": name})
        hit_reason = reason
        if prefer_hot and _matches_hot_topics(_candidate_keywords(cand), titles):
            hit_reason = "市场热点匹配，收盘纳入观察池"
        changes.append(WatchlistChange("add", code, name, hit_reason))


def _fill_watchlist_to_min(
    pf: dict[str, Any],
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
    changes: list[WatchlistChange],
    *,
    held_codes: set[str],
    base_mss: float,
) -> None:
    target_min = effective_watchlist_min(settings, pf)
    hot_titles = _hot_titles_for_adjust(snapshot, pf, settings)
    while _watchlist_only_count(pf, held_codes) < target_min:
        before = _watchlist_only_count(pf, held_codes)
        if hot_titles:
            _add_candidates(
                pf,
                settings,
                held_codes,
                changes,
                reason="补足观察池下限（热点优先）",
                prefer_hot=True,
                snapshot=snapshot,
                enriched=enriched,
                base_mss=base_mss,
                hot_titles=hot_titles,
            )
        if _watchlist_only_count(pf, held_codes) == before:
            _add_candidates(
                pf,
                settings,
                held_codes,
                changes,
                reason="补足观察池下限（候选池）",
                prefer_hot=False,
                snapshot=snapshot,
                enriched=enriched,
                base_mss=base_mss,
            )
        if _watchlist_only_count(pf, held_codes) == before:
            break


def _trim_by_score(
    watchlist: list[dict[str, Any]],
    enriched: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    limit: int,
    changes: list[WatchlistChange],
    *,
    reason_prefix: str = "超出上限，按评分保留",
    base_mss: Optional[float] = None,
) -> list[dict[str, Any]]:
    if len(watchlist) <= limit:
        return watchlist
    scored = [
        (
            _symbol_score(
                {**w, **enriched.get(_normalize_code(str(w.get("code", ""))), {})},
                base_mss=base_mss,
            ),
            w,
        )
        for w in watchlist
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    kept = [w for _, w in scored[:limit]]
    kept_codes = {_normalize_code(str(w.get("code", ""))) for w in kept}
    for w in watchlist:
        code = _normalize_code(str(w.get("code", "")))
        if code not in kept_codes:
            changes.append(
                WatchlistChange("remove", code, str(w.get("name", code)), reason_prefix)
            )
    return kept


def _snapshot_base_mss(snapshot: dict[str, Any], settings: dict[str, Any]) -> float:
    if snapshot.get("mss_final") is not None:
        return float(snapshot["mss_final"])
    breakdown = snapshot.get("mss_breakdown") or {}
    if breakdown:
        from agent_reach.daily_run.verdict import compute_mss

        return float(compute_mss(breakdown, settings))
    return 50.0


def _symbol_score(row: dict[str, Any], *, base_mss: Optional[float] = None) -> float:
    base = float(base_mss if base_mss is not None else 50)
    chg = row.get("change_pct")
    if chg is not None:
        base += float(chg) * 0.5
    return base


def _has_code(watchlist: list[dict[str, Any]], code: str) -> bool:
    return any(_normalize_code(str(w.get("code", ""))) == code for w in watchlist)


def collect_intraday_sold_codes(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Read today's sell actions from trade ledger for close watchlist recycle."""
    from agent_reach.daily_run.portfolio_manager import default_ledger_path
    from agent_reach.daily_run.trade_calendar import today_shanghai
    import json

    path = default_ledger_path()
    if not path.exists():
        return []
    today = today_shanghai().isoformat()
    sold: list[dict[str, Any]] = []
    # Tail-read recent lines only (ledger grows append-only)
    raw = path.read_bytes()
    chunk = raw[-65536:] if len(raw) > 65536 else raw
    for line in chunk.decode("utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not str(entry.get("at", "")).startswith(today):
            continue
        for action in entry.get("actions") or []:
            if action.get("side") == "sell":
                sold.append({"code": action.get("code"), "name": action.get("name")})
    return sold
