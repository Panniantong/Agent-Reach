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
from agent_reach.radar_students import active_students, load_students

TRAINING_DIR = RADAR_DIR / "training"
SCORES_FILE = TRAINING_DIR / "scores.jsonl"
GOLD_DIR = TRAINING_DIR / "gold"

DEFAULT_STUDENT_MODEL = "qwen3:4b"  # ad-hoc override only; the roster is the source of truth
RUBRIC_DIMENSIONS = ["coverage", "accuracy", "depth", "lens_application", "actionability"]

# ── mentor panel: main teacher + assistant mentors ────────────────────────
# Fable 5 is the main teacher (final scores + gold rewrite). Assistants
# critique with the same rubric; whoever has an API key present shows up,
# the rest are skipped — graceful degradation, never a hard dependency.
DEFAULT_MENTOR_MODEL = "claude-fable-5"
DEFAULT_ASSISTANTS = [
    {"provider": "anthropic", "model": "claude-opus-4-8", "name": "Opus"},
    {"provider": "anthropic", "model": "claude-sonnet-5", "name": "Sonnet"},
    {"provider": "openai", "model": "gpt-5-codex", "name": "Codex"},
    {"provider": "xai", "model": "grok-4", "name": "Grok"},
]
PROVIDERS = {
    "anthropic": {"key": "anthropic_api_key"},
    "openai": {"key": "openai_api_key", "base_url": "https://api.openai.com/v1"},
    "xai": {"key": "xai_api_key", "base_url": "https://api.x.ai/v1"},
}

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

MENTOR_SYSTEM = """你是資深投研主編（主師）。下面給你【今日原始材料】、多位學生模型各自寫的【簡報草稿】，以及（可能有的）多位助教的評語。
你的任務：對每位學生分別評分、綜合所有草稿與助教意見，產出一份修正後的範本(gold)簡報。

嚴格只輸出一個 JSON 物件，結構：
{
  "per_student": {"<student_id>": {"scores": {"coverage": 0-100, "accuracy": 0-100, "depth": 0-100, "lens_application": 0-100, "actionability": 0-100}, "total": 0-100}, ...},
  "best_student": "<student_id>",
  "issues": ["具體問題與修正點，逐條", ...],
  "gold_report": "修正後的完整簡報（markdown 字串，取各草稿之長）"
}

評分維度含義：coverage=是否覆蓋材料裡真正重要的信號；accuracy=有無臆造/張冠李戴/與材料矛盾；
depth=是否串聯因果、給出非顯然洞察；lens_application=是否正確應用反指/喊單透鏡；actionability=要點是否可操作。
助教評語僅供參考，你有最終裁量權；學生間獨立評分，不要平均主義。
gold_report 要比所有草稿更準、更深、噪聲更少，並修掉 issues 裡指出的問題。"""

ASSISTANT_SYSTEM = """你是投研評審助教。下面給你【今日原始材料】與多位學生模型的【簡報草稿】。
對每位學生按 rubric 獨立評分並列出具體問題。不要重寫簡報。

嚴格只輸出一個 JSON 物件：
{"per_student": {"<student_id>": {"scores": {"coverage": 0-100, "accuracy": 0-100, "depth": 0-100, "lens_application": 0-100, "actionability": 0-100}, "total": 0-100}, ...},
 "issues": ["具體問題，逐條", ...]}

維度定義：coverage=覆蓋材料中真正重要的信號；accuracy=無臆造/與材料矛盾；depth=串聯因果、非顯然洞察；
lens_application=正確應用反指/喊單透鏡；actionability=要點可操作。"""


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

    papers = sorted(grouped.get("paper", []), key=lambda x: x.score, reverse=True)
    if papers:
        lines.append("\n## arXiv 論文（摘要級）")
        for it in papers[:8]:
            why = "、".join(it.extra.get("why", [])[:4])
            tag = f" [{why}]" if why else ""
            lines.append(f"- {it.title}{tag} — {it.text[:200]} ({it.url})")

    text = "\n".join(lines)
    return text[:max_chars]


# ── student (local Ollama) ───────────────────────────────────────────────────


def _ollama_chat(
    model: str,
    system: str,
    user: str,
    base_url: str,
    timeout: int = 600,
    options: Optional[dict] = None,
) -> str:
    opts = {"temperature": 0.3, "num_ctx": 16384}
    opts.update(options or {})
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": opts,
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


