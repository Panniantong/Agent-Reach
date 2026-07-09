# -*- coding: utf-8 -*-
"""Autoresearch-style self-evolve harness for the radar.

THIS FILE IS THE FIXED HARNESS — the evolve agent must never modify it
(enforced by the allowlist diff-guard AND a SHA-256 manifest check every
cycle). Mapping to karpathy/autoresearch:

    prepare.py + val_bpb  →  this harness + eval_candidate() on frozen fixtures
    train.py              →  ALLOWED_FILES (evolve/radar.yaml, radar.py,
                             radar_report.py, radar_arxiv.py)
    program.md            →  evolve/program.md (human-edited only)
    experiment log        →  evolve/journal.jsonl (+ journal.md view)

One experiment = one mutation of ONE allowed file, gated cheap→expensive:
pytest (frozen tests) → collector health (offline invariants on frozen
feeds) → rubric eval (pinned student + pinned mentor, temperature 0, on
frozen held-out material). ``keep`` iff the mean rubric total beats the
baseline by EPSILON; keeps fast-forward the ``radar-evolve`` branch, the
user's checkout and config are never touched. Kill switch: evolve/STOP.
Merging kept work into main stays a HUMAN decision (PR), per CLAUDE.md.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from loguru import logger

from agent_reach.config import Config

REPO_ROOT = Path(__file__).resolve().parents[1]
EVOLVE_DIR = REPO_ROOT / "evolve"
FIXTURES_DIR = EVOLVE_DIR / "fixtures"
HELDOUT_DIR = FIXTURES_DIR / "heldout"
FEEDS_DIR = FIXTURES_DIR / "feeds"
MANIFEST_FILE = FIXTURES_DIR / "manifest.json"
JOURNAL_FILE = EVOLVE_DIR / "journal.jsonl"
JOURNAL_MD = EVOLVE_DIR / "journal.md"
STOP_FILE = EVOLVE_DIR / "STOP"
PROGRAM_FILE = EVOLVE_DIR / "program.md"

DEFAULT_BASE_BRANCH = "radar-evolve"
DEFAULT_EPSILON = 1.0

# What the agent may edit (repo-relative, posix). Everything else is illegal.
ALLOWED_FILES = frozenset({
    "evolve/radar.yaml",
    "agent_reach/radar.py",
    "agent_reach/radar_report.py",
    "agent_reach/radar_arxiv.py",
})
# Hash-verified every cycle (fixtures/** is added dynamically).
PROTECTED_FILES = (
    "agent_reach/radar_evolve.py",
    "evolve/program.md",
)

PROPOSER_SYSTEM = """你是雷達系統的實驗設計者。根據 program.md 的目標、實驗日誌與目前檔案內容，
提出「一個」最有希望提升評分的變更。單一變因：只改一個檔案、一件事。

嚴格只輸出一個 JSON 物件：
{
  "file": "<必須是允許清單中的路徑>",
  "kind": "config|prompt|code",
  "hypothesis": "一句話：改了什麼、為什麼預期評分會升",
  "new_content": "該檔案的完整新內容（整檔覆蓋）"
}

