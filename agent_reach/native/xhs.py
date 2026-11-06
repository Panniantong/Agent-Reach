# -*- coding: utf-8 -*-
"""Native XiaoHongShu backend (search / read / comments).

This is the in-repo home of the former ``~/Projects/Spider_XHS/xhs_api.py``
and ``~/.local/bin/xhs_comments.py``. Spider_XHS stays vendored and outside
git because it owns request signing; this module only

* injects ``xhs_cookie`` and the proxy through the child environment,
* enforces the cross-process 35s throttle, and
* maps the JSON payloads into Reach items / error codes.

It never uses a browser, a query slot or the browser search pacing.
"""

from __future__ import annotations

import errno
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import parse_qs, urlsplit, urlunsplit

from agent_reach.config import Config
from agent_reach.runtime.result import (
    BAD_INPUT,
    NEED_SETUP,
    TIMEOUT,
    UPSTREAM_BROKEN,
    ReachError,
)
from agent_reach.runtime.run import run_cmd
from agent_reach.utils.paths import home_dir
from agent_reach.utils.url import host_matches

from ._items import comment_item, map_xhs_error, note_item

DEFAULT_MIN_INTERVAL = 35.0
DEFAULT_LOCK_FILE = ".cache/xhs_api.lock"
DEFAULT_TIMEOUT = 120.0

#: Kept as a module constant so the Windows fallback can be tested without
#: pretending that ``os.name`` is ``nt`` (pathlib refuses WindowsPath on POSIX).
_WINDOWS = sys.platform == "win32"
_PROCESS_LOCK = threading.Lock()
_NOTE_PATH = re.compile(r"/(?:explore|search_result|discovery/item)/[A-Za-z0-9_-]+")

SEARCH_CODE = r'''
import json, os

out = {"success": False, "msg": "", "code": "", "notes": []}
notes = []
seen = set()
code = ""
limit = 5
try:
    from dotenv import load_dotenv; load_dotenv()
    from xhs_utils.xhs_pc import XHSPcAuth
    from xhs_utils.xhs_pc.params import generate_search_id
    from apis.xhs_pc_apis import XHS_Apis
    auth = XHSPcAuth.from_cookie(os.environ["XHS_COOKIE_INTERNAL"])
    api = XHS_Apis(auth).bootstrap()
    query = os.environ["XHS_QUERY"]
    limit = int(os.environ.get("XHS_LIMIT", "5"))
    sort = int(os.environ.get("XHS_SORT", "0"))
    root_search_id = generate_search_id()
    ok = True
    msg = ""
    page = 1
    while len(notes) < limit and page <= 10:
        success, msg, res_json = api.search_note(
            query, page, sort, search_id=generate_search_id(root_search_id)
        )
        code = str((res_json or {}).get("code") or "")
        if not success:
            ok = False
            break
        data = (res_json or {}).get("data") or {}
        items = data.get("items") or []
        for item in items:
            if item.get("model_type") != "note":
                continue
            card = item.get("note_card") or {}
            interact = card.get("interact_info") or {}
            cover = card.get("cover") or {}
            user = card.get("user") or {}
            note_id = item.get("id")
            token = item.get("xsec_token") or ""
            if not note_id or not token or note_id in seen:
                continue
            seen.add(note_id)
            notes.append({
                "id": note_id,
                "xsec_token": token,
                "url": "https://www.xiaohongshu.com/explore/%s?xsec_token=%s&xsec_source=pc_search" % (note_id, token),
                "title": card.get("display_title") or card.get("title") or "",
                "nickname": user.get("nickname") or user.get("nick_name") or "",
                "likes": interact.get("liked_count"),
                "collects": interact.get("collected_count"),
                "comments": interact.get("comment_count"),
                "cover_url": (cover.get("url_default") or "").replace("http://", "https://"),
            })
        if len(notes) >= limit or not data.get("has_more") or not items:
            break
        page += 1
    out["success"] = ok
    out["msg"] = str(msg or "")
except Exception as exc:
    out["success"] = False
    out["msg"] = str(exc)[-800:]
out["code"] = code
out["notes"] = notes[:limit]
print(json.dumps(out, ensure_ascii=False))
'''