def student_draft(material: str, student: dict, base_url: str, lessons: str = "") -> str:
    """One student's draft. ``student`` is a roster entry: {id, model, persona?, options?}."""
    system = STUDENT_SYSTEM
    persona = student.get("persona")
    if persona:
        system = f"{STUDENT_SYSTEM}\n\n【你的視角】{persona}"
    user = f"【格式骨架（只照这个结构与标注法写，里面没有任何事实可抄）】\n{STRUCTURE_TEMPLATE}\n\n"
    if lessons:
        user += f"【主编历次纠正的规则（务必遵守）】\n{lessons}\n\n"
    user += (
        f"【今日原始材料（唯一且全部的事实来源）】\n\n{material}\n\n"
        "只用【今日材料】里的事实写今天的简报，按上面的骨架组织。"
        "材料里没有的公司/代号/数字/事件，一律不得出现。"
    )
    return _ollama_chat(
        student["model"], system, user, base_url, options=student.get("options") or {}
    )


# ── mentor panel (main teacher + assistants; all optional) ───────────────────


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of prose/fenced model output."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        logger.warning("model returned no JSON object")
        return {"raw": text}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {"raw": text}


def _anthropic_chat(
    model: str, system: str, user: str, key: str,
    max_tokens: int = 8000, temperature: Optional[float] = None,
) -> str:
    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if temperature is not None:
        payload["temperature"] = temperature
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=300,
    )
    resp.raise_for_status()
    return "".join(b.get("text", "") for b in resp.json().get("content", []))


def _openai_compat_chat(
    base_url: str, model: str, system: str, user: str, key: str,
    temperature: Optional[float] = None,
) -> str:
    """OpenAI-compatible chat completions — serves both OpenAI and xAI."""
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if temperature is not None:
        payload["temperature"] = temperature
    resp = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json=payload,
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or ""


def _panel_chat(
    provider: str, model: str, system: str, user: str,
    config: Optional[Config] = None, temperature: Optional[float] = None,
) -> Optional[str]:
    """Call one panel member. None when the provider key is absent or the call
    fails — a missing assistant must never kill the pipeline."""
    config = config or Config()
    spec = PROVIDERS.get(provider)
    if not spec:
        logger.warning(f"unknown mentor provider: {provider}")
        return None
    key = config.get(spec["key"])  # Config.get falls back to the uppercase env var
    if not key:
        return None
    try:
        if provider == "anthropic":
            return _anthropic_chat(model, system, user, key, temperature=temperature)
        return _openai_compat_chat(spec["base_url"], model, system, user, key, temperature=temperature)
    except Exception as e:  # noqa: BLE001 - panel member failure degrades, not aborts
        logger.warning(f"panel call failed ({provider}/{model}): {e}")
        return None


def _drafts_block(drafts: dict[str, str]) -> str:
    return "\n\n".join(f"【學生 {sid} 的草稿】\n{d}" for sid, d in drafts.items())


def assistant_critique(
    drafts: dict[str, str], material: str, assistant: dict, config: Optional[Config] = None,
) -> Optional[dict]:
    """One assistant scores all drafts on the shared rubric. None if absent."""
    user = f"【今日原始材料】\n{material}\n\n{_drafts_block(drafts)}\n\n请按要求输出 JSON。"
    text = _panel_chat(
        assistant.get("provider", ""), assistant.get("model", ""),
        ASSISTANT_SYSTEM, user, config, temperature=0,
    )
    if text is None:
        return None
    out = _extract_json(text)
    out["assistant"] = assistant.get("name") or assistant.get("model", "")
    return out


