# -*- coding: utf-8 -*-
"""Scenario registry — named, parameterized pipelines.

Each scenario = collector(s) + an LLM spec list (``scenario_models`` in
radar.yaml, per-call ``model`` override) + a markdown deliverable under
RADAR_DIR. Triggered from the CLI (``radar-run``) or the web console, which
renders trigger cards straight from this registry (``scenarios_manifest``).

``run_scenario`` never raises; social posts are always drafts for human
review — nothing here publishes anywhere.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import requests
from loguru import logger

from agent_reach.config import Config
from agent_reach.llm import llm_chat_first
from agent_reach.radar import _FEED_UA, RADAR_DIR, load_sources

REPORTS_DIR = RADAR_DIR / "reports"
SUMMARIES_DIR = RADAR_DIR / "summaries"
SOCIAL_DIR = RADAR_DIR / "social"

TOPIC_CHOICES = ["all", "ai", "ee", "rf", "spacetech", "quantum"]

EXPERT_REPORT_SYSTEM = """你是該領域的資深研究員兼產業顧問。深讀下面這篇 arXiv 論文，用繁體中文（台灣用語）寫一份**長篇專家報告**，markdown 結構嚴格如下：

# <論文標題>（<arXiv ID>）
## 背景脈絡
- 這個問題為什麼存在、既有路線是什麼、這篇切入點在哪。
## 方法拆解
- 關鍵機制逐層講清楚，講因果不講流水帳；有公式/架構就白話重述。
## 實驗與證據批判
- 數字證據、基線公允性、消融是否支撐主張；哪些結論站得住、哪些過度延伸。
## 工程落地評估
- 復現成本、依賴的硬體/資料、與現有 stack 的整合難度。
## 產業與供應鏈影響
- 若結論成立，哪些環節受益或承壓（標註為推論，非投資建議）。
## 開放問題與後續追蹤
- 值得追的後續實驗、相關團隊、可能的反例。

硬性要求：只根據給你的論文內容寫，數字要能在原文找到；沒把握的明說。"""

X_SUMMARY_SYSTEM = """你是資深 AI 產業觀察員。下面是多位大神近期的 X 貼文材料（部分帳號附「怎麼讀」反向透鏡，讀時先套透鏡）。用繁體中文寫總結，結構：

## 共識
## 分歧
## 可行動訊號
## 值得追蹤

硬性要求：只根據材料寫，每條標註來源帳號；透鏡提醒要折價的內容就折價；材料裡沒有的不要編。"""

SOCIAL_POST_SYSTEM = """你是雙語科技社群寫手。根據材料寫一篇 X/Twitter 風格貼文**草稿**，輸出結構嚴格：

## 繁中版
（繁體中文台灣用語：有 hook、有觀點、資訊密度高，300 字內，結尾 3-5 個 hashtags，最後一行「觀點僅供參考，非投資建議」）

## English
(Punchy English version, under 280 words, 3-5 hashtags, last line "Not financial advice.")

硬性要求：只根據材料寫，不編數字；這是草稿，人工審核後才會發布。"""

MARKET_SIGNAL_SYSTEM = """你是市場訊號分析師。根據下面的雷達 digest 與 Finviz 市場資料，先提出 1-3 個今天真正值得注意的市場訊號（每個：訊號 + 證據 + 為什麼重要，推論處明確標註「推論」），然後把它們寫成一篇雙語社群貼文草稿，輸出結構嚴格：

## 訊號分析
（1-3 個訊號，條列）

## 繁中版
（貼文草稿，300 字內，hashtags，結尾「觀點僅供參考，非投資建議」）

## English
(Post draft, under 280 words, hashtags, last line "Not financial advice.")