DETAIL_CODE = r'''
import json, os

out = {"success": False, "msg": "", "code": ""}
try:
    from dotenv import load_dotenv; load_dotenv()
    from xhs_utils.xhs_pc import XHSPcAuth
    from apis.xhs_pc_apis import XHS_Apis
    auth = XHSPcAuth.from_cookie(os.environ["XHS_COOKIE_INTERNAL"])
    api = XHS_Apis(auth).bootstrap()
    url = os.environ["XHS_NOTE_URL"]
    success, msg, res_json = api.get_note_info(url)
    code = str((res_json or {}).get("code") or "")
    out["success"] = bool(success)
    out["msg"] = str(msg or "")
    out["code"] = code
    items = ((res_json or {}).get("data") or {}).get("items") or []
    if success and items:
        item = items[0]
        card = item.get("note_card") or {}
        interact = card.get("interact_info") or {}
        user = card.get("user") or {}
        imgs = card.get("image_list") or []
        out["note"] = {
            "id": card.get("note_id") or item.get("id"),
            "title": card.get("display_title") or card.get("title") or "",
            "desc": card.get("desc") or "",
            "nickname": user.get("nickname") or user.get("nick_name") or "",
            "user_id": user.get("user_id"),
            "likes": interact.get("liked_count"),
            "collects": interact.get("collected_count"),
            "comments": interact.get("comment_count"),
            "tags": [t.get("name") for t in (card.get("tag_list") or [])],
            "image_urls": [(i.get("url_default") or "").replace("http://", "https://") for i in imgs],
            "ip_location": card.get("ip_location"),
            "publish_time": card.get("time"),
        }
except Exception as exc:
    out["success"] = False
    out["msg"] = str(exc)[-800:]
print(json.dumps(out, ensure_ascii=False))
'''

COMMENTS_CODE = r'''
import json, os, time
from urllib.parse import parse_qs, urlparse

out = {"success": False, "msg": "", "code": "", "comments": [], "total_fetched": 0}
comments = []
code = ""
limit = 20
try:
    from dotenv import load_dotenv; load_dotenv()
    from xhs_utils.xhs_pc import XHSPcAuth
    from apis.xhs_pc_apis import XHS_Apis
    auth = XHSPcAuth.from_cookie(os.environ["XHS_COOKIE_INTERNAL"])
    api = XHS_Apis(auth).bootstrap()
    url = os.environ["XHS_NOTE_URL"]
    limit = int(os.environ.get("XHS_COMMENT_LIMIT", "20"))
    interval = float(os.environ.get("XHS_INTERVAL", "0"))
    parts = urlparse(url)
    note_id = [p for p in parts.path.split("/") if p][-1]
    token = (parse_qs(parts.query).get("xsec_token") or [""])[0]
    ok = True
    msg = ""
    cursor = ""
    while len(comments) < limit:
        success, msg, res_json = api.get_note_out_comment(note_id, cursor, token, None)
        code = str((res_json or {}).get("code") or "")
        if not success:
            ok = False
            break
        data = (res_json or {}).get("data") or {}
        for c in data.get("comments") or []:
            comments.append({
                "nickname": (c.get("user_info") or {}).get("nickname", ""),
                "content": c.get("content", ""),
                "likes": c.get("like_count", ""),
                "ip": c.get("ip_location", ""),
                "sub_count": c.get("sub_comment_count", 0),
                "sub": [{
                    "nickname": (s.get("user_info") or {}).get("nickname", ""),
                    "content": s.get("content", ""),
                    "likes": s.get("like_count", ""),
                } for s in (c.get("sub_comments") or [])],
            })
        if len(comments) >= limit or not data.get("has_more"):
            break
        next_cursor = data.get("cursor", "") or ""
        if not next_cursor or next_cursor == cursor:
            break
        if interval > 0:
            time.sleep(interval)
        cursor = next_cursor
    out["success"] = ok
    out["msg"] = str(msg or "")
except Exception as exc:
    out["success"] = False
    out["msg"] = str(exc)[-800:]
out["code"] = code
out["comments"] = comments[:limit]
out["total_fetched"] = len(comments)
print(json.dumps(out, ensure_ascii=False))
'''


# ── configuration and child process ─────────────────────────────────────────


