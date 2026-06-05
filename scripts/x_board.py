#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""X Board — a local, self-contained HTML viewer for fetched X (Twitter) posts.

Reads a user-edited follow-list (one @handle per line), fetches each person's
recent *original* posts through the already-installed ``twitter-cli``, and writes
a single self-contained HTML page (auto-opened in the browser). The page both
displays the posts and proves the fetch worked: each account gets an
"N posts fetched" badge and the page header shows an overall status line.

This is a read-only glue-layer helper. It does NOT modify Agent-Reach or any
upstream source, adds no new runtime dependencies (stdlib only for parsing and
rendering), and involves no LLM. Cookies are loaded from
``~/.agent-reach/config.yaml`` exactly as ``agent-reach configure`` wrote them,
mirroring the pattern in ``scripts/verify_twitter.ps1``. Credentials are never
written into the output HTML.

Usage (run with the Agent-Reach venv interpreter so ``twitter`` is on PATH):

    python scripts/x_board.py
    python scripts/x_board.py --file ~/.agent-reach/follow.txt -n 10
    python scripts/x_board.py --out ~/.agent-reach/x-board.html --no-open

Exit codes:
    0  all accounts fetched OK
    1  partial — some (or all) accounts errored; the page is still written/opened
    2  setup error — no cookies configured, or the follow-list is missing/empty
"""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

# Defaults live under ~/.agent-reach/ so the git clone stays clean (KTD6).
DEFAULT_FOLLOW_FILE = Path.home() / ".agent-reach" / "follow.txt"
DEFAULT_OUTPUT_FILE = Path.home() / ".agent-reach" / "x-board.html"
# Repo-relative pointer shown in error messages (not used to read at runtime).
SAMPLE_FOLLOW_FILE = "scripts/follow.sample.txt"


class XBoardError(Exception):
    """A setup/precondition failure (missing cookies or follow-list).

    Raised only for whole-run problems that should stop before fetching. Per-handle
    fetch failures are captured on :class:`AccountResult`, never raised.
    """


# ── Input layer (U1) ────────────────────────────────────────────────────────


def load_cookies(config: Any = None) -> Tuple[str, str]:
    """Return ``(auth_token, ct0)`` from Agent-Reach config.

    Uses ``agent_reach.config.Config`` so it reads exactly what
    ``agent-reach configure twitter-cookies`` wrote, and inherits Config's
    uppercase env-var fallback (``TWITTER_AUTH_TOKEN`` / ``TWITTER_CT0``).

    Raises :class:`XBoardError` with a remediation hint when either is absent.
    """
    if config is None:
        try:
            from agent_reach.config import Config
        except ImportError as exc:  # pragma: no cover - environment guard
            raise XBoardError(
                "Could not import agent_reach. Run X Board with the Agent-Reach "
                "venv interpreter (e.g. ~/.agent-reach-venv/Scripts/python.exe)."
            ) from exc
        config = Config()

    auth_token = config.get("twitter_auth_token")
    ct0 = config.get("twitter_ct0")
    if not auth_token or not ct0:
        raise XBoardError(
            "No Twitter/X cookies found in ~/.agent-reach/config.yaml.\n"
            '  Fix: agent-reach configure twitter-cookies "auth_token=...; ct0=..."\n'
            "  Export the header string from a dedicated/burner X account via Cookie-Editor."
        )
    return str(auth_token), str(ct0)


def parse_follow_list(path: Any) -> List[str]:
    """Parse a follow-list file into a clean, ordered, de-duplicated handle list.

    One handle per line; a leading ``@`` is optional. Blank lines and lines
    starting with ``#`` are ignored. Surrounding whitespace is trimmed. Handles
    are de-duplicated case-insensitively (X screen names are case-insensitive),
    keeping the first-seen spelling. Original case is otherwise preserved.

    Raises :class:`XBoardError` naming the path and the sample file if missing.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise XBoardError(
            f"Follow-list not found: {p}\n"
            "  Create it with one @handle per line (blank lines and # comments are ignored).\n"
            f"  See {SAMPLE_FOLLOW_FILE} for an example you can copy."
        )

    handles: List[str] = []
    seen: set = set()
    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        handle = line.lstrip("@").strip()
        if not handle:
            continue
        key = handle.lower()
        if key in seen:
            continue
        seen.add(key)
        handles.append(handle)
    return handles


# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class Post:
    """A single normalized, display-ready original post."""

    text: str
    created_at: str
    likes: int
    retweets: int
    permalink: str


@dataclass
class AccountResult:
    """The fetch outcome for one handle — either posts or a human error reason."""

    handle: str
    display_name: str
    posts: List[Post] = field(default_factory=list)
    error: Optional[str] = None
    fetched_count: int = 0


# ── Fetch layer (U2) ─────────────────────────────────────────────────────────


def resolve_twitter_exe() -> Optional[str]:
    """Locate the ``twitter`` executable.

    Prefers the binary next to the running interpreter (the venv's Scripts/bin
    dir, where ``pip install twitter-cli`` puts it) so the script works even when
    the venv isn't "activated"; falls back to PATH.
    """
    exe_dir = Path(sys.executable).parent
    for name in ("twitter.exe", "twitter"):
        candidate = exe_dir / name
        if candidate.exists():
            return str(candidate)
    return shutil.which("twitter")


def _to_int(value: Any, default: int = 0) -> int:
    """Coerce a value to int, tolerating None and bad types."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _short(text: Optional[str], limit: int = 200) -> str:
    """Collapse whitespace and truncate a (possibly multi-line) message."""
    collapsed = " ".join((text or "").split())
    if len(collapsed) > limit:
        return collapsed[:limit] + "..."
    return collapsed


def _extract_json(raw: str) -> Any:
    """Parse JSON from CLI output, trimming any leading non-JSON noise.

    Returns the parsed object, or ``None`` if nothing parseable is found.
    """
    if not raw:
        return None
    starts = [i for i in (raw.find("["), raw.find("{")) if i >= 0]
    if not starts:
        return None
    try:
        return json.loads(raw[min(starts):])
    except ValueError:
        return None


def _items_from_payload(data: Any) -> List[dict]:
    """Pull the list of tweet dicts out of twitter-cli's response envelope.

    twitter-cli wraps success as ``{"ok": true, "schema_version": "1",
    "data": [...]}``; tolerate a few alternative shapes and a bare list.
    """
    if isinstance(data, dict):
        if isinstance(data.get("data"), list):
            return data["data"]
        for key in ("tweets", "results", "posts"):
            if isinstance(data.get(key), list):
                return data[key]
        return []
    if isinstance(data, list):
        return data
    return []


def _post_text(item: dict) -> str:
    """Best available post text. twitter-cli emits ``text``; ``full_text`` is the
    raw x.com field — prefer it when present (defensive)."""
    return item.get("full_text") or item.get("text") or ""


def _is_repost(item: dict) -> bool:
    """True if the item is a retweet/repost (not an original)."""
    if item.get("isRetweet") is True or item.get("is_retweet") is True:
        return True
    if item.get("retweetedBy") or item.get("retweeted_by"):
        return True
    if item.get("retweeted_status") or item.get("retweeted_status_result"):
        return True
    return _post_text(item).lstrip().startswith("RT @")


def _is_reply(item: dict) -> bool:
    """True if the item is a reply.

    twitter-cli's ``user-posts`` (the "Posts" tab) already excludes replies to
    others server-side and *discards* the raw ``in_reply_to_*`` fields. We still
    check those defensively (in case of a raw/alternate shape) and fall back to
    the leading-``@`` mention heuristic for anything that slips through.
    """
    if (
        item.get("in_reply_to_status_id_str")
        or item.get("in_reply_to_screen_name")
        or item.get("in_reply_to_user_id_str")
    ):
        return True
    return _post_text(item).lstrip().startswith("@")


def filter_original_posts(items: List[dict]) -> List[dict]:
    """Keep only original posts — drop replies and reposts. Pure."""
    originals = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if _is_repost(item) or _is_reply(item):
            continue
        originals.append(item)
    return originals


def normalize_post(item: dict, handle: str) -> Post:
    """Map a twitter-cli tweet dict to the small :class:`Post` model. Pure.

    Tolerant of missing fields and of both the twitter-cli camelCase shape and a
    raw snake_case shape (counts default to 0).
    """
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    likes = _to_int(metrics.get("likes", item.get("favorite_count", item.get("favoriteCount"))))
    retweets = _to_int(metrics.get("retweets", item.get("retweet_count", item.get("retweetCount"))))
    created_at = item.get("createdAtISO") or item.get("createdAt") or item.get("created_at") or ""
    tweet_id = str(item.get("id") or item.get("id_str") or "")
    permalink = f"https://x.com/{handle}/status/{tweet_id}" if tweet_id else f"https://x.com/{handle}"
    return Post(
        text=_post_text(item),
        created_at=created_at,
        likes=likes,
        retweets=retweets,
        permalink=permalink,
    )


def extract_display_name(items: List[dict], handle: str) -> str:
    """Read the author display name from the embedded author object; else @handle."""
    for item in items:
        if isinstance(item, dict):
            author = item.get("author")
            if isinstance(author, dict):
                name = author.get("name") or author.get("screenName") or author.get("screen_name")
                if name:
                    return str(name)
    return "@" + handle


def fetch_handle(
    handle: str,
    count: int,
    env: dict,
    timeout: int = 60,
    twitter_exe: Optional[str] = None,
) -> AccountResult:
    """Fetch one handle's recent original posts via twitter-cli.

    Every failure mode (missing CLI, non-zero exit, timeout, unparseable output,
    API error envelope, empty result) is captured as ``AccountResult.error`` —
    this never raises so one bad handle can't abort the whole board (R6).
    """
    fallback_name = "@" + handle
    exe = twitter_exe or resolve_twitter_exe()
    if not exe:
        return AccountResult(
            handle, fallback_name, [],
            "twitter CLI not found. Run X Board with the Agent-Reach venv, "
            "or install it with: pip install twitter-cli",
            0,
        )

    # Over-fetch so client-side filtering still leaves enough originals.
    buffer = max(count * 2, count + 10)
    cmd = [exe, "user-posts", handle, "-n", str(buffer), "--json"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace",
            env=env, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return AccountResult(handle, fallback_name, [], f"Timed out after {timeout}s.", 0)
    except Exception as exc:  # pragma: no cover - defensive
        return AccountResult(handle, fallback_name, [], f"Failed to run twitter CLI: {exc}", 0)

    data = _extract_json(proc.stdout or "")
    # Structured error envelope: {"ok": false, "error": {"code","message"}}
    if isinstance(data, dict) and data.get("ok") is False:
        err = data.get("error") or {}
        message = err.get("message") or err.get("code") or "Unknown API error."
        return AccountResult(handle, fallback_name, [], _short(message), 0)
    if data is None:
        message = _short(proc.stderr or proc.stdout) or f"twitter CLI exited with code {proc.returncode}."
        return AccountResult(handle, fallback_name, [], message, 0)

    items = _items_from_payload(data)
    if not items:
        return AccountResult(
            handle, fallback_name, [],
            "No posts returned (the account may be empty, protected, or suspended).",
            0,
        )

    display_name = extract_display_name(items, handle)
    originals = filter_original_posts(items)
    posts = [normalize_post(item, handle) for item in originals][:count]
    return AccountResult(handle, display_name, posts, None, len(posts))


# ── Render layer (U3) ────────────────────────────────────────────────────────


def _parse_dt(value: str) -> Optional[datetime]:
    """Parse an ISO-8601 or Twitter-native timestamp; ``None`` if unparseable."""
    if not value:
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None


def format_relative_time(created_at: str, now: Optional[datetime] = None) -> str:
    """Compact relative age (``now``/``30m``/``3h``/``2d``); absolute date if old
    (>= 7 days); the raw string if it can't be parsed. Pure (pass ``now``)."""
    dt = _parse_dt(created_at)
    if dt is None:
        return created_at or ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now is None:  # pragma: no cover - exercised via tests with explicit now
        now = datetime.now(timezone.utc)
    seconds = max((now - dt).total_seconds(), 0)
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    if seconds < 7 * 86400:
        return f"{int(seconds // 86400)}d"
    return dt.astimezone(timezone.utc).strftime("%b %d, %Y")


