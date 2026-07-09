# -*- coding: utf-8 -*-
"""AI × Investment radar.

Collects "hot posts" across the platforms Agent Reach already reaches
(Twitter curated accounts + your timeline, Exa web search, RSS, Google
Trends), ranks them, and writes ONE compact markdown digest. The point is
anti-information-anxiety: a single ranked page of "what matters + why",
not a firehose.

Design notes
------------
- Pure orchestration on top of upstream tools (twitter-cli, mcporter/Exa,
  feedparser) — no scraping or API reimplementation, in line with Agent
  Reach's glue-layer philosophy.
- Every collector is isolated: a failing source logs a warning and yields
  nothing; it never aborts the run.
- Sources are overridable via ``~/.agent-reach/radar.yaml`` (auto-created
  with sensible defaults on first run).
- Insight synthesis is intentionally left to the caller: the digest ships
  a structured "raw material" section that Claude (or any LLM) turns into
  insights. ``synthesize_insights`` offers an optional Groq/OpenAI path for
  unattended/cron use.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser
import yaml
from loguru import logger

from agent_reach.config import Config

def _radar_output_dir() -> Path:
    """Output dir for digests/reports — `radar_output_dir` in config, else ~/.agent-reach/radar."""
    out = Config().get("radar_output_dir")
    return Path(out) if out else (Config.CONFIG_DIR / "radar")


RADAR_DIR = _radar_output_dir()
SOURCES_FILE = Config.CONFIG_DIR / "radar.yaml"

# Seeded for the user's focus: AI + investment. Tune in ~/.agent-reach/radar.yaml.
DEFAULT_SOURCES = {
    # X/Twitter accounts to pull recent posts from (no '@' needed).
    # Serenity (@aleabitoreddit) — "bottleneck theory" AI supply-chain analyst.
    "twitter_accounts": ["aleabitoreddit"],
    # Also pull YOUR home timeline (the people you already follow).
    # Off by default: the raw timeline is noisy (memes, off-topic virality)
    # and ranks high by views, drowning the signal. Turn on + rely on the
    # topic filter below if you want it.
    "twitter_feed": False,
    "twitter_per_account": 5,
    "twitter_feed_count": 25,
    # Relevance gate for the noisy sources (home feed, RSS, trends).
    # An item must contain one of these (case-insensitive) to pass.
    # Curated accounts and Exa queries are trusted and bypass this gate.
    "topic_keywords": [
        "ai", "a.i", "llm", "gpt", "agent", "model", "inference", "training",
        "chip", "semiconductor", "gpu", "tpu", "hbm", "dram", "nand", "wafer",
        "tsmc", "nvidia", "amd", "cuda", "cowos", "packaging", "foundry",
        "robot", "humanoid", "datacenter", "data center", "capex", "cloud",
        "funding", "raises", "raised", "series a", "series b", "series c",
        "series d", "series f", "valuation", "ipo", "vc", "venture",
        "stock", "shares", "earnings", "nasdaq", "$",
        "openai", "anthropic", "claude", "gemini", "deepseek", "meta",
    ],
    "filter_feed": True,
    "filter_rss": True,
    "filter_trends": True,
    # Standing Exa semantic searches (describe the ideal page, not keywords).
    "exa_queries": [
        "latest AI semiconductor supply chain bottleneck analysis this week",
        "notable AI agent or AI infrastructure startup funding round 2026",
        "AI datacenter capex and compute capacity news this week",
    ],
    "exa_per_query": 4,
    # RSS/Atom feeds (HN front page, ≥100 points = signal, not noise).
    "rss_feeds": [
        "https://hnrss.org/frontpage?points=100",
    ],
    "rss_per_feed": 6,
    # Google Trends daily search RSS — macro "what's the world searching"
    # pulse. Off by default (general daily trends are mostly off-topic noise
    # for an AI/investment radar). Set e.g. ["US", "TW"] to enable.
    "google_trends_geo": [],
    # Cap per section in the digest.
    "max_items_per_section": 8,
}


@dataclass
class Item:
    """One normalized piece of content from any source."""

    source: str  # e.g. "twitter:@aleabitoreddit", "exa", "rss:Hacker News"
    kind: str  # tweet | web | rss | trend
    title: str
    url: str
    text: str = ""
    author: str = ""
    score: float = 0.0  # engagement / ranking signal (higher = hotter)
    ts: Optional[str] = None  # ISO timestamp if known
    extra: dict = field(default_factory=dict)


# ── sources config ───────────────────────────────────────────────────────


def load_sources() -> dict:
    """Load radar sources, creating the file with defaults on first run."""
    if SOURCES_FILE.exists():
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # Merge so new default keys appear for existing users.
        merged = {**DEFAULT_SOURCES, **data}
        return merged
    SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SOURCES_FILE, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_SOURCES, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info(f"Created default radar sources at {SOURCES_FILE}")
    return dict(DEFAULT_SOURCES)


# ── relevance + dedup ─────────────────────────────────────────────────────


def _is_on_topic(item: Item, keywords: list[str]) -> bool:
    """True if the item text/title contains any topic keyword.

    Alphanumeric keywords match on word boundaries so short ones like "ai"
    don't fire on "m**ai**ntenance"/"av**ai**lable". Symbol keywords (e.g. "$")
    fall back to plain substring.
    """
    if not keywords:
        return True
    hay = f"{item.title} {item.text}".lower()
    for kw in keywords:
        kw = kw.lower().strip()
        if not kw:
            continue
        if kw.replace(" ", "").isalnum():
            if re.search(rf"\b{re.escape(kw)}\b", hay):
                return True
        elif kw in hay:
            return True
    return False


def _dedupe(items: list[Item]) -> list[Item]:
    """Drop duplicates by URL, then by a normalized text fingerprint."""
    seen: set[str] = set()
    out: list[Item] = []
    for it in items:
        key = it.url.strip() or re.sub(r"\W+", "", it.text.lower())[:80]
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(it)
    return out


# ── collectors (each isolated; never raises) ──────────────────────────────


def _twitter_env(config: Config) -> Optional[dict]:
    """Build env with Twitter creds from config, or None if not configured."""
    auth = config.get("twitter_auth_token")
    ct0 = config.get("twitter_ct0")
    if not (auth and ct0):
        return None
    env = os.environ.copy()
    env["TWITTER_AUTH_TOKEN"] = auth
    env["TWITTER_CT0"] = ct0
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_twitter_json(args: list[str], env: dict, timeout: int = 30) -> list[dict]:
    """Run `twitter <args> --json` and return the data list (empty on failure)."""
    twitter_bin = shutil.which("twitter")
    if not twitter_bin:
        logger.warning("twitter-cli not on PATH; skipping Twitter")
        return []
    try:
        proc = subprocess.run(
            [twitter_bin, *args, "--json"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except Exception as e:  # noqa: BLE001 - collector must never abort the run
        logger.warning(f"twitter {' '.join(args)} failed: {e}")
        return []
    out = (proc.stdout or "").strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        # twitter-cli sometimes emits YAML-ish output; fall back.
        try:
            data = yaml.safe_load(out)
        except Exception:  # noqa: BLE001
            return []
    if isinstance(data, dict):
        if not data.get("ok", True):
            logger.warning(f"twitter {' '.join(args)}: {data.get('error')}")
            return []
        return data.get("data") or []
    return data if isinstance(data, list) else []


def _tweet_to_item(t: dict, source: str) -> Optional[Item]:
    text = (t.get("text") or "").strip()
    if not text:
        return None
    author = t.get("author") or {}
    screen = author.get("screenName") or ""
    is_rt = bool(t.get("isRetweet"))
    metrics = t.get("metrics") or {}
    # Ranking signal: views dominate, fall back to a like/RT blend.
    score = float(
        metrics.get("views")
        or (metrics.get("likes", 0) * 3 + metrics.get("retweets", 0) * 5 + metrics.get("replies", 0))
    )
    tid = t.get("id")
    url = f"https://x.com/{screen}/status/{tid}" if screen and tid else ""
    return Item(
        source=source,
        kind="tweet",
        title=text.split("\n", 1)[0][:120],
        url=url,
        text=text,
        author=author.get("name") or screen,
        score=score,
        ts=t.get("createdAtISO"),
        extra={"metrics": metrics, "screenName": screen, "isRetweet": is_rt},
    )


def collect_twitter(sources: dict, config: Config) -> list[Item]:
    env = _twitter_env(config)
    if env is None:
        logger.warning("Twitter not configured (no auth_token/ct0); skipping")
        return []
    items: list[Item] = []
    per = int(sources.get("twitter_per_account", 5))
    # `user-posts` returns the account's timeline incl. retweets/amplifications.
    # Keep only the account's own original posts by default (their actual take).
    own_only = sources.get("twitter_own_posts_only", True)
    workers = int(sources.get("twitter_concurrency", 6))

    # Normalize entries to (handle, lens). Each entry is either "handle" or
    # {handle, note} — note is the "how to read" contra-lens from the KOL index.
    accounts: list[tuple[str, str]] = []
    for entry in sources.get("twitter_accounts", []):
        if isinstance(entry, dict):
            h, lens = str(entry.get("handle", "")).lstrip("@"), entry.get("note", "")
        else:
            h, lens = str(entry).lstrip("@"), ""
        if h:
            accounts.append((h, lens))

    timeout = int(sources.get("twitter_timeout", 30))
    retries = int(sources.get("twitter_retries", 1))

    def _fetch(acct: tuple[str, str]) -> list[Item]:
        h, lens = acct
        # Retry once on empty — `user-posts` intermittently times out under
        # X rate-limiting even for valid handles; a short backoff recovers it.
        rows: list[dict] = []
        for attempt in range(retries + 1):
            rows = _run_twitter_json(["user-posts", f"@{h}", "-n", str(per)], env, timeout=timeout)
            if rows:
                break
            if attempt < retries:
                time.sleep(2)
        out: list[Item] = []
        for t in rows:
            it = _tweet_to_item(t, source=f"twitter:@{h}")
            if not it:
                continue
            if own_only and (
                it.extra.get("isRetweet")
                or it.extra.get("screenName", "").lower() != h.lower()
            ):
                continue
            if lens:
                it.extra["lens"] = lens
            out.append(it)
        return out

    # Fetch accounts concurrently — `twitter` subprocess I/O releases the GIL,
    # so threads raise throughput a lot; cap concurrency to stay X-API-friendly.
    if accounts:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for res in pool.map(_fetch, accounts):
                items.extend(res)

    if sources.get("twitter_feed"):
        n = int(sources.get("twitter_feed_count", 25))
        keywords = sources.get("topic_keywords", []) if sources.get("filter_feed", True) else []
        for t in _run_twitter_json(["feed", "-n", str(n)], env):
            it = _tweet_to_item(t, source="twitter:feed")
            if it and _is_on_topic(it, keywords):
                items.append(it)
    return items


_EXA_BIN = None


def _exa_search(query: str, num: int, timeout: int = 90) -> list[Item]:
    global _EXA_BIN
    if _EXA_BIN is None:
        _EXA_BIN = shutil.which("mcporter") or ""
    if not _EXA_BIN:
        logger.warning("mcporter not on PATH; skipping Exa")
        return []
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    try:
        proc = subprocess.run(
            [_EXA_BIN, "call", "exa.web_search_exa", f"query={query}", f"numResults={num}"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Exa search failed for {query!r}: {e}")
        return []
    out = proc.stdout or ""
    # mcporter prints formatted text blocks: Title:/URL:/Published:/Author:/Highlights:
    items: list[Item] = []
    blocks = re.split(r"\n-{3,}\n", out)
    for blk in blocks:
        title_m = re.search(r"^Title:\s*(.+)$", blk, re.MULTILINE)
        url_m = re.search(r"^URL:\s*(\S+)$", blk, re.MULTILINE)
        if not (title_m and url_m):
            continue
        # First highlight line after "Highlights:" as a snippet.
        snippet = ""
        hi = re.search(r"Highlights:\s*(.+)", blk, re.DOTALL)
        if hi:
            snippet = re.sub(r"\s+", " ", hi.group(1)).strip()[:280]
        items.append(
            Item(
                source="exa",
                kind="web",
                title=title_m.group(1).strip(),
                url=url_m.group(1).strip(),
                text=snippet,
                score=0.0,
                extra={"query": query},
            )
        )
    return items


def collect_exa(sources: dict) -> list[Item]:
    items: list[Item] = []
    num = int(sources.get("exa_per_query", 4))
    for q in sources.get("exa_queries", []):
        items.extend(_exa_search(q, num))
    return items


def collect_rss(sources: dict) -> list[Item]:
    items: list[Item] = []
    per = int(sources.get("rss_per_feed", 6))
    for url in sources.get("rss_feeds", []):
        try:
            feed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"RSS parse failed for {url}: {e}")
            continue
        feed_title = (feed.feed.get("title") if feed.feed else None) or url
        for e in feed.entries[:per]:
            items.append(
                Item(
                    source=f"rss:{feed_title}",
                    kind="rss",
                    title=(e.get("title") or "").strip(),
                    url=e.get("link") or "",
                    text=re.sub(r"<[^>]+>", "", e.get("summary", ""))[:280],
                    ts=e.get("published"),
                )
            )
    return items


def collect_google_trends(sources: dict) -> list[Item]:
    items: list[Item] = []
    for geo in sources.get("google_trends_geo", []):
        url = f"https://trends.google.com/trending/rss?geo={geo}"
        try:
            feed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Google Trends fetch failed for {geo}: {e}")
            continue
        for e in feed.entries[:10]:
            traffic = ""
            # ht:approx_traffic shows up under various keys depending on parser.
            for k in ("ht_approx_traffic", "approx_traffic"):
                if e.get(k):
                    traffic = e.get(k)
                    break
            items.append(
                Item(
                    source=f"google-trends:{geo}",
                    kind="trend",
                    title=(e.get("title") or "").strip(),
                    url=e.get("link") or "",
                    text=traffic,
                    extra={"geo": geo, "traffic": traffic},
                )
            )
    return items


# ── orchestration + digest ────────────────────────────────────────────────


def collect_all(sources: dict, config: Config) -> dict[str, list[Item]]:
    """Run every collector, grouped by kind. Failures degrade gracefully.

    Trusted sources (curated Twitter accounts, Exa queries) are kept as-is.
    Noisy sources (RSS, Google Trends) are passed through the topic gate when
    their ``filter_*`` flag is on. Every group is de-duplicated.
    """
    kw = sources.get("topic_keywords", [])
    rss = collect_rss(sources)
    if sources.get("filter_rss", True):
        rss = [i for i in rss if _is_on_topic(i, kw)]
    trends = collect_google_trends(sources)
    if sources.get("filter_trends", True):
        trends = [i for i in trends if _is_on_topic(i, kw)]
    return {
        "tweet": _dedupe(collect_twitter(sources, config)),
        "web": _dedupe(collect_exa(sources)),
        "rss": _dedupe(rss),
        "trend": _dedupe(trends),
    }


def _fmt_metrics(m: dict) -> str:
    if not m:
        return ""
    bits = []
    if m.get("views"):
        bits.append(f"{int(m['views']):,} views")
    if m.get("likes"):
        bits.append(f"❤ {int(m['likes']):,}")
    if m.get("retweets"):
        bits.append(f"🔁 {int(m['retweets']):,}")
    return " · ".join(bits)


def build_digest(grouped: dict[str, list[Item]], sources: dict, when: datetime) -> str:
    cap = int(sources.get("max_items_per_section", 8))
    lines: list[str] = []
    lines.append(f"# 🛰️ AI × 投资 雷达 — {when:%Y-%m-%d %H:%M}")
    lines.append("")
    counts = {k: len(v) for k, v in grouped.items()}
    total = sum(counts.values())
    lines.append(
        f"> 共 {total} 条 · 推文 {counts.get('tweet',0)} · 网文 {counts.get('web',0)} "
        f"· RSS {counts.get('rss',0)} · 趋势 {counts.get('trend',0)}"
    )
    lines.append("")
    lines.append("## 🧠 今日洞察")
    lines.append("")
    lines.append("<!-- 由 Claude / LLM 阅读下方原料后填写：3-5 条「真正重要 + 为什么」，过滤噪声 -->")
    lines.append("_（待综合）_")
    lines.append("")

    # Twitter — ranked by engagement.
    tweets = sorted(grouped.get("tweet", []), key=lambda i: i.score, reverse=True)[:cap]
    if tweets:
        lines.append("## 🐦 Twitter / X（按热度）")
        lines.append("")
        for it in tweets:
            who = f"**{it.author}**" if it.author else it.source
            metric = _fmt_metrics(it.extra.get("metrics", {}))
            head = f"- {who}"
            if metric:
                head += f" — {metric}"
            lines.append(head)
            lens = it.extra.get("lens")
            if lens:
                lines.append(f"  - 🔎 _怎么读: {lens}_")
            body = it.text.strip().replace("\n", " ")
            lines.append(f"  - {body[:280]}{'…' if len(body) > 280 else ''}")
            if it.url:
                lines.append(f"  - {it.url}")
            lines.append("")

    # Exa web.
    web = grouped.get("web", [])[:cap]
    if web:
        lines.append("## 🔍 全网（Exa 语义搜索）")
        lines.append("")
        for it in web:
            lines.append(f"- [{it.title}]({it.url})")
            if it.text:
                lines.append(f"  - {it.text}")
        lines.append("")

    # RSS.
    rss = grouped.get("rss", [])[:cap]
    if rss:
        lines.append("## 📡 RSS（精选源）")
        lines.append("")
        for it in rss:
            lines.append(f"- [{it.title}]({it.url}) _({it.source.split(':',1)[-1]})_")
        lines.append("")

    # Trends — sidebar.
    trends = grouped.get("trend", [])[:10]
    if trends:
        lines.append("## 📈 Google Trends（宏观脉搏 · 泛热搜，仅供参考）")
        lines.append("")
        labels = ", ".join(t.title for t in trends if t.title)
        lines.append(f"> {labels}")
        lines.append("")

    return "\n".join(lines)


def run_radar(config: Optional[Config] = None, when: Optional[datetime] = None) -> tuple[Path, dict]:
    """Collect, build the digest, write it, and return (path, grouped_items)."""
    config = config or Config()
    when = when or datetime.now(timezone.utc).astimezone()
    sources = load_sources()
    grouped = collect_all(sources, config)
    digest = build_digest(grouped, sources, when)
    RADAR_DIR.mkdir(parents=True, exist_ok=True)
    out = RADAR_DIR / f"{when:%Y-%m-%d-%H%M}.md"
    out.write_text(digest, encoding="utf-8")
    # Also keep a stable "latest" pointer for easy reading/cron.
    (RADAR_DIR / "latest.md").write_text(digest, encoding="utf-8")
    return out, grouped