硬性要求：只根據材料；材料不足就少寫幾個訊號，不要編。"""


# ── registry model ────────────────────────────────────────────────────────


@dataclass
class Param:
    name: str
    label: str
    default: object = None
    choices: Optional[list[str]] = None


@dataclass
class Scenario:
    id: str
    label: str
    desc: str
    run: Callable[[dict, Config], dict]
    params: list[Param] = field(default_factory=list)
    required_providers: list[str] = field(default_factory=list)


def _model_specs(params: dict, sources: dict, key: str) -> list[str]:
    """Per-call model override, else the scenario_models fallback list."""
    override = str(params.get("model") or "").strip()
    if override:
        return [override]
    specs = (sources.get("scenario_models") or {}).get(key) or []
    return [str(s) for s in specs]


def _write(path_dir, name: str, text: str, used_model: str, meta: str = "") -> str:
    path_dir.mkdir(parents=True, exist_ok=True)
    path = path_dir / name
    header = f"<!-- model: {used_model}{(' · ' + meta) if meta else ''} -->\n\n"
    path.write_text(header + text, encoding="utf-8")
    return str(path)


# ── scenario: arXiv → expert long-form report ─────────────────────────────


def _run_arxiv_expert(params: dict, config: Config) -> dict:
    sources = load_sources()
    topic = str(params.get("topic") or "all")
    top_n = int(params.get("top_n") or 1)
    specs = _model_specs(params, sources, "arxiv_expert")
    when = datetime.now(timezone.utc).astimezone()

    from agent_reach.radar_wiki import _load_all_papers, _topic_papers

    papers = _load_all_papers(sources, config, when)
    if topic and topic != "all":
        papers = _topic_papers(papers, topic)
    picks = sorted(papers, key=lambda i: i.score, reverse=True)[:top_n]
    if not picks:
        return {"ok": False, "error": "沒有命中論文 — 先跑 agent-reach radar，或換 topic"}

    from agent_reach.radar_arxiv import fetch_paper_text

    outputs: list[str] = []
    used = ""
    for it in picks:
        aid = str(it.extra.get("arxiv_id") or "unknown")
        logger.info(f"expert report: reading {aid} ({it.title[:60]})")
        fulltext = fetch_paper_text(aid, int(sources.get("arxiv_fulltext_chars", 30000)))
        user = (
            f"【論文】{it.title}（arXiv:{aid}）\n【作者】{it.author}\n"
            f"【入選原因】{'、'.join(it.extra.get('why', []))}\n\n"
            f"【論文內容（HTML 轉文字，可能有噪聲）】\n{fulltext or it.text}"
        )
        text, used = llm_chat_first(specs, EXPERT_REPORT_SYSTEM, user, config)
        if not text:
            return {"ok": False, "error": f"模型全部失敗（{specs}）— 跑 radar-run providers 檢查",
                    "outputs": outputs}
        outputs.append(_write(
            REPORTS_DIR, f"{when:%Y-%m-%d}-{aid.replace('/', '_')}.md",
            text, used, meta=f"topic: {it.extra.get('topic', '')}",
        ))
    return {"ok": True, "outputs": outputs,
            "summary": f"{len(outputs)} 篇專家長報告（{used}）→ {REPORTS_DIR}"}


# ── scenario: X gurus → summary ───────────────────────────────────────────


def _run_x_summary(params: dict, config: Config) -> dict:
    sources = load_sources()
    category = str(params.get("category") or "all")
    specs = _model_specs(params, sources, "x_summary")
    when = datetime.now(timezone.utc).astimezone()

    from agent_reach.radar import collect_twitter
    from agent_reach.radar_report import build_material

    tweets = collect_twitter(sources, config)
    if category and category != "all":
        tweets = [t for t in tweets if t.extra.get("guru_category") == category]
    if not tweets:
        return {"ok": False, "error": "沒有收到貼文 — 檢查 twitter cookies（agent-reach doctor）或 category"}
    material = build_material({"tweet": tweets})
    text, used = llm_chat_first(specs, X_SUMMARY_SYSTEM, material, config)
    if not text:
        return {"ok": False, "error": f"模型全部失敗（{specs}）— NIM 需 NVIDIA_API_KEY，本地需 ollama pull nemotron"}
    out = _write(SUMMARIES_DIR, f"{when:%Y-%m-%d}-x-{category}.md", text, used,
                 meta=f"category: {category} · {len(tweets)} posts")
    return {"ok": True, "outputs": [out], "summary": f"X 大神總結（{used}）→ {out}"}


# ── scenario: GitHub trending → bilingual social post ─────────────────────


def fetch_github_trending(days: int = 7, keyword: str = "", top_n: int = 10,
                          timeout: int = 30) -> list[dict]:
    """Hot new repos via the public search API (no gh auth). Never raises."""
    since = (datetime.now(timezone.utc) - timedelta(days=int(days))).strftime("%Y-%m-%d")
    q = f"created:>{since}" + (f" {keyword}" if keyword else "")
    try:
        r = requests.get(
            "https://api.github.com/search/repositories",
            params={"q": q, "sort": "stars", "order": "desc", "per_page": int(top_n)},
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json", "User-Agent": _FEED_UA},
        )
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"github trending fetch failed: {e}")
        return []
    return [{
        "name": i.get("full_name", ""),
        "stars": int(i.get("stargazers_count") or 0),
        "desc": (i.get("description") or "")[:200],
        "lang": i.get("language") or "",
        "url": i.get("html_url", ""),
    } for i in items]


def _run_github_post(params: dict, config: Config) -> dict:
    sources = load_sources()
    days = int(params.get("days") or 7)
    keyword = str(params.get("keyword") or "")
    specs = _model_specs(params, sources, "social_post")
    when = datetime.now(timezone.utc).astimezone()

    repos = fetch_github_trending(days=days, keyword=keyword)
    if not repos:
        return {"ok": False, "error": "GitHub 搜尋沒有結果（網路 / rate limit / keyword 太窄）"}
    material = "\n".join(
        f"- {r['name']} ⭐ {r['stars']} · {r['lang']} · {r['desc']} · {r['url']}" for r in repos
    )
    user = f"【近 {days} 天新建熱門 GitHub repos{('（關鍵字 ' + keyword + '）') if keyword else ''}】\n{material}"
    text, used = llm_chat_first(specs, SOCIAL_POST_SYSTEM, user, config)
    if not text:
        return {"ok": False, "error": f"模型全部失敗（{specs}）"}
    out = _write(SOCIAL_DIR, f"{when:%Y-%m-%d}-github.md", text, used,
                 meta=f"days: {days} · repos: {len(repos)}")
    return {"ok": True, "outputs": [out], "summary": f"GitHub 熱門雙語貼文草稿（{used}）→ {out}"}


# ── scenario: market signals → bilingual social post ──────────────────────


def _run_market_signal(params: dict, config: Config) -> dict:
    sources = load_sources()
    specs = _model_specs(params, sources, "social_post")
    when = datetime.now(timezone.utc).astimezone()

    latest = RADAR_DIR / "latest.md"
    digest = latest.read_text(encoding="utf-8") if latest.exists() else ""
    market_lines: list[str] = []
    sidecar = RADAR_DIR / "latest-items.json"
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            for d in (data.get("items") or {}).get("market", []):
                market_lines.append(f"- {d.get('title')} ({d.get('source')})")
        except Exception:  # noqa: BLE001
            pass
    if not digest and not market_lines:
        return {"ok": False, "error": "沒有材料 — 先跑 agent-reach radar（建議含 --platforms finviz）"}
    user = f"【今日雷達 digest】\n{digest[:20000]}"
    if market_lines:
        user += "\n\n【Finviz 市場訊號】\n" + "\n".join(market_lines[:30])
    text, used = llm_chat_first(specs, MARKET_SIGNAL_SYSTEM, user, config)
    if not text:
        return {"ok": False, "error": f"模型全部失敗（{specs}）"}
    out = _write(SOCIAL_DIR, f"{when:%Y-%m-%d}-signal.md", text, used)
    return {"ok": True, "outputs": [out], "summary": f"市場訊號雙語貼文草稿（{used}）→ {out}"}


# ── registry ──────────────────────────────────────────────────────────────


SCENARIOS: dict[str, Scenario] = {
    s.id: s for s in [
        Scenario(
            id="arxiv_expert_report",
            label="ArXiv → 專家長報告",
            desc="挑主題 top 論文，全文深讀後由本地 Qwen 寫長篇專家報告",
            run=_run_arxiv_expert,
            params=[
                Param("topic", "主題", "all", TOPIC_CHOICES),
                Param("top_n", "篇數", 1),
                Param("model", "模型 spec（空=預設）", ""),
            ],
            required_providers=["ollama"],
        ),
        Scenario(
            id="x_guru_summary",
            label="X 大神 → Nemotron 總結",
            desc="抓 guru roster 近期貼文，Nemotron 總結共識/分歧/可行動訊號",
            run=_run_x_summary,
            params=[
                Param("category", "分類", "all",
                      ["all", "godfathers", "industry_leaders", "research", "engineering_oss",
                       "industry_supply", "education_data", "longform_voices", "cn_ecosystem"]),
                Param("model", "模型 spec（空=預設）", ""),
            ],
            required_providers=["twitter", "nvidia"],
        ),
        Scenario(
            id="github_trending_post",
            label="GitHub 熱門 → 雙語貼文",
            desc="近 N 天新建高星 repo，寫繁中+英文社群貼文草稿",
            run=_run_github_post,
            params=[
                Param("days", "天數", 7),
                Param("keyword", "關鍵字（可空）", ""),
                Param("model", "模型 spec（空=預設）", ""),
            ],
            required_providers=["anthropic"],
        ),
        Scenario(
            id="market_signal_post",
            label="市場訊號 → 雙語貼文",
            desc="讀今日 digest + Finviz 訊號，提 1-3 個訊號並寫雙語貼文草稿",
            run=_run_market_signal,
            params=[Param("model", "模型 spec（空=預設）", "")],
            required_providers=["anthropic"],
        ),
    ]
}


def run_scenario(scenario_id: str, params: Optional[dict] = None,
                 config: Optional[Config] = None) -> dict:
    """Run one scenario by id. Never raises."""
    sc = SCENARIOS.get(scenario_id)
    if not sc:
        return {"ok": False, "error": f"未知場景: {scenario_id}（radar-run list 看全部）"}
    try:
        return sc.run(params or {}, config or Config())
    except Exception as e:  # noqa: BLE001 - scenario failures must surface, not crash
        logger.warning(f"scenario {scenario_id} failed: {e}")
        return {"ok": False, "error": str(e)}


def scenarios_manifest(status: Optional[dict] = None) -> list[dict]:
    """JSON-serializable registry view; ``status`` (providers_status) marks readiness."""
    out = []
    for sc in SCENARIOS.values():
        missing = [p for p in sc.required_providers if status and not status.get(p, {}).get("ok")]
        out.append({
            "id": sc.id,
            "label": sc.label,
            "desc": sc.desc,
            "params": [{"name": p.name, "label": p.label, "default": p.default,
                        "choices": p.choices} for p in sc.params],
            "required_providers": sc.required_providers,
            "ready": not missing if status else None,
            "missing": missing,
        })
    return out
