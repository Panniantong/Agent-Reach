# -*- coding: utf-8 -*-
"""Mentor–student daily-report pipeline for the radar.

Pattern (maker–checker / distillation-by-critique):

    radar data ──▶ STUDENT (local Ollama qwen) drafts the daily report
                       │
                       ▼
                  MENTOR (Claude Opus) scores it on a rubric, lists fixes,
                  and rewrites a corrected "gold" report
                       │
                       ▼
    log (draft, critique, gold, scores) ──▶ gold reports become few-shot
    exemplars for the student's NEXT run, and scores are tracked over time.

The student is fully local/free and runs unattended. The mentor uses the
Anthropic API when ANTHROPIC_API_KEY is set (for scheduled/automated runs);
otherwise the pipeline saves the draft + material so Claude Opus (e.g. in
Claude Code) can do the critique interactively and seed the first gold.

No new dependencies — Ollama and Anthropic are called over HTTP with requests.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from loguru import logger

from agent_reach.config import Config
from agent_reach.radar import RADAR_DIR, Item, run_radar

TRAINING_DIR = RADAR_DIR / "training"
SCORES_FILE = TRAINING_DIR / "scores.jsonl"
GOLD_DIR = TRAINING_DIR / "gold"

DEFAULT_STUDENT_MODEL = "qwen2.5:7b"
RUBRIC_DIMENSIONS = ["coverage", "accuracy", "depth", "lens_application", "actionability"]

STUDENT_SYSTEM = """你是一个 AI×投资 研究助手。基于【今日多平台原始材料】写一份精炼、有深度、可操作的中文每日简报。
材料含：X 分析师原创推文（每条可能带「怎么读」反向透镜）、Exa 网文、RSS。

硬性要求：
1. 开头给【今日要点】3-5 条：每条是「真正重要的事 + 为什么重要」，过滤噪声。
2. 按主题归纳：半导体/供应链、AI 基建/算力、个股与估值、风险与市场情绪、加密（如有）。
3. 严格应用每条推文的「怎么读」透镜：标注为喊单/反指的，绝不当买入信号，要反向解读。
4. 区分事实与观点；观点注明出处（@handle）。不要编造数字或事件。
5. 简洁、可扫读；用 markdown。结尾一句风险提示（非投资建议）。
6. 【鐵律·防照抄】如果給了過往範本，範本只用於學習「格式與歸因風格」（如 [事實]/[觀點] 標註、@出處、因果串聯的寫法）。
   嚴禁照抄範本裡的任何公司/代號/數字/事件——今天簡報裡每一條事實與觀點都必須能在【今日材料】中找到出處；
   材料裡沒有的（即使範本裡有），絕對不要寫進今天的簡報。
7. 【語言】全程用「繁體中文（台灣用語）」輸出，不要用簡體字。
8. 【個股彙總】最後務必附一個表格「📊 個股彙總」：欄位 = 代號 | 觀點/原因（一句話）| 出處(@handle)。
   把今日材料中所有被討論到的股票/代號都列進去；沒有明確代號的公司可用名稱。"""

MENTOR_SYSTEM = """你是资深投研主编（导师）。下面给你【今日原始材料】和【学生模型写的简报草稿】。
你的任务：校验、纠错、提升，并产出一份修正后的范本(gold)简报。

严格只输出一个 JSON 对象，结构：
{
  "scores": {"coverage": 0-100, "accuracy": 0-100, "depth": 0-100, "lens_application": 0-100, "actionability": 0-100},
  "total": 0-100,
  "issues": ["具体问题与修正点，逐条", ...],
  "gold_report": "修正后的完整简报（markdown 字符串）"
}

