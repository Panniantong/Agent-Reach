# -*- coding: utf-8 -*-
"""Finviz Elite collector — market news + sector-rotation signals.

Self-contained CSV export calls against elite.finviz.com (same endpoints the
user's Quant exporter uses); no cross-repo imports. The auth token resolves
from ``FINVIZ_AUTH_TOKEN`` env / ``finviz_auth_token`` config, then from
``FINVIZ_AUTH_TOKEN=`` lines in the env files listed by
``finviz_env_paths`` (radar.yaml/config). The token is never logged or
echoed. Collector never raises.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Optional

import requests
from loguru import logger

from agent_reach.config import Config
from agent_reach.radar import _FEED_UA, Item, _is_on_topic

FINVIZ_BASE = "https://elite.finviz.com"
# Local convenience fallback (the user's Quant repo); override or clear via
# finviz_env_paths in radar.yaml / config.
DEFAULT_ENV_PATHS = ["D:/DOT/Quant/.env", "D:/DOT/Quant/finviz/.env"]


def _finviz_token(config: Optional[Config] = None, sources: Optional[dict] = None) -> str:
    """Resolve the Elite token: env/config key → env-file lines. Never logged."""
    config = config or Config()
    tok = config.get("finviz_auth_token")  # Config.get also checks FINVIZ_AUTH_TOKEN env
    if tok:
        return str(tok).strip()
    paths = (sources or {}).get("finviz_env_paths") or config.get("finviz_env_paths") or DEFAULT_ENV_PATHS
    for p in paths:
        try:
            text = Path(p).read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("FINVIZ_AUTH_TOKEN="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    return ""


def _fetch_csv(path: str, params: dict, token: str, timeout: int = 30) -> list[dict]:
    resp = requests.get(
        f"{FINVIZ_BASE}/{path}",
        params={**params, "auth": token},
        timeout=timeout,
        headers={"User-Agent": _FEED_UA},
    )
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _norm(row: dict) -> dict:
    return {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}


def collect_finviz(sources: dict, config: Optional[Config] = None) -> list[Item]:
    """Market news (topic-gated) + sector moves beyond the alert threshold."""
    cfg = sources.get("finviz") or {}
    token = _finviz_token(config, sources)
    if not token:
        logger.warning(
            "Finviz token not found (FINVIZ_AUTH_TOKEN / finviz_auth_token / finviz_env_paths); skipping"
        )
        return []
    items: list[Item] = []

    if cfg.get("news", True):
        try:
            rows = _fetch_csv("export/news", {"v": "1"}, token)
        except Exception as e:  # noqa: BLE001 - collector must never abort the run
            logger.warning(f"finviz news fetch failed: {e}")
            rows = []
        kw = sources.get("topic_keywords", []) if cfg.get("filter_news", True) else []
        top_n = int(cfg.get("news_top_n", 12))
        kept = 0
        for raw in rows:
            row = _norm(raw)
            title = row.get("title") or ""
            if not title:
                continue
            it = Item(
                source="finviz:news",
                kind="market",
                title=title,
                url=row.get("url") or row.get("link") or "",
                text=row.get("source") or "",
                ts=row.get("date"),
                extra={"type": "news", "category": row.get("category", "")},
            )
            if _is_on_topic(it, kw):
                items.append(it)
                kept += 1
            if kept >= top_n:
                break

    if cfg.get("groups", True):
        try:
            rows = _fetch_csv("export/groups", {"g": "sector", "v": "152"}, token)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"finviz groups fetch failed: {e}")
            rows = []
        alert = float(cfg.get("sector_alert_pct", 1.5))
        for raw in rows:
            row = _norm(raw)
            name = row.get("name") or ""
            try:
                chg = float((row.get("change") or "").replace("%", ""))
            except ValueError:
                continue
            if name and abs(chg) >= alert:
                arrow = "▲" if chg > 0 else "▼"
                items.append(Item(
                    source="finviz:sector",
                    kind="market",
                    title=f"{arrow} {name} 板塊單日 {chg:+.2f}%",
                    url=f"{FINVIZ_BASE}/groups.ashx",
                    score=abs(chg),
                    extra={"type": "sector", "sector": name, "change": chg},
                ))
    return items
