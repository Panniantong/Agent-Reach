# -*- coding: utf-8 -*-
"""Bilibili — multi-backend: bili-cli / OpenCLI / search API.

yt-dlp was REMOVED from this channel (live-verified 2026-06): bilibili's
risk control 412-blocks yt-dlp's requests in every configuration we
tried — latest version, direct, proxied, with warmed cookies — while
bili-cli keeps working (search/hot/video detail without login) and
OpenCLI covers subtitles through the browser session. yt-dlp remains the
YouTube backend; it just no longer serves bilibili.
"""

import json
import re
import urllib.request
from typing import Any

from agent_reach.runtime.result import (
    BAD_INPUT,
    NEED_LOGIN,
    NOT_FOUND,
    PLATFORM_BLOCKED,
    RATE_LIMITED,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
    unix_to_iso,
)
from agent_reach.runtime.run import CommandFailed, http_request, run_cmd
from agent_reach.runtime.sessions import has_login_state, session_env

from .base import Action, Channel, Param

_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")
_BILI_LOGIN_HINT = (
    "Bilibili subtitles need a login. Ask the user to run `bili login` and scan "
    "the QR code themselves; never log in on their behalf."
)


def _bvid(target: str, timeout: float) -> str:
    """BV id from a BV id, a video link, or a b23.tv short link."""
    t = str(target).strip()
    m = _BV_RE.search(t)
    if m:
        return m.group(0)
    if "b23.tv/" in t:
        url = t if "://" in t else f"https://{t}"
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            m = _BV_RE.search(resp.geturl())
        if m:
            return m.group(0)
    raise ReachError(BAD_INPUT, "target must be a BV id or a bilibili.com / b23.tv video link")


def _bili_json(args: list, timeout: float) -> Any:
    """Run bili-cli with --json; map its error envelope to unified codes."""
    try:
        out = run_cmd(["bili", *args, "--json"], timeout=timeout, env=session_env("bili-cli"))
    except CommandFailed as exc:
        out = exc.stdout
        if "{" not in out:
            raise
    try:
        payload = json.loads(out[out.index("{"):])
    except ValueError:
        raise ReachError(UPSTREAM_BROKEN, "bili-cli returned unreadable output") from None
    if not payload.get("ok"):
        err = payload.get("error") or {}
        code = str(err.get("code", ""))
        message = str(err.get("message", "bili-cli failed"))[:500]
        upstream_hint = str(err.get("hint") or "").strip() or None
        if any(word in code.lower() for word in ("risk", "captcha", "verification")):
            raise ReachError(PLATFORM_BLOCKED, message, hint=upstream_hint)
        if "rate" in code.lower() or "频繁" in message:
            raise ReachError(RATE_LIMITED, message)
        if code == "not_found":
            raise ReachError(NOT_FOUND, message)
        if "login" in code or "auth" in code or "credential" in code:
            raise ReachError(NEED_LOGIN, message, hint=_BILI_LOGIN_HINT)
        raise ReachError(UPSTREAM_BROKEN, message, hint=upstream_hint)
    return payload.get("data") or {}


def _reuse_subtitle_login(timeout: float) -> None:
    """Use the official upstream credential writer; no browser launch or database read."""
    import os
    from pathlib import Path

    from agent_reach.runtime import session_reuse, state, tools
    saved = state.load().get("session_reuse", {}).get("bilibili", {})
    if saved.get("blocked") or saved.get("source") == "manual":
        return
    cookies, source = session_reuse._source_cookies("bilibili", ("bilibili.com",))
    jar = {c["name"]: c["value"] for c in cookies}
    if not jar.get("SESSDATA"):
        return  # keep a saved native login when no connected local source exists
    exe = tools.resolve("bili")
    if not exe:
        return
    python = Path(exe).with_name("python.exe" if os.name == "nt" else "python")
    script = (
        "import json,sys;from bili_cli.auth import save_credential;"
        "from bilibili_api import Credential;d=json.load(sys.stdin);"
        "save_credential(Credential(sessdata=d.get('SESSDATA',''),bili_jct=d.get('bili_jct',''),"
        "ac_time_value=d.get('ac_time_value',''),buvid3=d.get('buvid3',''),"
        "buvid4=d.get('buvid4',''),dedeuserid=d.get('DedeUserID','')))"
    )
    run_cmd([str(python), "-c", script], timeout=timeout, env=session_env("bili-cli"),
            input_data=json.dumps(jar), label="Bilibili site login reuse")
    state.mutate(lambda data: data.setdefault("session_reuse", {}).__setitem__("bilibili", {
        "source": source, "copied_cookies": len(jar), "at": state.now(), "verified": False, "source_changed": False}))


