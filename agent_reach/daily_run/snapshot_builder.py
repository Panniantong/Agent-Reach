# -*- coding: utf-8
"""Build daily-run snapshots from portfolio config + live quotes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.macro_collector import collect_macro_context
from agent_reach.daily_run.mss_forecast import forecast_mss_range
from agent_reach.daily_run.snapshot_cache import load_daily_cache, load_last_snapshot, save_daily_cache

EnrichLevel = str  # full | quotes | lite


def default_portfolio_path() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "portfolio.json"


def example_portfolio_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "daily_run_portfolio.example.json"


def repo_portfolio_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "daily_run_portfolio.json"


def _portfolio_is_empty(data: dict[str, Any]) -> bool:
    holdings = data.get("holdings") or []
    watchlist = data.get("watchlist") or []
    return not holdings and not watchlist


def _finalize_portfolio(data: dict[str, Any]) -> dict[str, Any]:
    """Sync derived portfolio fields whenever config is loaded from disk."""
    if not data.get("holdings"):
        return data
    from agent_reach.daily_run.portfolio_manager import sync_portfolio_holding_days
    from agent_reach.daily_run.settings import load_settings

    return sync_portfolio_holding_days(data, settings=load_settings())


def load_portfolio(path: Optional[Path] = None) -> dict[str, Any]:
    p = path or default_portfolio_path()
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        if not _portfolio_is_empty(data):
            return _finalize_portfolio(data)

    for fallback in (repo_portfolio_path(), example_portfolio_path()):
        if fallback.exists():
            data = json.loads(fallback.read_text(encoding="utf-8"))
            if not _portfolio_is_empty(data):
                return _finalize_portfolio(data)

    if p.exists():
        return _finalize_portfolio(json.loads(p.read_text(encoding="utf-8")))

    raise FileNotFoundError(
        f"未找到持仓配置：{p}。可复制 config/daily_run_portfolio.json 到该路径"
    )


def save_portfolio(portfolio: dict[str, Any], path: Optional[Path] = None) -> Path:
    from agent_reach.daily_run.portfolio_manager import sync_portfolio_holding_days
    from agent_reach.daily_run.settings import load_settings

    portfolio = sync_portfolio_holding_days(portfolio, settings=load_settings())
    p = path or default_portfolio_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def code_to_xueqiu_symbol(code: str) -> str:
    text = code.strip().upper()
    for prefix in ("SH", "SZ", "BJ"):
        if text.startswith(prefix):
            return text
    text = text.zfill(6)
    if text.startswith(("5", "6", "9")):
        return f"SH{text}"
    if text.startswith(("4", "8")):
        return f"BJ{text}"
    return f"SZ{text}"


def _normalize_code(code: str) -> str:
    return code.zfill(6)[-6:] if str(code).isdigit() else str(code)


def fetch_quotes_map(
    codes: list[str],
    config=None,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, dict[str, Any]]:
    """Batch fetch quotes using configured source priority (akshare → xueqiu by default)."""
    from agent_reach.daily_run.quote_fetch import fetch_quotes_map as fetch_multi
    from agent_reach.daily_run.settings import load_settings

    unique = list(dict.fromkeys(_normalize_code(c) for c in codes if c))
    if not unique:
        return {}

    cfg = settings or load_settings()
    result = fetch_multi(unique, config, settings=cfg)
    return dict(result.quotes)


def fetch_quotes_result(
    codes: list[str],
    config=None,
    *,
    settings: Optional[dict[str, Any]] = None,
):
    """Like fetch_quotes_map but returns QuoteFetchResult for coverage metadata."""
    from agent_reach.daily_run.quote_fetch import fetch_quotes_map as fetch_multi
    from agent_reach.daily_run.settings import load_settings

    unique = list(dict.fromkeys(_normalize_code(c) for c in codes if c))
    cfg = settings or load_settings()
    return fetch_multi(unique, config, settings=cfg)


def _primary_row_fields(
    holdings: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    code_norm: str,
) -> dict[str, Any]:
    """Pull price/technicals from enriched holding or watchlist row for primary symbol."""
    for row in holdings + watchlist:
        if _normalize_code(str(row.get("code", ""))) != code_norm:
            continue
        fields: dict[str, Any] = {}
        for key in ("price", "change_pct", "ma20", "ma5", "position_20d", "volume_ratio", "name", "unrealized_pnl"):
            if row.get(key) is not None:
                fields[key] = row[key]
        return fields
    return {}


_TECHNICAL_KEYS = ("ma20", "ma5", "position_20d", "volume_ratio")


try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run.snapshot_builder")


def _technicals_patch(enriched: dict[str, Any]) -> dict[str, Any]:
    return {k: enriched.get(k) for k in _TECHNICAL_KEYS if enriched.get(k) is not None}


def _technicals_cost_fallback_enabled(settings: Optional[dict[str, Any]]) -> bool:
    snap = (settings or {}).get("snapshot") or {}
    return snap.get("technicals_cost_fallback", True) is not False


def _estimate_position_20d(price: Any, ma20: Any) -> Optional[float]:
    if price is None or ma20 is None:
        return None
    ma = float(ma20)
    if ma <= 0:
        return None
    ratio = (float(price) - ma) / ma
    return round(max(0.05, min(0.95, 0.5 + ratio * 2)), 4)


def _source_rows_by_code(portfolio: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in (portfolio.get("holdings") or []) + (portfolio.get("watchlist") or []):
        code = _normalize_code(str(row.get("code") or ""))
        if code:
            rows[code] = dict(row)
    return rows


def _fallback_technicals_patch(
    code: str,
    quote: dict[str, Any],
    *,
    row: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Seed ma20/position from portfolio row when AKShare hist is unavailable."""
    src = row or {}
    ma20 = src.get("ma20") if row else quote.get("ma20")
    if ma20 is None and row and _technicals_cost_fallback_enabled(settings):
        cost = row.get("cost")
        if cost is not None:
            ma20 = cost
    if ma20 is None:
        return {}

    price = quote.get("price") if quote.get("price") is not None else src.get("price")
    patch: dict[str, Any] = {"ma20": round(float(ma20), 2)}
    pos = _estimate_position_20d(price, ma20)
    if pos is not None:
        patch["position_20d"] = pos
    if row and row.get("volume_ratio") is not None and quote.get("volume_ratio") is None:
        patch["volume_ratio"] = row["volume_ratio"]
    return patch


