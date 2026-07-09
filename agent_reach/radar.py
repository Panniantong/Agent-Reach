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
    # ── 大神 roster ───────────────────────────────────────────────────────
    # Category → people. Each entry: handle (X, no '@') and/or rss, plus a
    # "lens" — how to READ this voice (contra-bias, what to trust/discount).
    # Entries without a handle contribute only their RSS feed. `arxiv_names`
    # feeds the arXiv author boost. Tune freely in ~/.agent-reach/radar.yaml.
    "gurus": {
        # 深度學習先驅（Godfathers of AI）
        "godfathers": [
            {"handle": "geoffreyhinton", "name": "Geoffrey Hinton",
             "lens": "2023 後轉向風險警示；看方向與論據，不看情緒",
             "arxiv_names": ["Geoffrey Hinton", "Geoffrey E. Hinton"]},
            {"handle": "ylecun", "name": "Yann LeCun",
             "lens": "對 LLM 路線長期唱衰，當反向校準器；世界模型主張看論據",
             "arxiv_names": ["Yann LeCun"]},
            {"name": "Yoshua Bengio", "rss": "https://yoshuabengio.org/feed/",
             "lens": "治理與風險視角，與 Hinton 立場接近",
             "arxiv_names": ["Yoshua Bengio"]},
        ],
        # 產業推動者
        "industry_leaders": [
            {"handle": "sama", "name": "Sam Altman",
             "lens": "每句都是融資/敘事管理；過濾行銷，只留產品與算力事實"},
            {"name": "Jensen Huang / NVIDIA", "rss": "https://blogs.nvidia.com/feed/",
             "lens": "算力瓶頸第一手；出貨與路線圖是事實，TAM 敘事打折"},
            {"handle": "demishassabis", "name": "Demis Hassabis",
             "lens": "科學向 AI 風向球（AlphaFold 系）；發言少而重"},
            {"name": "Dario Amodei / Anthropic",
             "lens": "安全敘事與 scaling 判斷；文章長但信號密度高（官方無 RSS，自行補源）"},
            {"handle": "karpathy", "name": "Andrej Karpathy",
             "lens": "2026-05 加入 Anthropic pre-training；教學型信號密度最高，本專案方法論主源",
             "arxiv_names": ["Andrej Karpathy"]},
        ],
        # 研究派
        "research": [
            {"handle": "ilyasut", "name": "Ilya Sutskever",
             "lens": "少而精；每次公開發言都是方向性信號",
             "arxiv_names": ["Ilya Sutskever"]},
            {"handle": "_jasonwei", "name": "Jason Wei",
             "lens": "scaling 與湧現能力路線的內部視角",
             "arxiv_names": ["Jason Wei"]},
            {"handle": "tri_dao", "name": "Tri Dao",
             "lens": "注意力/核函數效率的硬核信號（FlashAttention 系）",
             "arxiv_names": ["Tri Dao"]},
            {"handle": "polynoamial", "name": "Noam Brown",
             "lens": "推理/搜索路線（test-time compute）風向",
             "arxiv_names": ["Noam Brown"]},
        ],
        # 工程開源派
        "engineering_oss": [
            {"handle": "ggerganov", "name": "Georgi Gerganov",
             "lens": "端側/量化推理實戰（llama.cpp）；代碼動向即信號"},
            {"handle": "simonw", "name": "Simon Willison",
             "rss": "https://simonwillison.net/atom/everything/",
             "lens": "工具鏈與 prompt 工程實測派；結論常可直接復現"},
            {"handle": "jeremyphoward", "name": "Jeremy Howard",
             "lens": "教育+工程視角，對過度炒作免疫"},
        ],
        # 產業/供應鏈分析派
        "industry_supply": [
            {"handle": "dylan522p", "name": "Dylan Patel",
             "rss": "https://semianalysis.com/feed/",
             "lens": "供應鏈數字可信；個股結論自帶倉位，需折價"},
            {"name": "TrendForce", "rss": "https://www.trendforce.com/news/feed/",
             "lens": "報價與產能數據為主，觀點少"},
        ],
        # 教育/資料派
        "education_data": [
            {"handle": "AndrewYNg", "name": "Andrew Ng",
             "lens": "應用落地與人才面風向；對 AGI 敘事保守"},
            {"handle": "drfeifei", "name": "Fei-Fei Li",
             "lens": "資料集與空間智能（World Labs）視角"},
        ],
        # 長文/訪談/影響者
        "longform_voices": [
            {"handle": "dwarkesh_sp", "name": "Dwarkesh Patel",
             "lens": "深度訪談索引；嘉賓觀點看原文"},
            {"handle": "gwern", "name": "Gwern",
             "lens": "長文考據派；引用密度高，可溯源"},
            {"handle": "lilianweng", "name": "Lilian Weng",
             "rss": "https://lilianweng.github.io/index.xml",
             "lens": "技術綜述金標準；更新慢但每篇必讀"},
            {"handle": "lexfridman", "name": "Lex Fridman",
             "lens": "訪談索引用，非觀點源"},
            {"handle": "kaifulee", "name": "Kai-Fu Lee",
             "lens": "華語圈風向與中國市場視角"},
        ],
        # 華語/中國圈（公司級信號源）
        "cn_ecosystem": [
            {"name": "Qwen (Alibaba)", "rss": "https://qwenlm.github.io/blog/index.xml",
             "lens": "開源模型動作看事實：權重/benchmark/授權條款"},
            {"handle": "deepseek_ai", "name": "DeepSeek",
             "lens": "論文與開源動作看事實，效率敘事可信度高"},
            {"handle": "Zai_org", "name": "智譜 Z.ai",
             "lens": "中國 2B 模型商業化風向"},
        ],
    },
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
    # ── arXiv 論文雷達（tier 1 = 摘要掃描；tier 2 = top-N 全文深讀）───────
    "arxiv_categories": ["cs.AI", "cs.LG", "cs.CL", "cs.DC", "cs.AR"],
    "arxiv_max_results": 100,
    "arxiv_top_n": 8,  # tier 1: 進 digest 的篇數
    "arxiv_deep_dive_n": 4,  # tier 2: 全文蒸餾篇數
    # Weighted keywords — the scorer is the relevance gate (title hits ×2).
    "arxiv_keywords": {
        "kv cache": 3, "speculative decoding": 3, "hbm": 3,
        "mixture of experts": 2, "quantization": 2, "inference": 2,
        "distributed training": 2, "interconnect": 2, "scaling law": 2,
        "attention": 1, "reasoning": 1, "reinforcement learning": 1,
        "agent": 1, "pretraining": 1, "fine-tuning": 1,
    },
    "arxiv_orgs": [
        "DeepMind", "OpenAI", "Anthropic", "Meta AI", "NVIDIA",
        "Microsoft Research", "Qwen", "DeepSeek", "Alibaba", "ByteDance",
    ],
    "arxiv_author_boost": 6,
    "arxiv_org_boost": 4,
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