评分维度含义：coverage=是否覆盖材料里真正重要的信号；accuracy=有无臆造/张冠李戴/与材料矛盾；
depth=是否串联因果、给出非显然洞察；lens_application=是否正确应用反指/喊单透镜；actionability=要点是否可操作。
gold_report 要比草稿更准、更深、噪声更少，并修掉 issues 里指出的问题。"""


# ── material assembly (per-account fair, so deep analysts aren't buried) ──────


def build_material(grouped: dict[str, list[Item]], per_account: int = 2, max_chars: int = 22000) -> str:
    """Compact the full collection into LLM-ready material, fair across accounts."""
    lines: list[str] = []

    # Tweets grouped by account so every analyst is represented (not view-ranked).
    by_acct: dict[str, list[Item]] = {}
    for it in grouped.get("tweet", []):
        by_acct.setdefault(it.source, []).append(it)
    lines.append("## X 分析师推文（按账号）")
    for src, its in by_acct.items():
        its.sort(key=lambda x: x.score, reverse=True)
        handle = src.split(":", 1)[-1]
        for it in its[:per_account]:
            lens = it.extra.get("lens")
            m = it.extra.get("metrics", {})
            views = int(m.get("views", 0))
            tag = f" [怎么读: {lens}]" if lens else ""
            body = " ".join(it.text.split())
            lines.append(f"- {handle}{tag} ({views:,}v): {body}")

    web = grouped.get("web", [])
    if web:
        lines.append("\n## 全网网文 (Exa)")
        for it in web:
            lines.append(f"- {it.title} — {it.text[:200]} ({it.url})")

    rss = grouped.get("rss", [])
    if rss:
        lines.append("\n## RSS")
        for it in rss:
            lines.append(f"- {it.title} ({it.url})")

    text = "\n".join(lines)
    return text[:max_chars]


# ── student (local Ollama) ───────────────────────────────────────────────────


def _ollama_chat(model: str, system: str, user: str, base_url: str, timeout: int = 600) -> str:
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0.3, "num_ctx": 16384},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


LESSONS_FILE = TRAINING_DIR / "lessons.md"

# Fact-FREE skeleton. A 7B student copies any exemplar that contains facts, so
# we give it only headings + notation — nothing to plagiarize. All facts must
# then come from today's material.
STRUCTURE_TEMPLATE = """# 🛰️ AI×投資 每日簡報 — <今天日期>
## 📌 重點摘要
1. <真正重要的事 + 為什麼>（3-5 條，只放硬信號）
## 半導體 / 供應鏈
- [事實·@出處] <...>
- [觀點·@出處] <...>
## AI 基建 / 算力
- [事實/觀點·@出處] <...>
## 個股與估值
- [觀點·@出處] <代號 + 估值/邏輯>
## 風險與市場情緒
- [硬信號·@出處] <...>
## 加密（如有）
- [喊單/反指透鏡·@出處] <對喊單號要反向解讀，不當買入信號>
## 📊 個股彙總
| 代號 | 觀點/原因 | 出處 |
|---|---|---|
| $XXX | <一句話> | @handle |
## 待驗證 / 數據缺口
> 風險提示（非投資建議）"""


def load_lessons() -> str:
    """Accumulated mentor corrections (terse, fact-free rules) that steer the student."""
    if LESSONS_FILE.exists():
        return LESSONS_FILE.read_text(encoding="utf-8").strip()
    return ""


def append_lesson(lesson: str) -> None:
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    with open(LESSONS_FILE, "a", encoding="utf-8") as f:
        f.write(f"- {lesson.strip()}\n")


def load_exemplars(n: int = 2) -> list[str]:
    """Past gold reports — kept for human reference / future fine-tuning, NOT fed
    to the student as content (small models plagiarize them)."""
    if not GOLD_DIR.exists():
        return []
    files = sorted(GOLD_DIR.glob("*.md"), reverse=True)[:n]
    return [f.read_text(encoding="utf-8") for f in files]


def student_draft(material: str, model: str, base_url: str, lessons: str = "") -> str:
    user = f"【格式骨架（只照这个结构与标注法写，里面没有任何事实可抄）】\n{STRUCTURE_TEMPLATE}\n\n"
    if lessons:
        user += f"【主编历次纠正的规则（务必遵守）】\n{lessons}\n\n"
    user += (
        f"【今日原始材料（唯一且全部的事实来源）】\n\n{material}\n\n"
        "只用【今日材料】里的事实写今天的简报，按上面的骨架组织。"
        "材料里没有的公司/代号/数字/事件，一律不得出现。"
    )
    return _ollama_chat(model, STUDENT_SYSTEM, user, base_url)


# ── mentor (Claude Opus via Anthropic API; optional) ─────────────────────────


def mentor_critique(draft: str, material: str, model: str = "claude-opus-4-8") -> Optional[dict]:
    """Score + correct the student draft. Returns None if no ANTHROPIC_API_KEY."""
    key = os.environ.get("ANTHROPIC_API_KEY") or Config().get("anthropic_api_key")
    if not key:
        return None
    user = f"【今日原始材料】\n{material}\n\n【学生模型的简报草稿】\n{draft}\n\n请按要求输出 JSON。"
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 8000,
            "system": MENTOR_SYSTEM,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=300,
    )
    resp.raise_for_status()
    text = "".join(b.get("text", "") for b in resp.json().get("content", []))
    # The model may wrap JSON in prose/fences; extract the object.
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        logger.warning("mentor returned no JSON object")
        return {"raw": text}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {"raw": text}


# ── orchestration ─────────────────────────────────────────────────────────────


def run_report_pipeline(
    student_model: str = DEFAULT_STUDENT_MODEL,
    config: Optional[Config] = None,
    when: Optional[datetime] = None,
) -> dict:
    """Collect → student draft → mentor critique (if key) → log training triple."""
    config = config or Config()
    when = when or datetime.now(timezone.utc).astimezone()
    base_url = config.get("ollama_base_url") or os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
    stamp = f"{when:%Y-%m-%d-%H%M}"

    # 1) collect (parallel) + 2) assemble material
    _, grouped = run_radar(config=config, when=when)
    material = build_material(grouped)

    # 3) student draft — fact-free structure template + accumulated lessons
    #    (NOT past gold content, which a 7B student plagiarizes).
    lessons = load_lessons()
    # Pin the real date (the model otherwise hallucinates one from its cutoff).
    lessons = f"简报标题日期必须用：{when:%Y-%m-%d}（不要用你记忆里的日期）\n{lessons}"
    logger.info(f"student={student_model} drafting (lessons={'yes' if lessons else 'none'})...")
    draft = student_draft(material, student_model, base_url, lessons)

    # 4) mentor critique (automated only if ANTHROPIC_API_KEY present)
    critique = mentor_critique(draft, material)

    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "date": stamp,
        "student_model": student_model,
        "lessons_used": bool(lessons),
        "material_chars": len(material),
        "material": material,  # kept so an interactive mentor can read the student's input
        "draft": draft,
        "critique": critique,
        "mentor_ran": critique is not None and "scores" in (critique or {}),
    }
    rec_path = TRAINING_DIR / f"{stamp}.json"
    rec_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5) if mentor produced gold + scores, persist them for the feedback loop
    if critique and "gold_report" in critique:
        GOLD_DIR.mkdir(parents=True, exist_ok=True)
        (GOLD_DIR / f"{stamp}.md").write_text(critique["gold_report"], encoding="utf-8")
    if critique and "scores" in critique:
        with open(SCORES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"date": stamp, "total": critique.get("total"), **critique["scores"]}, ensure_ascii=False) + "\n")

    record["record_path"] = str(rec_path)
    record["material"] = material  # returned for interactive mentor fallback
    return record


def save_gold(stamp: str, gold_markdown: str, scores: Optional[dict] = None) -> Path:
    """Persist a mentor-approved gold report (used when mentor runs interactively)."""
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLD_DIR / f"{stamp}.md"
    path.write_text(gold_markdown, encoding="utf-8")
    if scores:
        TRAINING_DIR.mkdir(parents=True, exist_ok=True)
        with open(SCORES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"date": stamp, **scores}, ensure_ascii=False) + "\n")
    return path