def _interpreter() -> Path:
    configured = Config().get("xhs_python")
    if configured:
        return Path(str(configured)).expanduser()
    scripts = "Scripts" if _WINDOWS else "bin"
    executable = "python.exe" if _WINDOWS else "python"
    return (
        Path(__file__).resolve().parents[2]
        / "vendor" / "Spider_XHS" / ".venv" / scripts / executable
    )


def _spider_dir(interpreter: Path) -> Path:
    """Spider_XHS checkout that owns the imports used by the child code."""
    configured = Config().get("xhs_spider_dir")
    if configured:
        candidate = Path(str(configured)).expanduser()
        if candidate.is_dir():
            return candidate
    # Do not resolve symlinks here: a checkout's .venv/bin/python is often a
    # symlink to a UV/system CPython, and resolving it would lose the checkout.
    absolute = Path(os.path.abspath(os.path.expanduser(os.fspath(interpreter))))
    checkout: Optional[Path]
    try:
        checkout = absolute.parents[2]
    except IndexError:
        checkout = None
    if checkout is not None and (checkout / "apis").is_dir():
        return checkout
    return Path(__file__).resolve().parents[2] / "vendor" / "Spider_XHS"


def _proxy_env() -> dict[str, str]:
    """Configured proxy wins over inherited lowercase/ALL_PROXY variables."""
    proxy = Config().get("proxy") or os.environ.get("XHS_PROXY")
    if not proxy:
        return {}
    value = str(proxy)
    env = {
        key: value
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        )
    }
    no_proxy = Config().get("no_proxy") or os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    if no_proxy:
        env["NO_PROXY"] = env["no_proxy"] = str(no_proxy)
    return env


def load_cookie() -> str:
    """Read ``xhs_cookie`` from config (or its uppercase environment override)."""
    cookie = str(Config().get("xhs_cookie") or "").strip()
    if not cookie:
        raise ReachError(
            NEED_SETUP,
            "xhs_cookie is not configured; add it to ~/.agent-reach/config.yaml or set XHS_COOKIE",
        )
    return cookie


def _min_interval() -> float:
    try:
        return float(os.environ.get("XHS_MIN_INTERVAL", DEFAULT_MIN_INTERVAL))
    except (TypeError, ValueError):
        return DEFAULT_MIN_INTERVAL


