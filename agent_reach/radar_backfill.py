# -*- coding: utf-8 -*-
"""Guru backfill: historical X posts + key repo files → distilled knowledge.

Raw material is written to ``~/.agent-reach/radar/backfill`` (local only,
never committed). ``distill_knowledge`` turns it into a methodology
knowledge base draft; a human reviews it and commits it under
``agent_reach/knowledge/``. Glue-layer rules apply: X via the ``twitter``
CLI, GitHub via ``gh`` (Jina Reader fallback), no scraping.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger

from agent_reach.config import Config
from agent_reach.radar import (
    RADAR_DIR,
    Item,
    _run_twitter_json,
    _tweet_to_item,
    _twitter_env,
)

BACKFILL_DIR = RADAR_DIR / "backfill"

DEFAULT_REPOS = ["karpathy/autoresearch", "karpathy/nanochat"]
# The files that carry each repo's design essence (README always included).
REPO_KEY_FILES = {
    "karpathy/autoresearch": ["prepare.py", "train.py", "program.md"],
    "karpathy/nanochat": ["speedrun.sh"],
}

DISTILL_SYSTEM = """你是方法論蒸餾者。下面是某位技術大神的歷史 X posts 與代表性 repo 的原始碼/文件。
把它蒸餾成一份「方法論知識庫」markdown，用繁體中文，結構嚴格如下：

# <人名> 方法論知識庫
## 核心原則（自動迭代）
- 5-8 條，每條講清楚原則本身 + 為什麼成立（從材料中歸納，不要泛泛而談）。
## 精要規則
- 7-10 條 terse、無事實內容的行動規則（這段會餵給評審模型的 system prompt，
  不得含任何公司名/數字/日期，只留可遷移的做事方法）。
## 實驗設計模式
- 材料中出現的實驗/工程設計模式，表格或條列。
## 原始出處索引
- 逐條列出你引用的 repo 檔案與 posts 連結。

硬性要求：每條原則都要能在材料中找到根據；材料裡沒有的不要編。"""


# ── collectors ────────────────────────────────────────────────────────────


def backfill_twitter(handle: str, count: int, config: Optional[Config] = None) -> list[Item]:
    """Pull as much of a handle's timeline as the twitter CLI exposes; save raw JSONL."""
    config = config or Config()
    env = _twitter_env(config)
    if env is None:
        logger.warning("Twitter not configured (no auth_token/ct0); skipping backfill")
        return []
    handle = handle.lstrip("@")
    rows = _run_twitter_json(["user-posts", f"@{handle}", "-n", str(count)], env, timeout=120)
    items: list[Item] = []
    for t in rows:
        it = _tweet_to_item(t, source=f"twitter:@{handle}")
        if it:
            items.append(it)
    if items:
        BACKFILL_DIR.mkdir(parents=True, exist_ok=True)
        out = BACKFILL_DIR / f"{handle}-tweets.jsonl"
        with open(out, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(vars(it), ensure_ascii=False) + "\n")
        logger.info(f"backfilled {len(items)} posts from @{handle} → {out}")
    return items