def _cli_video_item(v: dict, text=None) -> dict:
    owner = v.get("owner") or {}
    return make_item(
        title=v.get("title"),
        url=v.get("url") or (f"https://www.bilibili.com/video/{v['bvid']}" if v.get("bvid") else None),
        author=owner.get("name") or v.get("author"),
        text=v.get("description") if text is None else text,
        raw=v,
    )


def _api_video_item(v: dict, text=None) -> dict:
    return make_item(
        title=v.get("title"),
        url=f"https://www.bilibili.com/video/{v.get('bvid')}" if v.get("bvid") else None,
        author=(v.get("owner") or {}).get("name"),
        published_at=unix_to_iso(v.get("pubdate")),
        text=v.get("desc") if text is None else text,
        raw={k: v.get(k) for k in ("bvid", "aid", "duration", "stat", "tname")},
    )


def _bili_api(path: str, timeout: float) -> dict:
    body = http_request(
        f"https://api.bilibili.com{path}",
        timeout=timeout,
        headers={"User-Agent": _UA, "Referer": "https://www.bilibili.com/"},
    )
    try:
        data = json.loads(body)
    except ValueError:
        raise ReachError(UPSTREAM_BROKEN, "Bilibili returned a verification page") from None
    if data.get("code") == -404:
        raise ReachError(NOT_FOUND, "video not found")
    if data.get("code") != 0:
        raise ReachError(UPSTREAM_BROKEN, f"Bilibili API code {data.get('code')}: {data.get('message')}")
    return data.get("data") or {}


_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class BilibiliChannel(Channel):
    name = "bilibili"
    description = "B站视频、字幕和搜索"

    level = "default"
    session = "bili-cli"
    login_argv = ("bili", "login")
    legacy_state = (".bilibili-cli",)
    tools = ("bili-cli",)
    actions = (
        Action(
            "search",
            "Search videos",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("bili-cli", "_cli_search"),),
            live_test={"query": "Python", "limit": 2},
        ),
        Action(
            "read",
            "Video title, uploader, description and stats",
            (Param("target", "BV id or video link"),),
            (("bili-cli", "_cli_read"), ("bilibili-api", "_api_read")),
            live_test={"target": "BV1GJ411x7h7"},
        ),
        Action(
            "hot",
            "Trending videos",
            (Param("limit", "max items", required=False, type=int, default=10),),
            (("bili-cli", "_cli_hot"), ("bilibili-api", "_api_hot")),
            live_test={"limit": 2},
        ),
        Action(
            "subtitle",
            "Subtitle text of the first video part, when available (may need a Bilibili login)",
            (Param("target", "BV id or video link"),),
            (("bili-cli", "_cli_subtitle"),),
            live_test={"target": "BV1GJ411x7h7"},
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "bilibili.com", "b23.tv")

    # ── unified entry backends ──

    def _cli_search(self, *, query: str, limit: int, timeout: float) -> list:
        data = _bili_json(["search", query, "--type", "video", "-n", str(limit)], timeout)
        return [_cli_video_item(v) for v in (data if isinstance(data, list) else [])[:limit]]

    def _cli_read(self, *, target: str, timeout: float) -> list:
        data = _bili_json(["video", _bvid(target, timeout)], timeout)
        return [_cli_video_item(data.get("video") or {})]

    def _api_read(self, *, target: str, timeout: float) -> list:
        return [_api_video_item(_bili_api(f"/x/web-interface/view?bvid={_bvid(target, timeout)}", timeout))]

    def _cli_hot(self, *, limit: int, timeout: float) -> list:
        data = _bili_json(["hot", "-n", str(limit)], timeout)
        return [_cli_video_item(v) for v in (data.get("items") or [])[:limit]]

    def _api_hot(self, *, limit: int, timeout: float) -> list:
        data = _bili_api(f"/x/web-interface/popular?ps={limit}&pn=1", timeout)
        return [_api_video_item(v) for v in (data.get("list") or [])[:limit]]

    def _cli_subtitle(self, *, target: str, timeout: float) -> list:
        _reuse_subtitle_login(timeout)
        data = _bili_json(["video", _bvid(target, timeout), "--subtitle"], timeout)
        sub = data.get("subtitle") or {}
        if not sub.get("available"):
            # Without a Bilibili login, upstream only says subtitles were unavailable.
            if not has_login_state("bili-cli"):
                raise ReachError(NEED_LOGIN, "Bilibili is not logged in", hint=_BILI_LOGIN_HINT)
            if any(w.get("code") == "subtitle_unavailable" for w in data.get("warnings", []) if isinstance(w, dict)):
                raise ReachError(UPSTREAM_BROKEN, "Bilibili could not retrieve subtitles; this does not prove the video has none")
            raise ReachError(NOT_FOUND, "this video has no subtitles")
        text = sub.get("text") or "\n".join(i.get("content", "") for i in sub.get("items") or [])
        return [_cli_video_item(data.get("video") or {}, text=text)]