def format_absolute_time(created_at: str) -> str:
    """Absolute UTC timestamp for hover titles; raw string if unparseable."""
    dt = _parse_dt(created_at)
    if dt is None:
        return created_at or ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #f5f7fa; color: #14171a; line-height: 1.5;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.statusbar { position: sticky; top: 0; z-index: 10; display: flex; flex-wrap: wrap;
  justify-content: space-between; align-items: center; gap: 8px; padding: 14px 20px;
  color: #fff; font-weight: 600; box-shadow: 0 1px 4px rgba(0,0,0,.15); }
.statusbar.ok { background: #17a673; }
.statusbar.warn { background: #d9822b; }
.statusbar .mark { margin-right: 6px; }
.status-meta { font-weight: 400; font-size: .85rem; opacity: .95; }
main { max-width: 720px; margin: 0 auto; padding: 20px 16px 60px; }
.account { background: #fff; border: 1px solid #e1e8ed; border-radius: 12px;
  margin-bottom: 22px; overflow: hidden; }
.acct-head { display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  padding: 14px 16px; border-bottom: 1px solid #eef3f6; }
.acct-head .name { font-weight: 700; }
.acct-head .handle { color: #657786; text-decoration: none; }
.acct-head .handle:hover { text-decoration: underline; }
.badge { margin-left: auto; font-size: .8rem; font-weight: 600;
  padding: 3px 10px; border-radius: 999px; }
.badge.ok { background: #e3f6ee; color: #0f7a52; }
.badge.err { background: #fdecea; color: #b3261e; }
.post { padding: 14px 16px; border-bottom: 1px solid #f2f5f7; }
.post:last-child { border-bottom: none; }
.post-text { word-wrap: break-word; margin-bottom: 8px; }
.post-meta { display: flex; align-items: center; gap: 16px; font-size: .85rem; color: #657786; }
.post-meta .permalink { margin-left: auto; color: #1d9bf0; text-decoration: none; }
.post-meta .permalink:hover { text-decoration: underline; }
.error-card { padding: 14px 16px; background: #fdf6f5; }
.error-reason { color: #b3261e; font-weight: 600; margin-bottom: 6px; }
.hint { color: #657786; font-size: .85rem; }
.hint code { background: #eef3f6; padding: 1px 5px; border-radius: 4px; }
.empty { padding: 14px 16px; color: #657786; font-style: italic; }
footer { text-align: center; color: #8a99a8; font-size: .8rem; padding: 20px; }
""".strip()


def _render_post(post: Post, now: datetime) -> str:
    text = html.escape(post.text).replace("\n", "<br>")
    rel = html.escape(format_relative_time(post.created_at, now))
    absolute = html.escape(format_absolute_time(post.created_at))
    permalink = html.escape(post.permalink, quote=True)
    return (
        '    <article class="post">\n'
        f'      <div class="post-text">{text}</div>\n'
        '      <div class="post-meta">\n'
        f'        <span class="time" title="{absolute}">{rel}</span>\n'
        f'        <span class="stat">&#9829; {post.likes}</span>\n'
        f'        <span class="stat">&#8646; {post.retweets}</span>\n'
        f'        <a class="permalink" href="{permalink}" target="_blank" rel="noopener">open &#8599;</a>\n'
        '      </div>\n'
        '    </article>'
    )


def _render_account(result: AccountResult, now: datetime) -> str:
    name = html.escape(result.display_name or ("@" + result.handle))
    handle = html.escape(result.handle)
    if result.error:
        badge = '<span class="badge err">fetch failed</span>'
        inner = (
            '    <div class="error-card">\n'
            f'      <div class="error-reason">{html.escape(result.error)}</div>\n'
            '      <div class="hint">If this keeps happening, your cookies may be stale — '
            're-run <code>agent-reach configure twitter-cookies</code>.</div>\n'
            '    </div>'
        )
    else:
        badge = f'<span class="badge ok">{result.fetched_count} posts fetched</span>'
        if result.posts:
            inner = "\n".join(_render_post(p, now) for p in result.posts)
        else:
            inner = '    <div class="empty">No original posts in the fetched window.</div>'
    return (
        '  <section class="account">\n'
        '    <div class="acct-head">\n'
        f'      <span class="name">{name}</span>\n'
        f'      <a class="handle" href="https://x.com/{handle}" target="_blank" rel="noopener">@{handle}</a>\n'
        f'      {badge}\n'
        '    </div>\n'
        f'{inner}\n'
        '  </section>'
    )


def render_html(results: List[AccountResult], generated_at: datetime) -> str:
    """Render account results into one self-contained HTML document string.

    Inline CSS only — no external assets, fonts, or remote images. Every dynamic
    value is HTML-escaped. The renderer only ever receives display data, never
    cookies, so credentials cannot leak into the output (R13).
    """
    if isinstance(generated_at, datetime):
        now = generated_at if generated_at.tzinfo else generated_at.replace(tzinfo=timezone.utc)
        stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    else:  # pragma: no cover - defensive; callers pass a datetime
        now = datetime.now(timezone.utc)
        stamp = str(generated_at)

    total = len(results)
    ok_count = sum(1 for r in results if not r.error)
    plural = "s" if total != 1 else ""
    if total and ok_count == total:
        status_class, mark = "ok", "&#9989;"  # ✅
        status_text = f"All {total} account{plural} OK"
    else:
        status_class, mark = "warn", "&#9888;"  # ⚠
        status_text = f"{ok_count} of {total} accounts OK"

    body = "\n".join(_render_account(r, now) for r in results)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>X Board</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        f'<header class="statusbar {status_class}">\n'
        f'  <div class="status-main"><span class="mark">{mark}</span> {html.escape(status_text)}</div>\n'
        f'  <div class="status-meta">{total} account{plural} &middot; fetched {html.escape(stamp)}</div>\n'
        "</header>\n"
        "<main>\n"
        f"{body}\n"
        "</main>\n"
        '<footer>Generated by X Board &middot; a read-only viewer over twitter-cli. '
        "No login details are stored in this file.</footer>\n"
        "</body>\n"
        "</html>\n"
    )


# ── CLI orchestration (U4) ───────────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> int:
    """Parse args, run the fetch→render pipeline, write+open the board.

    Returns an exit code: 0 all OK, 1 partial/all-failed (page still written),
    2 setup error (no cookies / missing or empty follow-list).
    """
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = argparse.ArgumentParser(
        prog="x_board",
        description="Build a local HTML board of recent original X posts for a follow-list.",
    )
    parser.add_argument("--file", default=str(DEFAULT_FOLLOW_FILE),
                        help=f"Follow-list path (default: {DEFAULT_FOLLOW_FILE}).")
    parser.add_argument("-n", "--count", type=int, default=10,
                        help="Original posts to show per account (default: 10).")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_FILE),
                        help=f"Output HTML path (default: {DEFAULT_OUTPUT_FILE}).")
    parser.add_argument("--no-open", action="store_true",
                        help="Do not open the page in a browser after writing it.")
    parser.add_argument("--timeout", type=int, default=60,
                        help="Per-account fetch timeout in seconds (default: 60).")
    args = parser.parse_args(argv)

    try:
        auth_token, ct0 = load_cookies()
    except XBoardError as exc:
        print(f"[setup] {exc}", file=sys.stderr)
        return 2

    try:
        handles = parse_follow_list(args.file)
    except XBoardError as exc:
        print(f"[setup] {exc}", file=sys.stderr)
        return 2
    if not handles:
        print(
            f"[setup] No handles found in {args.file}. Add one @handle per line "
            f"(see {SAMPLE_FOLLOW_FILE}).",
            file=sys.stderr,
        )
        return 2

    env = dict(os.environ)
    env["TWITTER_AUTH_TOKEN"] = auth_token
    env["TWITTER_CT0"] = ct0
    env["PYTHONUTF8"] = "1"

    twitter_exe = resolve_twitter_exe()
    results: List[AccountResult] = []
    for handle in handles:
        print(f"  fetching @{handle} ...", file=sys.stderr)
        results.append(
            fetch_handle(handle, args.count, env, timeout=args.timeout, twitter_exe=twitter_exe)
        )

    document = render_html(results, datetime.now(timezone.utc))
    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(document, encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)

    if not args.no_open:
        try:
            webbrowser.open(out_path.resolve().as_uri())
        except Exception:  # pragma: no cover - browser env dependent
            print("  (could not open a browser automatically; open the file manually)", file=sys.stderr)

    ok_count = sum(1 for r in results if not r.error)
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