規則：
- 不得動測試、fixtures、program.md、radar_evolve.py（動了會被丟棄並記錄違規）。
- 改 code 時保持所有既有函數簽名不變（health gate 會驗）。
- 從日誌學習：重複已被丟棄的假設是浪費預算。"""


# ── primitives ────────────────────────────────────────────────────────────


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git(args: list[str], cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess:
    git_bin = shutil.which("git") or "git"
    return subprocess.run(
        [git_bin, *args],
        cwd=str(cwd),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def compute_manifest_hashes(repo_root: Path = REPO_ROOT) -> dict[str, str]:
    """SHA-256 of the harness + program.md + every fixture (manifest excluded)."""
    hashes: dict[str, str] = {}
    for rel in PROTECTED_FILES:
        p = repo_root / rel
        if p.exists():
            hashes[rel] = _sha256(p)
    fixtures = repo_root / "evolve" / "fixtures"
    if fixtures.exists():
        for p in sorted(fixtures.rglob("*")):
            if p.is_file() and p.name != "manifest.json":
                hashes[p.relative_to(repo_root).as_posix()] = _sha256(p)
    return hashes


def load_manifest(repo_root: Path = REPO_ROOT) -> Optional[dict]:
    mf = repo_root / "evolve" / "fixtures" / "manifest.json"
    if not mf.exists():
        return None
    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def verify_manifest(repo_root: Path = REPO_ROOT) -> tuple[bool, str]:
    """The eval-gaming tripwire: harness/fixtures/program must match the freeze."""
    manifest = load_manifest(repo_root)
    if not manifest:
        return False, "manifest.json 不存在或損毀 — 先跑 radar-evolve freeze"
    expected = manifest.get("hashes") or {}
    actual = compute_manifest_hashes(repo_root)
    if expected != actual:
        drift = sorted(set(expected) ^ set(actual)) or [
            k for k in expected if expected.get(k) != actual.get(k)
        ]
        return False, f"受保護檔案被改動: {drift[:5]} — 拒絕執行"
    return True, "ok"


@dataclass
class Mutation:
    file: str
    new_content: str
    hypothesis: str
    kind: str  # config | prompt | code


def _mutation_allowed(changed_paths: list[str]) -> bool:
    """Every changed path must sit inside the allowlist (posix-normalized)."""
    if not changed_paths:
        return False
    return all(p.replace("\\", "/").strip() in ALLOWED_FILES for p in changed_paths if p.strip())


def decide(base: float, cand: float, epsilon: float = DEFAULT_EPSILON) -> str:
    return "keep" if cand >= base + epsilon else "discard"


# ── journal ───────────────────────────────────────────────────────────────


def append_journal(record: dict, journal: Path = JOURNAL_FILE) -> None:
    journal.parent.mkdir(parents=True, exist_ok=True)
    with open(journal, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_journal(journal: Path = JOURNAL_FILE) -> list[dict]:
    if not journal.exists():
        return []
    out = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def journal_tail_text(n: int = 12, journal: Path = JOURNAL_FILE) -> str:
    rows = [r for r in read_journal(journal) if r.get("id")][-n:]
    lines = []
    for r in rows:
        lines.append(
            f"- {r.get('id')} [{r.get('decision')}] {r.get('file', '')}: {r.get('hypothesis', '')}"
            f" (base={r.get('base_score')}, cand={r.get('cand_score')})"
        )
    return "\n".join(lines)


def rebuild_journal_md(journal: Path = JOURNAL_FILE, out: Path = JOURNAL_MD) -> None:
    rows = [r for r in read_journal(journal) if r.get("id")]
    lines = [
        "# 🧬 Radar evolve journal", "",
        "| id | decision | file | hypothesis | base | cand | pytest | health |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.get('id')} | {r.get('decision')} | {r.get('file', '')} "
            f"| {str(r.get('hypothesis', '')).replace('|', '/')[:80]} "
            f"| {r.get('base_score')} | {r.get('cand_score')} "
            f"| {'✓' if r.get('pytest_ok') else '✗'} | {'✓' if r.get('health_ok') else '✗'} |"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cached_baseline(base_sha: str, journal: Path = JOURNAL_FILE) -> Optional[float]:
    for r in reversed(read_journal(journal)):
        if r.get("baseline_sha") == base_sha and r.get("score") is not None:
            return float(r["score"])
    return None


# ── mutation proposal (main teacher) ─────────────────────────────────────


def propose_mutation(
    program: str,
    journal_tail: str,
    target_files: dict[str, str],
    config: Optional[Config] = None,
) -> Optional[Mutation]:
    """Ask the main teacher for ONE single-variable mutation. None on any failure."""
    from agent_reach.radar_report import DEFAULT_MENTOR_MODEL, _extract_json, _panel_chat

    config = config or Config()
    model = config.get("radar_mentor_model") or DEFAULT_MENTOR_MODEL
    user = f"【program.md（人類目標與規則）】\n{program}\n\n"
    if journal_tail:
        user += f"【實驗日誌（最近）】\n{journal_tail}\n\n"
    user += f"【允許修改的檔案清單】\n{sorted(ALLOWED_FILES)}\n\n"
    for rel, content in target_files.items():
        user += f"【目前 {rel}】\n```\n{content[:14000]}\n```\n\n"
    user += "請輸出 JSON。"
    text = _panel_chat("anthropic", model, PROPOSER_SYSTEM, user, config)
    if not text:
        return None
    data = _extract_json(text)
    file, content = data.get("file", ""), data.get("new_content", "")
    if file not in ALLOWED_FILES or not isinstance(content, str) or not content.strip():
        logger.warning(f"proposer returned invalid mutation (file={file!r})")
        return None
    return Mutation(
        file=file,
        new_content=content,
        hypothesis=str(data.get("hypothesis", ""))[:300],
        kind=str(data.get("kind", "config")),
    )


# ── gates (all run INSIDE the candidate worktree) ────────────────────────

_IMPORT_GUARD = (
    "import sys, json; from pathlib import Path\n"
    "worktree = Path(sys.argv[1]).resolve()\n"
    "sys.path.insert(0, str(worktree))\n"
    "import agent_reach\n"
    "assert Path(agent_reach.__file__).resolve().as_posix().startswith(worktree.as_posix()), "
    "'wrong agent_reach imported: ' + agent_reach.__file__\n"
)

# The candidate worktree ONLY produces the draft. Scoring happens in THIS
# fixed harness with the frozen rubric below — otherwise a mutation could
# game the eval by rewriting the mentor prompt to hand out high scores.
EVAL_SCRIPT = _IMPORT_GUARD + """
fixture_path, student_json, base_url = sys.argv[2:5]
from agent_reach.radar_report import student_draft
rec = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
student = json.loads(student_json)
draft = student_draft(rec["material"], student, base_url, lessons="")
print("EVOLVE_RESULT " + json.dumps({"draft": draft}, ensure_ascii=False))
"""

# Frozen grading rubric — hash-protected with the rest of this file.
EVAL_MENTOR_SYSTEM = """你是投研簡報評審。下面給你【原始材料】與【簡報草稿】。
按 rubric 對草稿獨立評分。嚴格只輸出一個 JSON 物件：
{"scores": {"coverage": 0-100, "accuracy": 0-100, "depth": 0-100, "lens_application": 0-100, "actionability": 0-100}, "total": 0-100}
維度：coverage=覆蓋材料中真正重要的信號；accuracy=無臆造/與材料矛盾；depth=串聯因果、非顯然洞察；
lens_application=正確應用反指/喊單透鏡；actionability=要點可操作。評分要嚴格、可重複。"""


def _mentor_score(draft: str, material: str, mentor_model: str, config: Config) -> Optional[float]:
    """Score one draft with the FROZEN rubric (runs in the harness, not the candidate)."""
    from agent_reach.radar_report import _extract_json, _panel_chat

    user = f"【原始材料】\n{material}\n\n【簡報草稿】\n{draft}\n\n請輸出 JSON。"
    text = _panel_chat("anthropic", mentor_model, EVAL_MENTOR_SYSTEM, user, config, temperature=0)
    if not text:
        return None
    total = _extract_json(text).get("total")
    return float(total) if isinstance(total, (int, float)) else None

HEALTH_SCRIPT = _IMPORT_GUARD + """
feeds_dir = Path(sys.argv[2])
ok, reasons = True, []
try:
    from agent_reach.radar import Item, _dedupe, collect_rss
    import agent_reach.radar_arxiv as ra

    rss_xml = (feeds_dir / "rss_sample.xml").read_text(encoding="utf-8")
    items = collect_rss({"rss_feeds": [rss_xml], "rss_per_feed": 10})
    if not items:
        ok, reasons = False, reasons + ["rss: no items from frozen feed"]
    elif not all(i.title and i.url for i in items):
        ok, reasons = False, reasons + ["rss: item missing title/url"]

    a = Item(source="s", kind="rss", title="t", url="https://u/1")
    b = Item(source="s", kind="rss", title="t", url="https://u/1")
    if len(_dedupe([a, b])) != 1:
        ok, reasons = False, reasons + ["dedupe invariant broken"]

    ax_xml = (feeds_dir / "arxiv_sample.xml").read_text(encoding="utf-8")
    ra._arxiv_query_url = lambda cats, n: ax_xml  # feed the frozen XML through the real path
    papers = ra.collect_arxiv({"arxiv_categories": ["cs.AI"], "arxiv_keywords": {"kv cache": 3}}, None)
    if not papers:
        ok, reasons = False, reasons + ["arxiv: on-topic paper did not survive the gate"]
    if any("basket" in p.title.lower() for p in papers):
        ok, reasons = False, reasons + ["arxiv: off-topic paper passed the gate"]
