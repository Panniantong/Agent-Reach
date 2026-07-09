# -*- coding: utf-8 -*-
"""KOL-post output branch.

Generates a single-stock KOL post scaffold (繁體中文) in the RKLB template:
frontmatter + 為什麼看它 + 供應鏈深度挖 (auto-injected from the user's supply-chain
knowledge graph) + 軟體/機器人連結 + 展望+風險 + 你的補充佔位 + hashtags.

One stock per post. The scaffold is meant to be refined by the writer (Claude
Opus) with live facts (Exa/web) and by the user with their KG knowledge.

Leverages the $hark supply-chain KG (`app/kg_data.js`, `window.KG_DATA = {...}`)
when available: pulls the relevant sector's chokepoint Material/Technology nodes
straight into the 供應鏈 section.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent_reach.config import Config
from agent_reach.radar import RADAR_DIR

KOL_DIR = RADAR_DIR / "kol"
DEFAULT_KG_PATH = Path("D:/DOT/$hark/app/kg_data.js")

THEMES = {
    "space": "太空股",
    "software": "軟體股",
    "robotics": "廣義機器人股（人形 + 非人形）",
    "semi": "半導體股",
    "critical_minerals": "關鍵礦物股",
    "github": "熱門 GitHub 專案",
}


def load_kg(path: Optional[Path] = None) -> Optional[dict]:
    """Load the $hark supply-chain KG bundle (window.KG_DATA = {...})."""
    p = Path(Config().get("kg_data_path") or path or DEFAULT_KG_PATH)
    if not p.exists():
        return None
    try:
        t = p.read_text(encoding="utf-8")
        return json.loads(t[t.find("{") : t.rfind("}") + 1])
    except Exception:  # noqa: BLE001
        return None


def kg_chokepoints(kg: dict, sector: str, limit: int = 12) -> list[str]:
    """Return chokepoint Material/Technology node names for a sector (flat bundle)."""
    sec = (kg or {}).get("sectors", {}).get(sector)
    if not sec:
        return []
    out = []
    for n in sec.get("nodes", []):
        if n.get("type") in ("Material", "Technology", "Chokepoint"):
            out.append(f"[{n['type']}] {n.get('name', '')}")
    return out[:limit]


# ── richer artifact graphs (outputs/kg/*.json — edges carry the real chain) ──

DEFAULT_KG_ARTIFACT_DIR = Path("D:/DOT/$hark/outputs/kg")
# Edge relations rendered in the supply-chain section, with human labels.
_REL_LABELS = {
    "SUPPLIES": "↗ 供應給",
    "DEPENDS_ON": "↙ 依賴於",
    "HAS_RISK": "⚠ 風險",
    "ALTERNATIVE_TO": "⇄ 替代/競爭",
    "CAPEX_FLOWS_TO": "💰 資本支出流向",
    "STRATEGIC_INVESTMENT_IN": "🏦 戰略投資",
}


def load_graph(sector: str) -> Optional[dict]:
    """Load a rich KG artifact (string nodes + edge dicts) for a sector, if present."""
    base = Path(Config().get("kg_artifact_dir") or DEFAULT_KG_ARTIFACT_DIR)
    for name in (f"{sector}_supply_chain.json", f"supply_chain_{sector}.json"):
        p = base / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return None
    return None


def ticker_chain(sector: str, ticker: str, limit: int = 14) -> list[str]:
    """Edges touching `ticker` in the sector graph, grouped by relation, as readable lines."""
    g = load_graph(sector)
    if not g:
        return []
    t = ticker.upper()
    lines: list[str] = []
    for e in g.get("edges", []):
        if not isinstance(e, dict):
            continue
        src, dst, rel = str(e.get("src", "")).upper(), str(e.get("dst", "")).upper(), e.get("type", "")
        if t not in (src, dst):
            continue
        label = _REL_LABELS.get(rel, rel)
        other = dst if src == t else src
        mat = f"｜{e.get('material')}" if e.get("material") else ""
        note = f" — {e.get('note')}" if e.get("note") else ""
        grade = f" [grade {e.get('grade')}]" if e.get("grade") else ""
        arrow = f"{t} {label} {other}" if src == t else f"{other} {label} {t}"
        lines.append(f"- {arrow}{mat}{grade}{note}")
    return lines[:limit]


def scaffold(ticker: str, sector: str = "robotics", when: Optional[datetime] = None) -> str:
    when = when or datetime.now(timezone.utc).astimezone()
    theme = THEMES.get(sector, sector)
    # Prefer the rich artifact graph (real edges for this ticker); fall back to
    # the flat bundle's sector chokepoint node list.
    chain = ticker_chain(sector, ticker)
    kg = load_kg()
    chokes = kg_chokepoints(kg, sector) if kg else []
    kg_note = f"（KG as_of {kg.get('as_of')}）" if kg else "（未載入 KG）"

    fm = [
        "---",
        "type: kol_post_draft",
        f"as_of_timestamp: {when:%Y-%m-%dT%H:%M:%S%z}",
        "author_role: Writer",
        "PROJECT: Trading_Society_KOL_Post_Expansion",
        "PROGRAM: KOL_Post_Generation_Space_Software_Robotics_Themes",
        "SKILL: Structured_Markdown_Post_Generation",
        f"TARGET: KOL post on {ticker} ({theme}) — 供應鏈深度挖 + 軟體/機器人連結 + 風險標記 + 用戶 KG 補充佔位。一次一檔。",
        "source_paths: Exa/web 即時事實 + $hark 供應鏈 KG",
        "confidence: <填：公開事實 high / 預測 medium>",
        'risk_flags: ["<填風險>"]',
        "---",
        "",
    ]

    if chain:
        choke_block = f"**{ticker} 在 KG 中的供應鏈鏈路（{sector}，真實邊）：**\n" + "\n".join(chain)
    elif chokes:
        choke_block = f"**{sector} sector 卡脖子節點（請補與 {ticker} 的關係）：**\n" + "\n".join(
            f"- {c}" for c in chokes
        )
    else:
        choke_block = "- <從 KG 補充相關材料/技術卡脖子節點>"

    body = f"""# 🛰️ {ticker}：<一句話主題>