def _gh(args: list[str], timeout: int = 60) -> str:
    """Run `gh <args>`; empty string on any failure (never raises)."""
    gh_bin = shutil.which("gh")
    if not gh_bin:
        logger.warning("gh CLI not on PATH")
        return ""
    try:
        proc = subprocess.run(
            [gh_bin, *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"gh {' '.join(args[:3])}... failed: {e}")
        return ""
    if proc.returncode != 0:
        logger.warning(f"gh {' '.join(args[:3])}...: {(proc.stderr or '').strip()[:200]}")
        return ""
    return proc.stdout or ""


def _fetch_raw_fallback(repo: str, path: str) -> str:
    """Jina Reader on raw.githubusercontent.com when gh is unavailable."""
    from agent_reach.channels.web import WebChannel

    for branch in ("main", "master"):
        try:
            text = WebChannel().read(f"https://raw.githubusercontent.com/{repo}/{branch}/{path}")
        except Exception:  # noqa: BLE001
            continue
        if text and len(text.strip()) > 50:
            return text
    return ""


def backfill_github_repo(repo: str, key_files: Optional[list[str]] = None) -> dict:
    """Repo metadata + README + key files via gh CLI (Jina fallback). Never raises."""
    key_files = key_files if key_files is not None else REPO_KEY_FILES.get(repo, [])
    meta_raw = _gh(["repo", "view", repo, "--json", "name,description,stargazerCount,updatedAt"])
    try:
        meta = json.loads(meta_raw) if meta_raw else {}
    except json.JSONDecodeError:
        meta = {}
    files: dict[str, str] = {}
    readme = _gh(["api", f"repos/{repo}/readme", "-H", "Accept: application/vnd.github.raw"])
    if not readme:
        readme = _fetch_raw_fallback(repo, "README.md")
    if readme:
        files["README.md"] = readme
    for path in key_files:
        text = _gh(["api", f"repos/{repo}/contents/{path}", "-H", "Accept: application/vnd.github.raw"])
        if not text:
            text = _fetch_raw_fallback(repo, path)
        if text:
            files[path] = text
    result = {"repo": repo, "meta": meta, "files": files}
    if files:
        BACKFILL_DIR.mkdir(parents=True, exist_ok=True)
        out = BACKFILL_DIR / f"{repo.replace('/', '__')}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"backfilled {repo}: {list(files)} → {out}")
    return result


# ── distillation ──────────────────────────────────────────────────────────


def assemble_distill_material(
    tweets: list[Item],
    repos: list[dict],
    max_chars: int = 60000,
) -> str:
    """Compact raw backfill into LLM-ready distillation material (pure)."""
    lines: list[str] = []
    for r in repos:
        meta = r.get("meta") or {}
        lines.append(f"## Repo: {r.get('repo')}")
        if meta:
            lines.append(f"({meta.get('description', '')} · ⭐ {meta.get('stargazerCount', '?')})")
        for path, text in (r.get("files") or {}).items():
            lines.append(f"\n### {path}\n{text[:12000]}")
        lines.append("")
    if tweets:
        lines.append("## 歷史 X posts（節錄）")
        for it in tweets:
            body = " ".join(it.text.split())
            lines.append(f"- [{it.ts or '?'}] {body[:500]}")
    return "\n".join(lines)[:max_chars]


def distill_knowledge(
    material: str,
    config: Optional[Config] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """Distill the knowledge-base draft with the main teacher. None without a key."""
    from agent_reach.radar_report import DEFAULT_MENTOR_MODEL, _panel_chat

    config = config or Config()
    model = model or config.get("radar_mentor_model") or DEFAULT_MENTOR_MODEL
    return _panel_chat("anthropic", model, DISTILL_SYSTEM, material, config)


def run_backfill(
    handle: str = "karpathy",
    repos: Optional[list[str]] = None,
    count: int = 300,
    distill: bool = False,
    out_path: Optional[Path] = None,
    config: Optional[Config] = None,
) -> dict:
    """Backfill one guru; optionally distill into a knowledge-base draft."""
    config = config or Config()
    repos = repos if repos is not None else DEFAULT_REPOS
    tweets = backfill_twitter(handle, count, config) if handle else []
    repo_data = [backfill_github_repo(r) for r in repos]
    repo_data = [r for r in repo_data if r.get("files")]
    result: dict = {
        "handle": handle,
        "tweets": len(tweets),
        "repos": {r["repo"]: list(r["files"]) for r in repo_data},
        "backfill_dir": str(BACKFILL_DIR),
    }
    if distill:
        material = assemble_distill_material(tweets, repo_data)
        draft = distill_knowledge(material, config)
        if draft:
            out = Path(out_path) if out_path else BACKFILL_DIR / f"{handle or 'knowledge'}-kb-draft.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(draft, encoding="utf-8")
            result["kb_draft"] = str(out)
        else:
            result["kb_draft"] = None
    return result