except Exception as e:
    ok, reasons = False, [f"health crashed: {e}"]
print("EVOLVE_HEALTH " + json.dumps({"ok": ok, "reasons": reasons}))
"""


def _parse_tagged_json(output: str, tag: str) -> Optional[dict]:
    for line in reversed((output or "").splitlines()):
        if line.startswith(tag + " "):
            try:
                return json.loads(line[len(tag) + 1:])
            except json.JSONDecodeError:
                return None
    return None


def _run_py(script: str, argv: list[str], cwd: Path, timeout: int) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script, *argv],
            cwd=str(cwd),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001
        return False, f"subprocess failed: {e}"
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def run_pytest_gate(worktree: Path, timeout: int = 1200) -> bool:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q", "-x"],
            cwd=str(worktree),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"pytest gate crashed: {e}")
        return False
    if proc.returncode != 0:
        logger.warning(f"pytest gate failed:\n{(proc.stdout or '')[-800:]}")
    return proc.returncode == 0


def collector_health(worktree: Path, timeout: int = 300) -> bool:
    ok, output = _run_py(HEALTH_SCRIPT, [str(worktree), str(worktree / "evolve" / "fixtures" / "feeds")], worktree, timeout)
    result = _parse_tagged_json(output, "EVOLVE_HEALTH")
    if not ok or not result:
        logger.warning(f"health gate crashed: {output[-500:]}")
        return False
    if not result.get("ok"):
        logger.warning(f"health gate failed: {result.get('reasons')}")
    return bool(result.get("ok"))


def eval_candidate(
    worktree: Path,
    fixtures: list[Path],
    pinned_student: dict,
    mentor_model: str,
    config: Optional[Config] = None,
    timeout_per_fixture: int = 1200,
) -> Optional[float]:
    """Mean frozen-rubric total over the frozen fixtures. None on any failure.

    Candidate code drafts (pinned student, temperature 0); the harness
    grades with its own frozen rubric + pinned mentor at temperature 0.
    """
    import os as _os

    config = config or Config()
    base_url = config.get("ollama_base_url") or _os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
    totals: list[float] = []
    for fx in fixtures:
        ok, output = _run_py(
            EVAL_SCRIPT,
            [str(worktree), str(fx), json.dumps(pinned_student), base_url],
            worktree,
            timeout_per_fixture,
        )
        result = _parse_tagged_json(output, "EVOLVE_RESULT")
        draft = (result or {}).get("draft")
        if not ok or not draft:
            logger.warning(f"eval draft failed on {fx.name}: {output[-400:]}")
            return None
        material = json.loads(fx.read_text(encoding="utf-8")).get("material", "")
        total = _mentor_score(draft, material, mentor_model, config)
        if total is None:
            logger.warning(f"eval scoring failed on {fx.name}")
            return None
        totals.append(total)
        logger.info(f"eval {fx.name}: {total}")
    return round(sum(totals) / len(totals), 2) if totals else None


# ── experiment cycle ──────────────────────────────────────────────────────


def _worktree_base(repo_root: Path) -> Path:
    return repo_root.parent / f"{repo_root.name}-evolve"


def _cleanup_worktree(repo_root: Path, wt_path: Path, branch: str) -> None:
    _git(["worktree", "remove", "--force", str(wt_path)], cwd=repo_root)
    _git(["branch", "-D", branch], cwd=repo_root)


def run_experiment(
    exp_id: str,
    base_branch: str = DEFAULT_BASE_BRANCH,
    config: Optional[Config] = None,
    repo_root: Path = REPO_ROOT,
    epsilon: float = DEFAULT_EPSILON,
    dry_run: bool = False,
) -> dict:
    """One full cycle: worktree → baseline → mutate → gates → keep/discard."""
    config = config or Config()
    record: dict = {
        "id": exp_id,
        "ts": f"{datetime.now(timezone.utc).isoformat()}",
        "decision": "error",
        "pytest_ok": False,
        "health_ok": False,
        "base_score": None,
        "cand_score": None,
    }
    ok, msg = verify_manifest(repo_root)
    if not ok:
        record["decision"] = "abort:manifest"
        record["error"] = msg
        return record

    manifest = load_manifest(repo_root) or {}
    pinned_student = manifest.get("pinned_student") or {}
    mentor_model = manifest.get("pinned_mentor") or "claude-fable-5"
    heldout = repo_root / "evolve" / "fixtures" / "heldout"
    fixtures = sorted(heldout.glob("*.json"))
    if not fixtures or not pinned_student:
        record["decision"] = "abort:no_fixtures"
        record["error"] = "缺 heldout fixtures 或 pinned student — 先跑 radar-evolve freeze"
        return record

    rp = _git(["rev-parse", base_branch], cwd=repo_root)
    if rp.returncode != 0:
        record["decision"] = "abort:no_base_branch"
        record["error"] = f"base branch 不存在: {base_branch}"
        return record
    base_sha = rp.stdout.strip()

    branch = f"evolve/exp-{exp_id}"
    wt_path = _worktree_base(repo_root) / f"exp-{exp_id}"
    wt_path.parent.mkdir(parents=True, exist_ok=True)
    add = _git(["worktree", "add", str(wt_path), "-b", branch, base_sha], cwd=repo_root)
    if add.returncode != 0:
        record["decision"] = "abort:worktree"
        record["error"] = (add.stderr or "")[-300:]
        return record

    try:
        # Baseline on pristine base code (cached per base SHA).
        base_score = cached_baseline(base_sha)
        if base_score is None:
            logger.info(f"computing baseline for {base_sha[:8]}...")
            base_score = eval_candidate(wt_path, fixtures, pinned_student, mentor_model, config)
            if base_score is None:
                record["decision"] = "abort:baseline_failed"
                return record
            append_journal({"baseline_sha": base_sha, "score": base_score,
                            "ts": f"{datetime.now(timezone.utc).isoformat()}"})
        record["base_score"] = base_score

        # Propose ONE mutation from the worktree's current file contents.
        program = PROGRAM_FILE.read_text(encoding="utf-8") if PROGRAM_FILE.exists() else ""
        targets = {
            rel: (wt_path / rel).read_text(encoding="utf-8")
            for rel in sorted(ALLOWED_FILES)
            if (wt_path / rel).exists()
        }
        mutation = propose_mutation(program, journal_tail_text(), targets, config)
        if mutation is None:
            record["decision"] = "abort:no_proposal"
            return record
        record["file"] = mutation.file
        record["kind"] = mutation.kind
        record["hypothesis"] = mutation.hypothesis

        target = wt_path / mutation.file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(mutation.new_content, encoding="utf-8")

        # Diff guard — the only authority on what changed is git itself.
        st = _git(["status", "--porcelain"], cwd=wt_path)
        changed = [line[3:].strip().strip('"') for line in st.stdout.splitlines() if line.strip()]
        if not _mutation_allowed(changed):
            record["decision"] = "discard:illegal_files"
            record["changed"] = changed
            return record

        # Gates, cheap → expensive.
        record["pytest_ok"] = run_pytest_gate(wt_path)
        if not record["pytest_ok"]:
            record["decision"] = "discard:pytest"
            return record
        record["health_ok"] = collector_health(wt_path)
        if not record["health_ok"]:
            record["decision"] = "discard:health"
            return record
        cand = eval_candidate(wt_path, fixtures, pinned_student, mentor_model, config)
        if cand is None:
            record["decision"] = "discard:eval_failed"
            return record
        record["cand_score"] = cand

        record["decision"] = decide(base_score, cand, epsilon)
        if record["decision"] == "keep" and not dry_run:
            body = f"evolve(radar): {mutation.hypothesis}\n\nbase={base_score} cand={cand} (+{round(cand - base_score, 2)})"
            _git(["add", "-A"], cwd=wt_path)
            cm = _git(["commit", "-m", body], cwd=wt_path)
            if cm.returncode != 0:
                record["decision"] = "error"
                record["error"] = (cm.stderr or "")[-300:]
                return record
            new_sha = _git(["rev-parse", "HEAD"], cwd=wt_path).stdout.strip()
            parent = _git(["rev-parse", "HEAD~1"], cwd=wt_path).stdout.strip()
            if parent != base_sha:
                record["decision"] = "error"
                record["error"] = "non-fast-forward keep refused"
                return record
            # Fast-forward the base branch without touching the user's checkout.
            ff = _git(["update-ref", f"refs/heads/{base_branch}", new_sha, base_sha], cwd=repo_root)
            if ff.returncode != 0:
                record["decision"] = "error"
                record["error"] = (ff.stderr or "")[-300:]
                return record
            record["commit"] = new_sha
        elif record["decision"] == "keep" and dry_run:
            record["decision"] = "keep:dry_run"
        return record
    finally:
        _cleanup_worktree(repo_root, wt_path, branch)
        append_journal(record)
        rebuild_journal_md()


# ── freeze + preflight + loop ─────────────────────────────────────────────


def freeze(
    from_training: int = 5,
    repo_root: Path = REPO_ROOT,
    config: Optional[Config] = None,
) -> dict:
    """Build the frozen eval set from real training records and pin the graders.

    Pins the CURRENT leaderboard top student (temperature 0, fixed seed) and
    the main mentor model into manifest.json so the metric never drifts as
    the roster evolves.
    """
    from agent_reach.radar import RADAR_DIR
    from agent_reach.radar_report import DEFAULT_MENTOR_MODEL
    from agent_reach.radar_students import active_students, leaderboard, load_students, student_scores

    config = config or Config()
    training = RADAR_DIR / "training"
    records = sorted(training.glob("2*.json"), reverse=True)
    materials: list[dict] = []
    for rec_path in records:
        try:
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if rec.get("material"):
            materials.append({"date": rec.get("date", rec_path.stem), "material": rec["material"]})
        if len(materials) >= from_training:
            break
    if not materials:
        raise RuntimeError(f"沒有可用的 training 紀錄（{training}）— 先跑幾次 radar-report")

    heldout = repo_root / "evolve" / "fixtures" / "heldout"
    if heldout.exists():
        shutil.rmtree(heldout)
    heldout.mkdir(parents=True, exist_ok=True)
    for i, m in enumerate(materials, 1):
        (heldout / f"fixture-{i:02d}.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    students = active_students(load_students())
    if not students:
        raise RuntimeError("student roster 為空")
    board = leaderboard(students, student_scores())
    top_id = board[0]["id"] if board and board[0]["rolling_mean"] is not None else students[0]["id"]
    pinned = next((s for s in students if s["id"] == top_id), students[0])
    pinned_student = {
        "id": "eval-pinned",
        "model": pinned["model"],
        "persona": pinned.get("persona", ""),
        "options": {"temperature": 0, "seed": 42},
    }
    mentor_model = config.get("radar_mentor_model") or DEFAULT_MENTOR_MODEL

    manifest = {
        "frozen_at": f"{datetime.now(timezone.utc):%Y-%m-%d}",
        "pinned_student": pinned_student,
        "pinned_mentor": mentor_model,
        "fixtures": [p.name for p in sorted(heldout.glob('*.json'))],
    }
    mf = repo_root / "evolve" / "fixtures" / "manifest.json"
    mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # Hash AFTER writing fixtures so the manifest seals exactly what's on disk.
    manifest["hashes"] = compute_manifest_hashes(repo_root)
    mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"froze {len(materials)} fixtures, pinned student={pinned_student['model']}, mentor={mentor_model}")
    return manifest


def preflight(config: Optional[Config] = None, repo_root: Path = REPO_ROOT) -> tuple[bool, str]:
    import os as _os

    config = config or Config()
    if STOP_FILE.exists():
        return False, "evolve/STOP 存在 — 移除後再跑"
    if not (config.get("anthropic_api_key") or _os.environ.get("ANTHROPIC_API_KEY")):
        return False, "缺 ANTHROPIC_API_KEY（主師負責提案與評分）"
    ok, msg = verify_manifest(repo_root)
    if not ok:
        return False, msg
    base_url = config.get("ollama_base_url") or _os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
    try:
        requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
    except Exception:  # noqa: BLE001
        return False, f"Ollama 不可達（{base_url}）— 評測學生跑不起來"
    st = _git(["status", "--porcelain"], cwd=repo_root)
    if st.returncode != 0:
        return False, "git 不可用"
    return True, "ok"


def run_evolve(
    budget: int = 5,
    base_branch: str = DEFAULT_BASE_BRANCH,
    epsilon: float = DEFAULT_EPSILON,
    dry_run: bool = False,
    max_minutes: Optional[int] = None,
    config: Optional[Config] = None,
    repo_root: Path = REPO_ROOT,
) -> list[dict]:
    """The overnight loop: N experiments against a fixed metric, keep or discard."""
    config = config or Config()
    ok, msg = preflight(config, repo_root)
    if not ok:
        raise RuntimeError(f"preflight 失敗: {msg}")
    # Base branch = accumulation point for kept experiments (human PRs it later).
    if _git(["rev-parse", "--verify", base_branch], cwd=repo_root).returncode != 0:
        cur = _git(["rev-parse", "HEAD"], cwd=repo_root).stdout.strip()
        _git(["branch", base_branch, cur], cwd=repo_root)
        logger.info(f"created base branch {base_branch} at {cur[:8]}")

    started = time.monotonic()
    results: list[dict] = []
    stamp = f"{datetime.now(timezone.utc):%Y%m%d-%H%M}"
    for i in range(1, budget + 1):
        if STOP_FILE.exists():
            logger.info("STOP file present — halting")
            break
        if max_minutes and (time.monotonic() - started) > max_minutes * 60:
            logger.info("time budget exhausted — halting")
            break
        exp_id = f"{stamp}-{i:02d}"
        logger.info(f"=== experiment {exp_id} ({i}/{budget}) ===")
        rec = run_experiment(exp_id, base_branch, config, repo_root, epsilon, dry_run)
        results.append(rec)
        logger.info(f"experiment {exp_id}: {rec.get('decision')} "
                    f"(base={rec.get('base_score')}, cand={rec.get('cand_score')})")
        if str(rec.get("decision", "")).startswith("abort"):
            break
    return results