def _wait_and_stamp(
    path: Path, interval: float, remaining: Optional[float], started: float
) -> float:
    """Wait for the shared throttle and record the request start time.

    Callers hold the cross-process lock (POSIX) or the process lock (Windows).
    """
    try:
        last = float(path.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        last = 0.0
    wait = interval - (time.time() - last)
    if wait > 0:
        elapsed = time.monotonic() - started
        if remaining is not None and elapsed + wait >= remaining:
            raise ReachError(
                TIMEOUT, "XiaoHongShu throttle wait exceeds the remaining timeout"
            )
        time.sleep(wait)
    try:
        path.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass
    return time.monotonic() - started


def _lock_path() -> Path:
    override = os.environ.get("XHS_LOCK_FILE")
    if override:
        return Path(override).expanduser()
    return home_dir() / DEFAULT_LOCK_FILE


def _acquire_process_lock(remaining: Optional[float], started: float) -> None:
    if remaining is None:
        acquired = _PROCESS_LOCK.acquire()
    else:
        timeout = max(0.0, started + remaining - time.monotonic())
        acquired = _PROCESS_LOCK.acquire(timeout=timeout)
    if not acquired:
        raise ReachError(
            TIMEOUT, "XiaoHongShu throttle lock wait exceeds the remaining timeout"
        )


def _throttle(remaining: Optional[float] = None) -> float:
    """Cross-process throttle shared with the old xhs_api.py lock file.

    ``fcntl`` is imported lazily: Windows has no such module and every CLI
    invocation imports all channels. Lock acquisition is non-blocking so a
    busy peer cannot overshoot the action's remaining budget.
    """
    interval = _min_interval()
    if interval <= 0:
        return 0.0
    path = _lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    started = time.monotonic()
    if _WINDOWS:
        _acquire_process_lock(remaining, started)
        try:
            return _wait_and_stamp(path, interval, remaining, started)
        finally:
            _PROCESS_LOCK.release()
    import fcntl

    try:
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        _acquire_process_lock(remaining, started)
        try:
            return _wait_and_stamp(path, interval, remaining, started)
        finally:
            _PROCESS_LOCK.release()
    try:
        if remaining is None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:
            deadline = started + remaining
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                        raise
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise ReachError(
                            TIMEOUT,
                            "XiaoHongShu throttle lock wait exceeds the remaining timeout",
                        )
                    time.sleep(min(0.05, left))
        return _wait_and_stamp(path, interval, remaining, started)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def run_py(code: str, *, timeout: float, extra_env: Optional[dict[str, str]] = None) -> str:
    """Run one snippet inside the Spider_XHS venv with cookie, proxy and throttle."""
    cookie = load_cookie()
    interpreter = _interpreter()
    if not interpreter.is_file():
        raise ReachError(
            NEED_SETUP,
            f"xhs_python is not installed: {interpreter}; install Spider_XHS or set xhs_python",
        )
    started = time.monotonic()
    _throttle(timeout)
    budget = timeout - (time.monotonic() - started)
    if budget <= 0.1:
        raise ReachError(TIMEOUT, "XiaoHongShu throttle left no time for the request")

    env = _proxy_env()
    env["XHS_COOKIE_INTERNAL"] = cookie
    env.update(extra_env or {})
    return run_cmd(
        [str(interpreter), "-c", code],
        timeout=budget,
        env=env,
        cwd=str(_spider_dir(interpreter)),
        label="xhs",
    )


def _payload(stdout: str) -> dict:
    text = (stdout or "").strip()
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    # Upstream tooling may print warnings before the JSON line.
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            candidate = json.loads(line)
        except ValueError:
            continue
        if isinstance(candidate, dict):
            return candidate
    raise ReachError(
        UPSTREAM_BROKEN,
        "XiaoHongShu returned non-JSON output (the request may be blocked)",
    )


def _call(code: str, *, timeout: float, extra_env: dict[str, str]) -> dict:
    return _payload(run_py(code, timeout=timeout, extra_env=extra_env))


# ── input validation ────────────────────────────────────────────────────────


def _search_limit(limit: Any) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ReachError(BAD_INPUT, "limit must be a positive integer")
    return limit


def _comments_limit(limit: Any) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ReachError(BAD_INPUT, "limit must be between 1 and 50 top-level comments")
    return limit


def _resolve_short_link(url: str, timeout: float) -> str:
    """Follow an xhslink redirect so native can read the note instead of pausing."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "agent-reach/xhs"})
    try:
        with urllib.request.urlopen(
            request, timeout=max(0.1, min(timeout, 10.0))
        ) as response:
            resolved = response.geturl()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ReachError(
            UPSTREAM_BROKEN, f"could not resolve XiaoHongShu short link: {exc}"
        ) from None
    if not resolved or host_matches(resolved, "xhslink.com"):
        raise ReachError(UPSTREAM_BROKEN, "XiaoHongShu short link did not resolve to a note")
    return resolved


def _normalize_note_url(target: Any, timeout: float) -> str:
    """Resolve short links, upgrade http, strip a trailing slash, and require a token."""
    url = str(target or "").strip()
    if host_matches(url, "xhslink.com"):
        url = _resolve_short_link(url, timeout)
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    path = parsed.path.rstrip("/")
    normalized = urlunsplit(("https", parsed.netloc, path, parsed.query, parsed.fragment))
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not host_matches(normalized, "xiaohongshu.com")
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or not _NOTE_PATH.fullmatch(path)
    ):
        raise ReachError(
            BAD_INPUT, "target must be a full Xiaohongshu note link including xsec_token"
        )
    token = (parse_qs(parsed.query).get("xsec_token") or [""])[0].strip()
    if not token:
        raise ReachError(
            BAD_INPUT,
            "target is missing xsec_token; run search again and use the returned full link",
        )
    return normalized


def _note_url(target: Any, timeout: float) -> str:
    return _normalize_note_url(target, timeout)


def _comment_url(target: Any, timeout: float) -> str:
    return _normalize_note_url(target, timeout)


# ── public backend surface ──────────────────────────────────────────────────


def search(*, query: str, limit: int, timeout: float, sort: int = 0) -> list[dict]:
    query = str(query or "").strip()
    if not query:
        raise ReachError(BAD_INPUT, "query must not be empty")
    limit = _search_limit(limit)
    if isinstance(sort, bool) or not isinstance(sort, int):
        raise ReachError(BAD_INPUT, "sort must be an integer")
    payload = _call(
        SEARCH_CODE,
        timeout=timeout,
        extra_env={"XHS_QUERY": query, "XHS_LIMIT": str(limit), "XHS_SORT": str(sort)},
    )
    error = map_xhs_error("search", payload)
    if error is not None:
        raise error
    rows = payload.get("notes")
    if not isinstance(rows, list):
        raise ReachError(UPSTREAM_BROKEN, "XiaoHongShu search returned no notes list")
    return [note_item(row) for row in rows if isinstance(row, dict)][:limit]


def read(*, target: str, timeout: float) -> list[dict]:
    url = _note_url(target, timeout)
    payload = _call(DETAIL_CODE, timeout=timeout, extra_env={"XHS_NOTE_URL": url})
    error = map_xhs_error("read", payload)
    if error is not None:
        raise error
    note = payload.get("note")
    if not isinstance(note, dict) or not note:
        raise ReachError(UPSTREAM_BROKEN, "XiaoHongShu detail returned no note")
    return [note_item(note, url=url)]


def comments(*, target: str, limit: int, timeout: float) -> list[dict]:
    url = _comment_url(target, timeout)
    limit = _comments_limit(limit)
    payload = _call(
        COMMENTS_CODE,
        timeout=timeout,
        extra_env={
            "XHS_NOTE_URL": url,
            "XHS_COMMENT_LIMIT": str(limit),
            "XHS_INTERVAL": str(_min_interval()),
        },
    )
    error = map_xhs_error("comments", payload)
    if error is not None:
        raise error
    rows = payload.get("comments")
    if not isinstance(rows, list):
        raise ReachError(UPSTREAM_BROKEN, "XiaoHongShu comments returned no comments list")
    return [comment_item(row, url=url) for row in rows if isinstance(row, dict)][:limit]


# ── CLI compatibility (shims re-exec ``python -m agent_reach.native.xhs``) ──


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Keep the old xhs_api.py / xhs_comments.py command lines working."""
    import argparse

    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0].startswith(("http://", "https://")):
        # Old xhs_comments.py usage: ``<note_url> [pages]`` (default 2 pages).
        pages = 2
        if len(args) > 1:
            try:
                pages = max(1, int(args[1]))
            except ValueError:
                pages = 2
        args = ["comments", args[0], str(min(50, pages * 10))]
    elif args and args[0] == "detail":
        args[0] = "read"

    parser = argparse.ArgumentParser(prog="xhs", description="XiaoHongShu native backend")
    sub = parser.add_subparsers(dest="command")
    search_parser = sub.add_parser("search", help="search notes")
    search_parser.add_argument("query")
    search_parser.add_argument("limit", nargs="?", type=int, default=5)
    search_parser.add_argument("sort", nargs="?", type=int, default=0)
    read_parser = sub.add_parser("read", help="read one note")
    read_parser.add_argument("url")
    comments_parser = sub.add_parser("comments", help="read top-level comments")
    comments_parser.add_argument("url")
    comments_parser.add_argument("limit", nargs="?", type=int, default=20)
    parsed = parser.parse_args(args)
    if parsed.command is None:
        parser.print_help()
        return 1

    try:
        if parsed.command == "search":
            items = search(
                query=parsed.query,
                limit=parsed.limit,
                sort=parsed.sort,
                timeout=DEFAULT_TIMEOUT,
            )
        elif parsed.command == "read":
            items = read(target=parsed.url, timeout=DEFAULT_TIMEOUT)
        else:
            items = comments(target=parsed.url, limit=parsed.limit, timeout=DEFAULT_TIMEOUT)
    except ReachError as exc:
        print(json.dumps(
            {"success": False, "msg": exc.message, "code": exc.code}, ensure_ascii=False
        ))
        return 1

    payload: dict[str, Any] = {"success": True, "msg": "", "items": items}
    if parsed.command == "search":
        payload["notes"] = [item.get("raw") for item in items]
    elif parsed.command == "read":
        payload["note"] = items[0].get("raw") if items else None
    else:
        payload["comments"] = [item.get("raw") for item in items]
        payload["total_fetched"] = len(items)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI compatibility path
    raise SystemExit(main())