def load_sources(path: Optional[Path] = None) -> dict:
    """Load radar sources, creating the file with defaults on first run.

    Resolution order: explicit ``path`` arg → ``radar_sources_file`` config
    key (or ``RADAR_SOURCES_FILE`` env) → ``~/.agent-reach/radar.yaml``.
    The explicit arg exists so the evolve harness and tests can point a run
    at a git-tracked sources file without touching user config.
    """
    src = Path(path) if path else Path(Config().get("radar_sources_file") or SOURCES_FILE)
    if src.exists():
        with open(src, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # Merge so new default keys appear for existing users.
        merged = {**DEFAULT_SOURCES, **data}
        return merged
    src.parent.mkdir(parents=True, exist_ok=True)
    with open(src, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_SOURCES, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info(f"Created default radar sources at {src}")
    return dict(DEFAULT_SOURCES)


# ── guru roster ───────────────────────────────────────────────────────────

GURU_CATEGORY_LABELS = {
    "godfathers": "深度學習先驅",
    "industry_leaders": "產業推動者",
    "research": "研究派",
    "engineering_oss": "工程開源派",
    "industry_supply": "產業/供應鏈分析",
    "education_data": "教育/資料派",
    "longform_voices": "長文/訪談/影響者",
    "cn_ecosystem": "華語/中國圈",
}


def guru_entries(sources: dict) -> list[dict]:
    """Flatten the ``gurus`` category map into entries tagged with category."""
    out: list[dict] = []
    gurus = sources.get("gurus") or {}
    if not isinstance(gurus, dict):
        return out
    for category, entries in gurus.items():
        for entry in entries or []:
            if not isinstance(entry, dict):
                entry = {"handle": str(entry)}
            e = dict(entry)
            e["category"] = category
            out.append(e)
    return out


def guru_twitter_accounts(sources: dict) -> list[dict]:
    """Guru entries with an X handle, as collect_twitter account dicts."""
    out: list[dict] = []
    for e in guru_entries(sources):
        handle = str(e.get("handle") or "").lstrip("@")
        if not handle:
            continue
        out.append({"handle": handle, "note": e.get("lens", ""), "category": e.get("category", "")})
    return out


def guru_rss_feeds(sources: dict) -> list[str]:
    """Per-guru RSS/Atom feeds (deduped, order-preserving)."""
    seen: set[str] = set()
    out: list[str] = []
    for e in guru_entries(sources):
        url = str(e.get("rss") or "").strip()
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def guru_feed_meta(sources: dict) -> dict[str, dict]:
    """RSS feed URL → {name, lens, category} for digest annotation."""
    meta: dict[str, dict] = {}
    for e in guru_entries(sources):
        url = str(e.get("rss") or "").strip()
        if url:
            meta.setdefault(url, {
                "name": e.get("name", ""),
                "lens": e.get("lens", ""),
                "category": e.get("category", ""),
            })
    return meta


def guru_author_names(sources: dict) -> list[str]:
    """All arxiv author names across gurus (for the arXiv author boost)."""
    seen: set[str] = set()
    out: list[str] = []
    for e in guru_entries(sources):
        for name in e.get("arxiv_names") or []:
            n = str(name).strip()
            if n and n.lower() not in seen:
                seen.add(n.lower())
                out.append(n)
    return out


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

    # Normalize entries to (handle, lens, category). Legacy twitter_accounts
    # entries ("handle" or {handle, note}) come first so an explicit user
    # entry overrides a guru-roster duplicate; guru accounts follow with
    # their category tag for digest grouping.
    accounts: list[tuple[str, str, str]] = []
    seen_handles: set[str] = set()
    for entry in sources.get("twitter_accounts", []):
        if isinstance(entry, dict):
            h, lens = str(entry.get("handle", "")).lstrip("@"), entry.get("note", "")
        else:
            h, lens = str(entry).lstrip("@"), ""
        if h and h.lower() not in seen_handles:
            seen_handles.add(h.lower())
            accounts.append((h, lens, ""))
    for g in guru_twitter_accounts(sources):
        h = g["handle"]
        if h.lower() not in seen_handles:
            seen_handles.add(h.lower())
            accounts.append((h, g.get("note", ""), g.get("category", "")))

    timeout = int(sources.get("twitter_timeout", 30))
    retries = int(sources.get("twitter_retries", 1))

    def _fetch(acct: tuple[str, str, str]) -> list[Item]:
        h, lens, category = acct
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
            if category:
                it.extra["guru_category"] = category
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
    meta = guru_feed_meta(sources)
    urls: list[str] = []
    for url in list(sources.get("rss_feeds", [])) + guru_rss_feeds(sources):
        if url not in urls:
            urls.append(url)
    for url in urls:
        try:
            feed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"RSS parse failed for {url}: {e}")
            continue
        guru = meta.get(url, {})
        feed_title = guru.get("name") or (feed.feed.get("title") if feed.feed else None) or url
        extra: dict = {}
        if guru.get("lens"):
            extra["lens"] = guru["lens"]
        if guru.get("category"):
            extra["guru_category"] = guru["category"]
        for e in feed.entries[:per]:
            items.append(
                Item(
                    source=f"rss:{feed_title}",
                    kind="rss",
                    title=(e.get("title") or "").strip(),
                    url=e.get("link") or "",
                    text=re.sub(r"<[^>]+>", "", e.get("summary", ""))[:280],
                    ts=e.get("published"),
                    extra=dict(extra),
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
    # Deferred import — radar_arxiv imports from this module.
    from agent_reach.radar_arxiv import collect_arxiv

    kw = sources.get("topic_keywords", [])
    rss = collect_rss(sources)
    if sources.get("filter_rss", True):
        # Guru feeds are curated/trusted — only generic feeds go through the
        # topic gate (a Lilian Weng post shouldn't die on keyword mismatch).
        rss = [i for i in rss if i.extra.get("guru_category") or _is_on_topic(i, kw)]
    trends = collect_google_trends(sources)
    if sources.get("filter_trends", True):
        trends = [i for i in trends if _is_on_topic(i, kw)]
    return {
        "tweet": _dedupe(collect_twitter(sources, config)),
        "web": _dedupe(collect_exa(sources)),
        "rss": _dedupe(rss),
        "trend": _dedupe(trends),
        # Papers carry their own scorer-gate; no topic filter here.
        "paper": _dedupe(collect_arxiv(sources, config)),
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
        f"· RSS {counts.get('rss',0)} · 论文 {counts.get('paper',0)} · 趋势 {counts.get('trend',0)}"
    )
    lines.append("")
    lines.append("## 🧠 今日洞察")
    lines.append("")
    lines.append("<!-- 由 Claude / LLM 阅读下方原料后填写：3-5 条「真正重要 + 为什么」，过滤噪声 -->")
    lines.append("_（待综合）_")
    lines.append("")

    # Twitter — ranked by engagement; grouped by guru category when present.
    def _emit_tweets(its: list[Item]) -> None:
        for it in its:
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

    all_tweets = grouped.get("tweet", [])
    if all_tweets:
        lines.append("## 🐦 Twitter / X（按热度）")
        lines.append("")
        if any(i.extra.get("guru_category") for i in all_tweets):
            buckets: dict[str, list[Item]] = {}
            for it in all_tweets:
                buckets.setdefault(it.extra.get("guru_category", ""), []).append(it)
            # Uncategorized (user's own accounts) first, then roster order.
            order = [""] + list(GURU_CATEGORY_LABELS) + [
                c for c in buckets if c and c not in GURU_CATEGORY_LABELS
            ]
            for cat in order:
                if cat not in buckets:
                    continue
                label = "自選帳號" if not cat else GURU_CATEGORY_LABELS.get(cat, cat)
                lines.append(f"### {label}")
                lines.append("")
                _emit_tweets(sorted(buckets.pop(cat), key=lambda i: i.score, reverse=True)[:cap])
        else:
            _emit_tweets(sorted(all_tweets, key=lambda i: i.score, reverse=True)[:cap])

    # arXiv papers — 軟硬體架構脈搏, ranked by the relevance scorer.
    papers = sorted(grouped.get("paper", []), key=lambda i: i.score, reverse=True)
    if papers:
        top_n = int(sources.get("arxiv_top_n", 8))
        dive_n = int(sources.get("arxiv_deep_dive_n", 4))
        lines.append("## 📄 arXiv 論文雷達（軟硬體架構脈搏）")
        lines.append("")
        for rank, it in enumerate(papers[:top_n]):
            flag = " 🔬" if rank < dive_n else ""
            lines.append(f"- [{it.title}]({it.url}){flag} · score {it.score:g}")
            why = it.extra.get("why") or []
            if why:
                lines.append(f"  - _{'、'.join(why[:6])}_")
            if it.author:
                lines.append(f"  - {it.author[:120]}")
        lines.append("")
        if dive_n and len(papers) > 0:
            lines.append("> 🔬 = 深讀候選（`agent-reach radar-deepdive` 產出全文蒸餾報告）")
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