**一次只講一支股票 | {theme} 專題 | 供應鏈深度挖 + 軟體/機器人連結**

各位太空迷、供應鏈研究同好、量化與 KOL 朋友：

KOL Post 系列——一次一檔，我先產出草稿，你用你的理解 + 知識圖譜(KG)補充，共同打磨成可發內容。

---

## 為什麼現在看 {ticker}？
- **重大催化劑**：<填>
- **基本面**：<填 營收/訂單/毛利/backlog>
- **成長故事**：<填>
- **雙引擎（國防/商業 或 人形/工業）**：<填>

---

## 供應鏈深度挖（leverage 你的 KG {kg_note}）
從 KG 自動帶出的卡脖子節點（請補關係）：
{choke_block}

**你的 KG 可以補充的點**：
- <關鍵材料的地理集中度 / 台灣或亞洲角色>
- <替代來源、認證/驗證瓶頸、垂直整合進度>

---

## 軟體 + 廣義機器人連結
- **軟體核心**：<填>
- **廣義機器人（人形 + 非人形）**：<填>
- **GitHub / 開源連結（如有）**：<填 有趣/熱門專案>

---

## 短期 vs 中期展望 + 風險標記（Performance-first）
- **短期（1-3 月）**：<填>
- **中期（6-18 月）**：<填>
- **風險標記**：<高波動 / 執行風險 / 競爭 / 地緣 / 估值>
- **適合族群**：<填>

---

## 總結與討論
<填 2-3 句>。**recommend-only，非投資建議。**

**你的補充時間**：
- <針對性問題 1>
- <針對性問題 2>
- 想看下一檔哪一支？（{theme}）

#{ticker} #{sector} #SupplyChain #供應鏈分析

---

**後記給自己 / 團隊**：KOL Post 輸出分支。格式＝事實 + 供應鏈深度(KG) + 軟體/機器人連結 + 展望 + 風險標記 + 互動問題。下一檔換主題平行處理。
"""
    return "\n".join(fm) + body


def write_scaffold(ticker: str, sector: str = "robotics", when: Optional[datetime] = None) -> Path:
    when = when or datetime.now(timezone.utc).astimezone()
    KOL_DIR.mkdir(parents=True, exist_ok=True)
    path = KOL_DIR / f"{ticker}-{sector}-{when:%Y-%m-%d}.md"
    path.write_text(scaffold(ticker, sector, when), encoding="utf-8")
    return path
