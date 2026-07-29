# -*- coding: utf-8
"""Industry / sector classification for holdings and watchlist symbols."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.snapshot_builder import _normalize_code


def _watchlist_cfg(settings: dict[str, Any]) -> dict[str, Any]:
    return settings.get("watchlist") or {}


def build_sector_index(settings: dict[str, Any]) -> dict[str, str]:
    wl = _watchlist_cfg(settings)
    index: dict[str, str] = {}

    for code, sector in (wl.get("sector_map") or {}).items():
        norm = _normalize_code(str(code))
        if norm and sector:
            index[norm] = str(sector)

    for sector, rows in (wl.get("sector_pools") or {}).items():
        for row in rows or []:
            norm = _normalize_code(str(row.get("code", "")))
            if norm:
                index.setdefault(norm, str(sector))

    for row in wl.get("candidates") or []:
        norm = _normalize_code(str(row.get("code", "")))
        if not norm or norm in index:
            continue
        for sector, rows in (wl.get("sector_pools") or {}).items():
            if any(_normalize_code(str(r.get("code", ""))) == norm for r in rows or []):
                index[norm] = str(sector)
                break
        if norm in index:
            continue
        keywords = [str(k) for k in (row.get("keywords") or []) if k]
        name = str(row.get("name") or "")
        matched = _match_sector_by_keywords(keywords + [name], wl.get("sector_pools") or {})
        if matched:
            index[norm] = matched

    return index


def _match_sector_by_keywords(keywords: list[str], pools: dict[str, Any]) -> Optional[str]:
    text = " ".join(keywords).lower()
    if not text:
        return None
    best: Optional[tuple[int, str]] = None
    for sector, rows in pools.items():
        hits = 0
        for row in rows or []:
            for kw in row.get("keywords") or []:
                if str(kw).lower() in text:
                    hits += 1
            name = str(row.get("name") or "")
            if name and name.lower() in text:
                hits += 2
        if sector.lower() in text:
            hits += 2
        if hits and (best is None or hits > best[0]):
            best = (hits, str(sector))
    return best[1] if best else None


def lookup_sector(
    code: str,
    name: Optional[str] = None,
    *,
    settings: Optional[dict[str, Any]] = None,
    quote: Optional[dict[str, Any]] = None,
) -> str:
    """Resolve A-share sector label for a symbol."""
    norm = _normalize_code(str(code or ""))
    if not norm:
        return "未分类"

    if quote:
        for key in ("sector", "industry"):
            val = quote.get(key)
            if val and str(val) not in ("", "未分类", "综合"):
                return str(val)

    if settings:
        index = build_sector_index(settings)
        if norm in index:
            return index[norm]
        pools = _watchlist_cfg(settings).get("sector_pools") or {}
        matched = _match_sector_by_keywords([name or "", norm], pools)
        if matched:
            return matched

    if name:
        return _guess_sector_from_name(name)
    return "未分类"


def _guess_sector_from_name(name: str) -> str:
    """Lightweight name heuristics when config/quote have no sector."""
    rules = [
        (("澜起", "兆易", "中芯", "中微", "长电", "半导体"), "半导体"),
        (("京东方", "面板", "显示"), "面板"),
        (("中际", "水晶", "光", "旭创"), "光通信"),
        (("海康", "大华", "安防"), "安防"),
        (("工业富联", "服务器"), "AI算力"),
        (("海能达", "对讲", "专网"), "通信设备"),
        (("存储", "DDR"), "存储"),
    ]
    text = str(name)
    for keys, sector in rules:
        if any(k in text for k in keys):
            return sector
    return "未分类"


def attach_sector(
    row: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    quote: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    out = dict(row)
    existing = out.get("sector") or out.get("industry")
    if existing and str(existing) not in ("", "未分类", "综合"):
        out["sector"] = str(existing)
        out["industry"] = str(existing)
        return out
    code = str(out.get("code") or "")
    name = str(out.get("name") or "")
    sector = lookup_sector(code, name, settings=settings, quote=quote)
    out["sector"] = sector
    out["industry"] = sector
    return out


def attach_sectors_to_rows(
    rows: list[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
    quote_map: Optional[dict[str, dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    qmap = quote_map or {}
    return [
        attach_sector(
            row,
            settings=settings,
            quote=qmap.get(_normalize_code(str(row.get("code", "")))),
        )
        for row in rows
    ]


def enrich_symbol_map_sectors(
    symbols: dict[str, dict[str, Any]],
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, dict[str, Any]]:
    if not settings:
        return symbols
    out: dict[str, dict[str, Any]] = {}
    for code, row in symbols.items():
        out[code] = attach_sector(dict(row), settings=settings)
    return out