def mentor_critique(
    drafts: dict[str, str],
    material: str,
    assistant_notes: Optional[list[dict]] = None,
    config: Optional[Config] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Optional[dict]:
    """Main teacher: per-student scores + gold rewrite, informed by assistant
    critiques. Returns None without an Anthropic key (interactive fallback)."""
    from agent_reach.knowledge import knowledge_rules

    config = config or Config()
    model = model or config.get("radar_mentor_model") or DEFAULT_MENTOR_MODEL
    system = MENTOR_SYSTEM
    rules = knowledge_rules()
    if rules:
        # Terse fact-free methodology rules only — the full KB never reaches
        # the students (they'd plagiarize it), the mentor can hold it.
        system = f"{MENTOR_SYSTEM}\n\n【評審方法論參考】\n{rules}"
    user = f"【今日原始材料】\n{material}\n\n{_drafts_block(drafts)}\n\n"
    for note in assistant_notes or []:
        user += (
            f"【助教 {note.get('assistant', '?')} 的評語】\n"
            f"{json.dumps({k: v for k, v in note.items() if k != 'assistant'}, ensure_ascii=False)}\n\n"
        )
    user += "请按要求输出 JSON。"
    text = _panel_chat("anthropic", model, system, user, config, temperature=temperature)
    if text is None:
        return None
    return _extract_json(text)


# ── orchestration ─────────────────────────────────────────────────────────────


def run_report_pipeline(
    student_model: Optional[str] = None,
    config: Optional[Config] = None,
    when: Optional[datetime] = None,
) -> dict:
    """Collect → every active student drafts → assistants critique → main
    teacher scores per student + writes gold → log the training record.

    ``student_model`` is an ad-hoc single-student override; normally the
    roster (radar-students) decides who drafts.
    """
    config = config or Config()
    when = when or datetime.now(timezone.utc).astimezone()
    base_url = config.get("ollama_base_url") or os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
    stamp = f"{when:%Y-%m-%d-%H%M}"

    # 1) collect (parallel) + 2) assemble material
    _, grouped = run_radar(config=config, when=when)
    material = build_material(grouped)

    # 3) students draft — fact-free structure template + accumulated lessons
    #    (NOT past gold content, which a small student plagiarizes).
    lessons = load_lessons()
    # Pin the real date (the model otherwise hallucinates one from its cutoff).
    lessons = f"简报标题日期必须用：{when:%Y-%m-%d}（不要用你记忆里的日期）\n{lessons}"
    if student_model:
        students = [{"id": student_model, "model": student_model, "options": {}}]
    else:
        students = active_students(load_students())
    drafts: dict[str, str] = {}
    for s in students:
        try:
            logger.info(f"student={s['id']} ({s['model']}) drafting...")
            drafts[s["id"]] = student_draft(material, s, base_url, lessons)
        except Exception as e:  # noqa: BLE001 - one student failing must not kill the run
            logger.warning(f"student {s.get('id')} failed: {e}")
    if not drafts:
        raise RuntimeError(
            "沒有任何學生完成草稿 — 檢查 Ollama 是否在跑、roster 模型是否已 pull"
            f"（ollama_base_url={base_url}）"
        )

    # 4) assistant mentors critique (only those with keys present), then the
    #    main teacher issues per-student scores + the gold rewrite.
    assistants = config.get("radar_assistant_mentors") or DEFAULT_ASSISTANTS
    assistant_notes = []
    for a in assistants:
        note = assistant_critique(drafts, material, a, config)
        if note:
            assistant_notes.append(note)
            logger.info(f"assistant {note.get('assistant')} critiqued")
    critique = mentor_critique(drafts, material, assistant_notes, config)

    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    mentor_ran = critique is not None and "per_student" in (critique or {})
    record = {
        "date": stamp,
        "students": [{"id": s["id"], "model": s["model"]} for s in students],
        "lessons_used": bool(lessons),
        "material_chars": len(material),
        "material": material,  # kept so an interactive mentor can read the students' input
        "drafts": drafts,
        "assistant_critiques": assistant_notes,
        "critique": critique,
        "mentor_ran": mentor_ran,
    }
    rec_path = TRAINING_DIR / f"{stamp}.json"
    rec_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5) persist gold + per-student scores for the feedback loop / leaderboard
    if critique and critique.get("gold_report"):
        GOLD_DIR.mkdir(parents=True, exist_ok=True)
        (GOLD_DIR / f"{stamp}.md").write_text(critique["gold_report"], encoding="utf-8")
    if mentor_ran:
        model_by_id = {s["id"]: s["model"] for s in students}
        with open(SCORES_FILE, "a", encoding="utf-8") as f:
            for sid, entry in (critique.get("per_student") or {}).items():
                if not isinstance(entry, dict):
                    continue
                f.write(json.dumps({
                    "date": stamp,
                    "student_id": sid,
                    "model": model_by_id.get(sid, ""),
                    "total": entry.get("total"),
                    **(entry.get("scores") or {}),
                }, ensure_ascii=False) + "\n")

    record["record_path"] = str(rec_path)
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
