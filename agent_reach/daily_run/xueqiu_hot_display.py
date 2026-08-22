# -*- coding: utf-8
"""Render Xueqiu hot posts / hot stocks for daily-run morning push."""

from __future__ import annotations

from typing import Any, Optional


def normalize_xueqiu_symbol(symbol: str) -> str:
    """Normalize SH688008 / 688008 → 6-digit A-share code."""
    text = str(symbol or "").strip().upper()
    for prefix in ("SH", "SZ", "BJ"):
        if text.startswith(prefix):
            return text[len(prefix) :].zfill(6)[-6:]
    if text.isdigit():
        return text.zfill(6)[-6:]
    return text


def _portfolio_rows(portfolio: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map normalized code → {code, name, role}. Holdings beat watchlist."""
    out: dict[str, dict[str, Any]] = {}
    for row in portfolio.get("watchlist") or []:
        if not isinstance(row, dict):
            continue
        code = normalize_xueqiu_symbol(str(row.get("code") or ""))
        if not code or len(code) != 6:
            continue
        out[code] = {
            "code": code,
            "name": str(row.get("name") or code),
            "role": "watchlist",
        }
    for row in portfolio.get("holdings") or []:
        if not isinstance(row, dict):
            continue
        code = normalize_xueqiu_symbol(str(row.get("code") or ""))
        if not code or len(code) != 6:
            continue
        out[code] = {
            "code": code,
            "name": str(row.get("name") or code),
            "role": "holding",
        }
    return out


def match_portfolio_hot_stocks(
    portfolio: dict[str, Any],
    hot_stocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find portfolio/watchlist symbols appearing on Xueqiu hot-stock boards."""
    if not portfolio or not hot_stocks:
        return []
    rows = _portfolio_rows(portfolio)
    if not rows:
        return []

    matches: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for stock in hot_stocks:
        code = normalize_xueqiu_symbol(str(stock.get("symbol") or ""))
        pf_row = rows.get(code)
        if not pf_row:
            continue
        board = str(stock.get("board") or "人气榜")
        key = (code, board)
        if key in seen:
            continue
        seen.add(key)
        matches.append(
            {
                **pf_row,
                "rank": stock.get("rank"),
                "board": board,
                "board_type": stock.get("board_type"),
                "symbol": stock.get("symbol") or code,
                "current": stock.get("current"),
                "percent": stock.get("percent"),
            }
        )
    matches.sort(
        key=lambda item: (
            0 if item.get("role") == "holding" else 1,
            int(item.get("board_type") or 10),
            int(item.get("rank") or 999),
        )
    )
    return matches


def match_portfolio_hot_posts(
    portfolio: dict[str, Any],
    posts: list[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Find hot posts whose title/text hits portfolio/watchlist keywords."""
    if not portfolio or not posts:
        return []
    from agent_reach.daily_run.hot_news_collector import portfolio_keywords

    keywords = portfolio_keywords(portfolio, settings)
    if not keywords:
        return []

    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for post in posts:
        if not isinstance(post, dict):
            continue
        title = str(post.get("title") or "").strip()
        text = str(post.get("text") or "").strip()
        blob = f"{title} {text}"
        if not blob.strip():
            continue
        matched = [kw for kw in keywords if kw and kw in blob]
        if not matched:
            continue
        key = str(post.get("url") or post.get("id") or title[:48])
        if key in seen:
            continue
        seen.add(key)
        matches.append({**post, "matched_keywords": matched[:3]})
    return matches


def apply_portfolio_hot_stock_matches(
    signals: dict[str, Any],
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Attach portfolio_hot_stocks matches to macro_signals when enabled."""
    from agent_reach.daily_run.settings import effective_settings, load_settings

    cfg = effective_settings(settings or load_settings())
    collector_cfg = cfg.get("macro_collector") or {}
    if collector_cfg.get("match_portfolio_hot_stocks", True) is False:
        return signals

    boards: list[dict[str, Any]] = []
    for stock in signals.get("hot_stocks") or []:
        if isinstance(stock, dict):
            boards.append({**stock, "board": stock.get("board") or "人气榜", "board_type": 10})
    for stock in signals.get("hot_watch_stocks") or []:
        if isinstance(stock, dict):
            boards.append({**stock, "board": stock.get("board") or "关注榜", "board_type": 12})

    matches = match_portfolio_hot_stocks(portfolio, boards)
    if matches:
        signals["portfolio_hot_stocks"] = matches
    else:
        signals.pop("portfolio_hot_stocks", None)
    return signals


def apply_portfolio_hot_post_matches(
    signals: dict[str, Any],
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Attach portfolio_hot_posts keyword matches to macro_signals when enabled."""
    from agent_reach.daily_run.settings import effective_settings, load_settings

    cfg = effective_settings(settings or load_settings())
    collector_cfg = cfg.get("macro_collector") or {}
    if collector_cfg.get("match_portfolio_hot_posts", True) is False:
        return signals

    posts = [p for p in (signals.get("sentiment_posts") or []) if isinstance(p, dict)]
    matches = match_portfolio_hot_posts(portfolio, posts, settings=cfg)
    if matches:
        signals["portfolio_hot_posts"] = matches
    else:
        signals.pop("portfolio_hot_posts", None)
    return signals


def enrich_portfolio_xueqiu_matches(
    signals: dict[str, Any],
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Apply hot-stock and hot-post portfolio overlap enrichment."""
    apply_portfolio_hot_stock_matches(signals, portfolio, settings=settings)
    apply_portfolio_hot_post_matches(signals, portfolio, settings=settings)
    return signals


def portfolio_hot_post_summary(
    macro_signals: Optional[dict[str, Any]],
    *,
    limit: int = 2,
) -> str:
    """One-line hot-post keyword overlap summary for narrative cards."""
    matches = (macro_signals or {}).get("portfolio_hot_posts") or []
    if not matches:
        return ""
    parts: list[str] = []
    for item in matches[:limit]:
        title = str(item.get("title") or (item.get("text") or "")[:24]).strip() or "—"
        kws = item.get("matched_keywords") or []
        kw_s = f"（{','.join(str(k) for k in kws[:2])}）" if kws else ""
        parts.append(f"{title}{kw_s}")
    return "热帖命中：" + " · ".join(parts)


def _portfolio_hot_stock_match_key(match: dict[str, Any]) -> tuple[str, str]:
    code = normalize_xueqiu_symbol(str(match.get("code") or match.get("symbol") or ""))
    board = str(match.get("board") or "热股")
    return (code, board)


def _intraday_hot_stock_history_path() -> "Path":
    from pathlib import Path

    return Path.home() / ".agent-reach" / "daily_run" / "cache" / "xueqiu_intraday_hot_history.json"


def apply_intraday_hot_stock_delta(
    signals: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Mark portfolio hot-stock matches newly seen since the previous intraday scan."""
    import json

    from agent_reach.daily_run.settings import effective_settings, load_settings
    from agent_reach.daily_run.trade_calendar import today_shanghai

    cfg = effective_settings(settings or load_settings())
    collector_cfg = cfg.get("macro_collector") or {}
    if collector_cfg.get("intraday_hot_stock_delta_enabled", True) is False:
        signals.pop("portfolio_hot_stocks_new", None)
        return signals

    current = [m for m in (signals.get("portfolio_hot_stocks") or []) if isinstance(m, dict)]
    current_keys = {_portfolio_hot_stock_match_key(m) for m in current if _portfolio_hot_stock_match_key(m)[0]}

    today = today_shanghai().isoformat()
    path = _intraday_hot_stock_history_path()
    history: dict[str, Any] = {"date": today, "match_keys": []}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and loaded.get("date") == today:
                history = loaded
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    prev_keys = {
        (str(pair[0]), str(pair[1]))
        for pair in (history.get("match_keys") or [])
        if isinstance(pair, (list, tuple)) and len(pair) == 2
    }
    new_keys = current_keys - prev_keys
    new_matches = [m for m in current if _portfolio_hot_stock_match_key(m) in new_keys]
    if new_matches:
        signals["portfolio_hot_stocks_new"] = new_matches
    else:
        signals.pop("portfolio_hot_stocks_new", None)

    history["date"] = today
    history["match_keys"] = [list(key) for key in sorted(current_keys)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return signals


def portfolio_hot_stocks_new_summary(
    macro_signals: Optional[dict[str, Any]],
    *,
    limit: int = 3,
) -> str:
    """One-line summary for newly appeared hot-board matches."""
    matches = (macro_signals or {}).get("portfolio_hot_stocks_new") or []
    if not matches:
        return ""
    parts: list[str] = []
    for item in matches[:limit]:
        name = str(item.get("name") or item.get("code") or "—")
        rank = item.get("rank")
        board = str(item.get("board") or "热股")
        role = "持仓" if item.get("role") == "holding" else "观察池"
        rank_s = f"#{rank}" if rank is not None else ""
        pct = item.get("percent")
        pct_s = f" {float(pct):+.1f}%" if pct is not None else ""
        parts.append(f"{name}({role}·新登{board}{rank_s}{pct_s})")
    return "热股新上榜：" + " · ".join(parts)


def portfolio_hot_stock_summary(
    macro_signals: Optional[dict[str, Any]],
    *,
    limit: int = 3,
) -> str:
    """One-line overlap summary for narrative cards."""
    matches = (macro_signals or {}).get("portfolio_hot_stocks") or []
    if not matches:
        return ""
    parts: list[str] = []
    for item in matches[:limit]:
        name = str(item.get("name") or item.get("code") or "—")
        rank = item.get("rank")
        board = str(item.get("board") or "热股")
        role = "持仓" if item.get("role") == "holding" else "观察池"
        pct = item.get("percent")
        rank_s = f"#{rank}" if rank is not None else ""
        pct_s = f" {float(pct):+.1f}%" if pct is not None else ""
        parts.append(f"{name}({role}·{board}{rank_s}{pct_s})")
    return "热股命中：" + " · ".join(parts)


def render_portfolio_hot_post_overlap_markdown(
    matches: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> str:
    if not matches:
        return ""
    lines = ["**📌 持仓相关热帖**", ""]
    for idx, item in enumerate(matches[:limit], start=1):
        title = str(item.get("title") or (item.get("text") or "")[:48]).strip() or "—"
        author = str(item.get("author") or "—").strip()
        kws = item.get("matched_keywords") or []
        kw_s = f" · 命中 {','.join(str(k) for k in kws[:3])}" if kws else ""
        likes = item.get("likes")
        like_s = f" · 👍{likes}" if likes is not None else ""
        url = str(item.get("url") or "").strip()
        row = f"{idx}. {title}（{author}{like_s}）{kw_s}"
        if url:
            row += f"\n   {url}"
        lines.append(row)
    return "\n".join(lines).strip()


def render_portfolio_hot_stock_overlap_markdown(
    matches: list[dict[str, Any]],
) -> str:
    if not matches:
        return ""
    lines = ["**⚡ 持仓/观察池 × 雪球热股**", ""]
    for item in matches:
        name = str(item.get("name") or item.get("code") or "—")
        code = str(item.get("code") or "—")
        role = "持仓" if item.get("role") == "holding" else "观察池"
        board = str(item.get("board") or "热股")
        rank = item.get("rank")
        rank_s = f"#{rank}" if rank is not None else "—"
        pct = item.get("percent")
        pct_s = f" · {float(pct):+.2f}%" if pct is not None else ""
        current = item.get("current")
        price_s = f" · ¥{current}" if current is not None else ""
        lines.append(f"- **{name}** ({code}) {role} · {board} {rank_s}{price_s}{pct_s}")
    return "\n".join(lines).strip()


def xueqiu_sentiment_source_summary(
    posts: list[dict[str, Any]],
    *,
    max_titles: int = 2,
) -> str:
    """One-line summary for sources.sentiment / evidence chain."""
    if not posts:
        return ""
    parts = [
        str(p.get("title") or (p.get("text") or "")[:30]).strip()
        for p in posts[:max_titles]
        if (p.get("title") or p.get("text"))
    ]
    if not parts:
        return ""
    return "雪球热点：" + " | ".join(parts)


def render_intraday_xueqiu_alert_markdown(
    macro_signals: Optional[dict[str, Any]],
) -> str:
    """Compact cross alert block for intraday scan Feishu cards."""
    if not macro_signals:
        return ""
    new_summary = portfolio_hot_stocks_new_summary(macro_signals)
    stock_summary = portfolio_hot_stock_summary(macro_signals, limit=5)
    post_summary = portfolio_hot_post_summary(macro_signals, limit=2)
    exa_summary = xueqiu_exa_research_summary(macro_signals)
    if not new_summary and not stock_summary and not post_summary and not exa_summary:
        return ""
    lines = ["**⚡ 雪球交叉提醒**", ""]
    if new_summary:
        lines.append(f"- **{new_summary}**")
    if exa_summary:
        lines.append(f"- {exa_summary}")
    if stock_summary:
        lines.append(f"- {stock_summary}")
    if post_summary:
        lines.append(f"- {post_summary}")
    return "\n".join(lines).strip()


def portfolio_symbol_sentiment_summary(
    macro_signals: Optional[dict[str, Any]],
    *,
    limit: int = 2,
) -> str:
    rows = (macro_signals or {}).get("portfolio_symbol_sentiment") or []
    if not rows:
        return ""
    parts: list[str] = []
    for row in rows[:limit]:
        name = str(row.get("name") or row.get("code") or "—")
        posts = row.get("posts") or []
        if not posts:
            continue
        top = posts[0]
        title = str(top.get("title") or (top.get("text") or "")[:20]).strip() or "讨论"
        parts.append(f"{name}:{title}")
    if not parts:
        return ""
    return "个股舆情：" + " · ".join(parts)


def xueqiu_exa_research_summary(
    macro_signals: Optional[dict[str, Any]],
    *,
    limit: int = 1,
) -> str:
    rows = (macro_signals or {}).get("xueqiu_exa_research") or []
    ok = [r for r in rows if r.get("success") and (r.get("summary") or "").strip()]
    if not ok:
        return ""
    parts: list[str] = []
    for row in ok[:limit]:
        label = str(row.get("label") or "Exa")
        summary = str(row.get("summary") or "").strip().splitlines()[0][:72]
        parts.append(f"{label} {summary}")
    return "Exa：" + " | ".join(parts)


def render_portfolio_symbol_sentiment_markdown(
    rows: list[dict[str, Any]],
    *,
    post_limit: int = 2,
) -> str:
    if not rows:
        return ""
    lines = ["**💬 个股雪球讨论**", ""]
    for row in rows:
        name = str(row.get("name") or row.get("code") or "—")
        code = str(row.get("code") or "—")
        role = "持仓" if row.get("role") == "holding" else "观察池"
        lines.append(f"**{name}** ({code}) {role}")
        for post in (row.get("posts") or [])[:post_limit]:
            title = str(post.get("title") or (post.get("text") or "")[:48]).strip() or "—"
            author = str(post.get("author") or "—").strip()
            url = str(post.get("url") or "").strip()
            row_s = f"- {title}（{author}）"
            if url:
                row_s += f"\n  {url}"
            lines.append(row_s)
        lines.append("")
    return "\n".join(lines).strip()


def render_xueqiu_exa_research_markdown(
    results: list[dict[str, Any]],
) -> str:
    if not results:
        return ""
    lines = ["**🔍 雪球交叉 Exa 调研**", ""]
    for row in results:
        status = "✅" if row.get("success") else "⚠️"
        trigger = str(row.get("trigger") or "").strip()
        trigger_s = f"（{trigger}）" if trigger else ""
        lines.append(f"**{status} {row.get('label', '调研')}**{trigger_s}")
        if row.get("summary"):
            lines.append(str(row["summary"])[:400])
        for hit in (row.get("hits") or [])[:2]:
            title = hit.get("title") or "—"
            url = hit.get("url") or ""
            if url:
                lines.append(f"- [{str(title)[:60]}]({url})")
            else:
                lines.append(f"- {str(title)[:80]}")
        lines.append("")
    return "\n".join(lines).strip()


def render_xueqiu_hot_markdown(
    macro_signals: Optional[dict[str, Any]],
    *,
    post_limit: int = 5,
    stock_limit: int = 10,
) -> str:
    """Markdown block for Feishu morning card: hot posts + hot stocks."""
    if not macro_signals:
        return ""
    posts = macro_signals.get("sentiment_posts") or []
    stocks = macro_signals.get("hot_stocks") or []
    stock_matches = macro_signals.get("portfolio_hot_stocks") or []
    post_matches = macro_signals.get("portfolio_hot_posts") or []
    symbol_rows = macro_signals.get("portfolio_symbol_sentiment") or []
    exa_rows = macro_signals.get("xueqiu_exa_research") or []
    search_rows = macro_signals.get("xueqiu_stock_search") or []
    if (
        not posts
        and not stocks
        and not stock_matches
        and not post_matches
        and not symbol_rows
        and not exa_rows
        and not search_rows
    ):
        return ""

    lines = ["**🔥 雪球热门**", ""]
    overlap_md = render_portfolio_hot_stock_overlap_markdown(stock_matches)
    if overlap_md:
        lines.extend(overlap_md.splitlines())
        lines.append("")
    post_overlap_md = render_portfolio_hot_post_overlap_markdown(post_matches)
    if post_overlap_md:
        lines.extend(post_overlap_md.splitlines())
        lines.append("")
    symbol_md = render_portfolio_symbol_sentiment_markdown(symbol_rows)
    if symbol_md:
        lines.extend(symbol_md.splitlines())
        lines.append("")
    exa_md = render_xueqiu_exa_research_markdown(exa_rows)
    if exa_md:
        lines.extend(exa_md.splitlines())
        lines.append("")
    from agent_reach.daily_run.xueqiu_stock_search import render_xueqiu_stock_search_markdown

    search_md = render_xueqiu_stock_search_markdown(search_rows)
    if search_md:
        lines.extend(search_md.splitlines())
        lines.append("")

    if posts:
        lines.append(f"**热帖 Top{min(len(posts), post_limit)}**")
        for idx, post in enumerate(posts[:post_limit], start=1):
            title = str(post.get("title") or (post.get("text") or "")[:48]).strip() or "—"
            author = str(post.get("author") or "—").strip()
            likes = post.get("likes")
            like_s = f" · 👍{likes}" if likes is not None else ""
            url = str(post.get("url") or "").strip()
            row = f"{idx}. {title}（{author}{like_s}）"
            if url:
                row += f"\n   {url}"
            lines.append(row)
        lines.append("")

    if stocks:
        lines.append(f"**热股 Top{min(len(stocks), stock_limit)}（人气榜）**")
        for stock in stocks[:stock_limit]:
            rank = stock.get("rank")
            name = str(stock.get("name") or "—").strip()
            symbol = str(stock.get("symbol") or "").strip()
            current = stock.get("current")
            percent = stock.get("percent")
            sym_s = f" {symbol}" if symbol else ""
            price_s = f" ¥{current}" if current is not None else ""
            pct_s = f" {float(percent):+.2f}%" if percent is not None else ""
            prefix = f"{rank}. " if rank is not None else "- "
            lines.append(f"{prefix}{name}{sym_s}{price_s}{pct_s}")

    return "\n".join(lines).strip()


def xueqiu_hot_context_summary(
    macro_signals: Optional[dict[str, Any]],
    *,
    post_limit: int = 3,
    stock_limit: int = 3,
) -> str:
    """Compact one-liner for morning/weekly narrative context."""
    if not macro_signals:
        return ""
    overlap = portfolio_hot_stock_summary(macro_signals)
    if overlap:
        return overlap
    post_overlap = portfolio_hot_post_summary(macro_signals)
    if post_overlap:
        return post_overlap
    from agent_reach.daily_run.xueqiu_stock_search import xueqiu_stock_search_summary

    search_summary = xueqiu_stock_search_summary(macro_signals)
    if search_summary:
        return search_summary
    exa_summary = xueqiu_exa_research_summary(macro_signals)
    if exa_summary:
        return exa_summary
    symbol_summary = portfolio_symbol_sentiment_summary(macro_signals)
    if symbol_summary:
        return symbol_summary

    parts: list[str] = []
    posts = macro_signals.get("sentiment_posts") or []
    for post in posts[:post_limit]:
        title = str(post.get("title") or (post.get("text") or "")[:24]).strip()
        if title:
            parts.append(title)
    stocks = macro_signals.get("hot_stocks") or []
    for stock in stocks[:stock_limit]:
        name = str(stock.get("name") or stock.get("symbol") or "").strip()
        pct = stock.get("percent")
        if name:
            if pct is not None:
                parts.append(f"{name}{float(pct):+.1f}%")
            else:
                parts.append(name)
    if not parts:
        return ""
    return "雪球：" + " | ".join(parts)


def sync_xueqiu_sentiment_source(
    sources: dict[str, Any],
    macro_signals: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Prefer live Xueqiu posts over portfolio sentiment override."""
    out = dict(sources or {})
    posts = (macro_signals or {}).get("sentiment_posts") or []
    summary = xueqiu_sentiment_source_summary(posts)
    if not summary:
        return out
    out["sentiment"] = {
        "summary": summary,
        "backend": "xueqiu",
        "post_count": len(posts),
    }
    overlap = portfolio_hot_stock_summary(macro_signals)
    if overlap:
        out["sentiment"]["portfolio_hot_stocks"] = overlap
    return out