def _attach_technicals(
    quote: dict[str, Any],
    code: str,
    *,
    fallback_row: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    out = dict(quote)
    norm = _normalize_code(code)
    try:
        from agent_reach.daily_run.akshare_adapter import fetch_technicals

        out.update(fetch_technicals(norm))
    except Exception as exc:
        logger.warning("akshare technicals failed for {}: {}", norm, exc)

    if _technicals_patch(out).get("ma20") is None:
        fb = _fallback_technicals_patch(norm, out, row=fallback_row, settings=settings)
        if fb:
            out.update(fb)
            logger.info(
                "technicals fallback for {}: ma20={} source={}",
                norm,
                fb.get("ma20"),
                "portfolio" if (fallback_row or {}).get("ma20") is not None else "cost",
            )
    return out


def _ensure_cached_technicals(
    codes: list[str],
    quote_map: dict[str, dict[str, Any]],
    cached_technicals: dict[str, Any],
    source_rows: dict[str, dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    updated = dict(cached_technicals)
    for code in dict.fromkeys(codes):
        if code not in quote_map:
            continue
        have = updated.get(code) or {}
        if isinstance(have, dict) and have.get("ma20") is not None:
            continue
        patch = _technicals_patch(quote_map[code])
        if patch.get("ma20") is None:
            patch = _fallback_technicals_patch(
                code,
                quote_map[code],
                row=source_rows.get(code),
                settings=settings,
            )
        if patch:
            updated[code] = {**(have if isinstance(have, dict) else {}), **patch}
            quote_map[code] = {**quote_map[code], **patch}
    return updated


def _apply_cached_technicals(
    quote_map: dict[str, dict[str, Any]],
    cached_technicals: dict[str, Any],
) -> None:
    for code, fields in cached_technicals.items():
        if code in quote_map and isinstance(fields, dict) and fields:
            quote_map[code] = {**quote_map[code], **fields}


def _backfill_missing_technicals(
    codes: list[str],
    quote_map: dict[str, dict[str, Any]],
    cached_technicals: dict[str, Any],
    *,
    source_rows: Optional[dict[str, dict[str, Any]]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Fetch AKShare technicals for symbols still missing ma20 during intraday."""
    from agent_reach.daily_run.snapshot_cache import merge_technicals, save_daily_cache

    updated = dict(cached_technicals)
    patches: dict[str, dict[str, Any]] = {}
    for code in dict.fromkeys(codes):
        if code not in quote_map:
            continue
        have = updated.get(code) or {}
        if isinstance(have, dict) and have.get("ma20") is not None:
            continue
        patch = _technicals_patch(
            _attach_technicals(
                quote_map[code],
                code,
                fallback_row=(source_rows or {}).get(code),
                settings=settings,
            )
        )
        if patch.get("ma20") is None:
            patch = _fallback_technicals_patch(
                code,
                quote_map[code],
                row=(source_rows or {}).get(code),
                settings=settings,
            )
        if patch:
            patches[code] = patch
            quote_map[code] = {**quote_map[code], **patch}
    if patches:
        updated = merge_technicals(updated, patches)
        save_daily_cache({"technicals": updated})
    return updated


def _try_akshare_quote(code: str) -> Optional[dict[str, Any]]:
    try:
        from agent_reach.daily_run.akshare_adapter import fetch_quote

        return fetch_quote(code)
    except Exception:
        return None


def enrich_holding(
    holding: dict[str, Any],
    quote_map: dict[str, dict[str, Any]],
    *,
    with_technicals: bool = False,
) -> dict[str, Any]:
    code = _normalize_code(str(holding.get("code", "")))
    out = dict(holding)
    quote = quote_map.get(code)
    if quote:
        if quote.get("price") is not None:
            out["price"] = quote["price"]
        if quote.get("change_pct") is not None:
            out["change_pct"] = quote.get("change_pct")
        out["name"] = quote.get("name") or out.get("name")
        out["quote_source"] = quote.get("source")
        for k in _TECHNICAL_KEYS:
            if quote.get(k) is not None and out.get(k) is None:
                out[k] = quote[k]
        for k in ("sector", "industry"):
            if quote.get(k) and not out.get(k):
                out[k] = quote[k]
        if with_technicals:
            enriched = _attach_technicals(quote, code, fallback_row=out)
            for k in _TECHNICAL_KEYS:
                if enriched.get(k) is not None:
                    out[k] = enriched[k]
    elif out.get("cost") is not None:
        fallback = _try_akshare_quote(code)
        if fallback and fallback.get("price") is not None:
            out["price"] = fallback["price"]
            out["change_pct"] = fallback.get("change_pct")
            out["name"] = fallback.get("name") or out.get("name")
            out["quote_source"] = fallback.get("source", "akshare_spot_em")
            if fallback.get("volume_ratio") is not None:
                out["volume_ratio"] = fallback["volume_ratio"]
            if with_technicals:
                enriched = _attach_technicals(fallback, code)
                for k in _TECHNICAL_KEYS:
                    if enriched.get(k) is not None:
                        out[k] = enriched[k]
        else:
            out["price"] = out["cost"]
            out["quote_source"] = "cost_fallback"
    return out


def build_snapshot(
    portfolio: Optional[dict[str, Any]] = None,
    *,
    report_type: str = "intraday",
    primary_code: Optional[str] = None,
    config=None,
    enrich: bool = True,
    enrich_level: EnrichLevel = "full",
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a daily-run snapshot from portfolio + live macro/quotes.

    enrich_level:
      - full: macro + quotes + technicals (morning/close)
      - quotes: refresh quotes, reuse cached macro/technicals (intraday)
      - lite: reuse last_snapshot, refresh quotes only (weekend jobs)
    """
    from agent_reach.daily_run.settings import load_settings

    if not enrich:
        enrich_level = "lite"

    cfg = settings or load_settings()
    snap_cfg = cfg.get("snapshot") or {}
    if enrich_level == "full" and snap_cfg.get("intraday_enrich_level") and report_type == "intraday":
        enrich_level = str(snap_cfg.get("intraday_enrich_level", "quotes"))

    if enrich_level == "lite":
        return _build_lite_snapshot(
            portfolio=portfolio,
            report_type=report_type,
            primary_code=primary_code,
            config=config,
            settings=cfg,
        )

    pf = portfolio or load_portfolio()
    source_rows_by_code = _source_rows_by_code(pf)
    code = primary_code or pf.get("primary_code") or "MARKET"
    if code == "MARKET" and pf.get("holdings"):
        code = str(pf["holdings"][0]["code"])

    code_norm = _normalize_code(str(code))
    holdings = [dict(h) for h in (pf.get("holdings") or [])]
    watchlist = [dict(w) for w in (pf.get("watchlist") or [])]

    daily_cache = load_daily_cache() if enrich_level == "quotes" else {}
    macro_ctx: dict[str, Any] = {}
    if enrich_level == "full":
        macro_ctx = collect_macro_context(pf, config=config, settings=cfg, workflow=report_type)
    elif daily_cache.get("macro_ctx"):
        macro_ctx = dict(daily_cache["macro_ctx"])
    else:
        macro_ctx = collect_macro_context(pf, config=config, settings=cfg, workflow=report_type)

    primary_name = code_norm
    primary_price = None
    primary_ma20 = None
    primary_ma5 = None
    primary_pos = None
    primary_vol = None
    primary_change = None
    quote_summary_parts: list[str] = []
    has_cost_fallback = False
    cached_technicals: dict[str, Any] = dict(daily_cache.get("technicals") or {})

    all_codes = [code_norm] + [
        _normalize_code(str(h.get("code", ""))) for h in holdings
    ] + [_normalize_code(str(w.get("code", ""))) for w in watchlist]
    quote_result = fetch_quotes_result(all_codes, config, settings=cfg)
    quote_map = dict(quote_result.quotes)
    quote_meta = {
        "sources_used": list(quote_result.sources_used),
        "coverage_pct": round(quote_result.coverage_for(all_codes) * 100, 1),
        "errors": dict(quote_result.errors),
    }

    if enrich_level == "quotes":
        cached_technicals = _backfill_missing_technicals(
            all_codes,
            quote_map,
            cached_technicals,
            source_rows=source_rows_by_code,
            settings=cfg,
        )
        _apply_cached_technicals(quote_map, cached_technicals)

    def _enrich_row(row: dict[str, Any], *, with_technicals: bool) -> dict[str, Any]:
        c = _normalize_code(str(row.get("code", "")))
        merged_map = dict(quote_map)
        if c in cached_technicals:
            merged_map[c] = {**merged_map.get(c, {}), **cached_technicals[c]}
        return enrich_holding(row, merged_map, with_technicals=with_technicals)

    holdings = [
        _enrich_row(h, with_technicals=enrich_level == "full")
        for h in holdings
    ]
    watchlist = [
        _enrich_row(w, with_technicals=enrich_level == "full")
        for w in watchlist
    ]

    from agent_reach.daily_run.sector_classifier import attach_sectors_to_rows

    holdings = attach_sectors_to_rows(holdings, settings=cfg, quote_map=quote_map)
    watchlist = attach_sectors_to_rows(watchlist, settings=cfg, quote_map=quote_map)
    for code, quote in quote_map.items():
        if quote.get("sector") or quote.get("industry"):
            continue
        from agent_reach.daily_run.sector_classifier import attach_sector

        patched = attach_sector({"code": code, "name": quote.get("name")}, settings=cfg, quote=quote)
        if patched.get("sector"):
            quote_map[code] = {**quote, "sector": patched["sector"], "industry": patched["sector"]}

    if enrich_level == "full":
        for c in dict.fromkeys(all_codes):
            if c not in quote_map:
                continue
            enriched = _attach_technicals(
                quote_map[c],
                c,
                fallback_row=source_rows_by_code.get(c),
                settings=cfg,
            )
            quote_map[c] = enriched
            patch = _technicals_patch(enriched)
            if patch:
                cached_technicals[c] = patch
        cached_technicals = _ensure_cached_technicals(
            all_codes,
            quote_map,
            cached_technicals,
            source_rows_by_code,
            settings=cfg,
        )

    # When live quotes fail, seed primary symbol from cost/holding row and retry technicals.
    if code_norm not in quote_map:
        for row in holdings + watchlist:
            if _normalize_code(str(row.get("code", ""))) == code_norm and row.get("price") is not None:
                stub = {
                    "code": code_norm,
                    "name": row.get("name", code_norm),
                    "price": row["price"],
                    "change_pct": row.get("change_pct"),
                    "source": row.get("quote_source") or "cost_fallback",
                }
                if enrich_level == "full":
                    quote_map[code_norm] = _attach_technicals(
                        stub,
                        code_norm,
                        fallback_row=source_rows_by_code.get(code_norm),
                        settings=cfg,
                    )
                else:
                    quote_map[code_norm] = stub
                break

    row_fields = _primary_row_fields(holdings, watchlist, code_norm)
    if code_norm in quote_map:
        primary_quote = {**quote_map[code_norm], **row_fields}
        primary_name = primary_quote.get("name", code_norm)
        primary_price = primary_quote.get("price")
        primary_ma20 = primary_quote.get("ma20")
        primary_ma5 = primary_quote.get("ma5")
        primary_pos = primary_quote.get("position_20d")
        primary_vol = primary_quote.get("volume_ratio")
        primary_change = primary_quote.get("change_pct")
    else:
        primary_change = row_fields.get("change_pct")
        if row_fields.get("price") is not None:
            primary_price = row_fields["price"]
        if row_fields.get("name"):
            primary_name = str(row_fields["name"])

    for eh in holdings + watchlist:
        if eh.get("quote_source") == "cost_fallback":
            has_cost_fallback = True
        if eh.get("price") is not None:
            chg = eh.get("change_pct")
            chg_s = f" {chg:+.2f}%" if chg is not None else ""
            quote_summary_parts.append(f"{eh.get('name')} {eh['price']}{chg_s}")

    portfolio_block = {
        "total": pf.get("total"),
        "cash_ratio": pf.get("cash_ratio"),
        "cash": pf.get("cash"),
        "holdings": holdings,
    }

    sources = dict(macro_ctx.get("sources") or {})
    if quote_summary_parts:
        sources["quote"] = {
            "summary": " · ".join(quote_summary_parts[:4]),
            "backend": "snapshot_builder",
        }

    mss_breakdown = dict(macro_ctx.get("mss_breakdown") or pf.get("mss_breakdown") or {})
    from agent_reach.daily_run.trade_calendar import today_shanghai

    today = today_shanghai().isoformat()
    if report_type == "premarket" and primary_code:
        for row in holdings + watchlist:
            if _normalize_code(str(row.get("code", ""))) == code_norm:
                primary_name = str(row.get("name") or primary_name)
                break
        snapshot_name = primary_name
    elif report_type == "premarket":
        snapshot_name = f"{today} 早盘"
    else:
        snapshot_name = primary_name

    snapshot: dict[str, Any] = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "report_type": report_type,
        "enrich_level": enrich_level,
        "code": code_norm,
        "name": snapshot_name,
        "mss_breakdown": mss_breakdown,
        "sources": sources,
        "structured_review_complete": primary_ma20 is not None,
        "macro_summary": macro_ctx.get("macro_summary") or pf.get("macro_summary"),
        "macro_signals": macro_ctx.get("macro_signals"),
        "portfolio": portfolio_block,
        "watchlist": watchlist,
        "has_cost_fallback": has_cost_fallback,
        "quote_fetch": quote_meta,
    }
    rf = (macro_ctx.get("macro_signals") or {}).get("redfox")
    if isinstance(rf, dict):
        snapshot["redfox"] = rf

    if primary_price is not None:
        snapshot["price"] = primary_price
        snapshot["reference_price"] = primary_price
    if primary_ma20 is not None:
        snapshot["ma20"] = primary_ma20
    if primary_ma5 is not None:
        snapshot["ma5"] = primary_ma5
    if primary_pos is not None:
        snapshot["position_20d"] = primary_pos
    if primary_vol is not None:
        snapshot["volume_ratio"] = primary_vol
    if primary_change is not None:
        snapshot["change_pct"] = primary_change
    if row_fields.get("unrealized_pnl") is not None:
        snapshot["unrealized_pnl"] = row_fields["unrealized_pnl"]

    if report_type == "premarket" and enrich_level == "full":
        mss_range, forecast_meta = forecast_mss_range(snapshot, cfg)
        snapshot["mss_range"] = mss_range
        snapshot["mss_forecast"] = forecast_meta
    else:
        snapshot["mss_range"] = pf.get("mss_range") or daily_cache.get("mss_range")

    if enrich_level == "full":
        save_daily_cache(
            {
                "macro_ctx": {
                    "mss_breakdown": mss_breakdown,
                    "sources": sources,
                    "macro_summary": snapshot.get("macro_summary"),
                    "macro_signals": macro_ctx.get("macro_signals"),
                },
                "technicals": cached_technicals,
                "mss_range": snapshot.get("mss_range"),
            }
        )

    if report_type == "premarket":
        from agent_reach.daily_run.prior_close import attach_prior_close_reference

        snapshot = attach_prior_close_reference(snapshot, cfg)

    return snapshot


def _build_lite_snapshot(
    *,
    portfolio: Optional[dict[str, Any]],
    report_type: str,
    primary_code: Optional[str],
    config,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Weekend / dry runs: reuse last snapshot, refresh quotes only."""
    pf = portfolio or load_portfolio()
    base = load_last_snapshot() or {}
    snap = build_snapshot(
        pf,
        report_type=report_type,
        primary_code=primary_code,
        config=config,
        enrich_level="quotes",
        settings=settings,
    )
    if base:
        for key in ("macro_summary", "macro_signals", "mss_breakdown", "sources", "mss_range"):
            if base.get(key) is not None and snap.get(key) in (None, {}, ""):
                snap[key] = base[key]
    snap["enrich_level"] = "lite"
    snap["report_type"] = report_type
    return snap


def build_and_save(
    output: Optional[Path] = None,
    *,
    report_type: str = "intraday",
    config=None,
    portfolio: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
    enrich_level: EnrichLevel = "full",
    primary_code: Optional[str] = None,
) -> tuple[dict[str, Any], Path]:
    snap = build_snapshot(
        portfolio=portfolio,
        report_type=report_type,
        config=config,
        settings=settings,
        enrich_level=enrich_level,
        primary_code=primary_code,
    )
    out = output or (Path.home() / ".agent-reach" / "daily_run" / "last_snapshot.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return snap, out
