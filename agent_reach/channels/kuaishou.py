# -*- coding: utf-8 -*-
"""Read Kuaishou pages through the Agent Reach browser and its own API requests."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlsplit

from agent_reach.runtime.result import (
    BAD_INPUT,
    NEED_LOGIN,
    NOT_FOUND,
    PLATFORM_BLOCKED,
    RATE_LIMITED,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)

from .base import Action, Channel, Param

_ORIGIN = "https://www.kuaishou.com"
_SEARCH_PATH = "/rest/v/search/feed"
_HOT_PATH = "/rest/v/feed/hot"
_PROFILE_FEED_PATH = "/rest/v/profile/feed"
_GRAPHQL_PATH = "/graphql"
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_LOGIN_HINT = (
    "Run `agent-reach login kuaishou` and let the user sign in to Kuaishou in the "
    "Agent Reach browser. Never ask for a password."
)


def _capture_script(paths: tuple[str, ...]) -> str:
    """Capture bounded same-origin responses for the already verified read endpoints."""
    allowed_paths = json.dumps(paths)
    return r"""(() => {
  const origin = "https://www.kuaishou.com";
  const paths = new Set(__ALLOWED_PATHS__);
  const rows = window.__agentReachKuaishouResponses || [];
  window.__agentReachKuaishouResponses = rows;
  const record = (url, status, body, requestBody) => {
    try {
      const target = new URL(url, location.href);
      if (target.origin !== origin || !paths.has(target.pathname) || rows.length >= 12) return;
      if (typeof body !== "string" || body.length > 2500000) return;
      rows.push({path: target.pathname, status, body,
        requestBody: typeof requestBody === "string" ? requestBody.slice(0, 20000) : ""});
    } catch (_) {}
  };
  const open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.__agentReachUrl = String(url);
    return open.call(this, method, url, ...rest);
  };
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function(body) {
    this.addEventListener("loadend", () => {
      try { record(this.responseURL || this.__agentReachUrl, this.status,
        typeof this.responseText === "string" ? this.responseText : JSON.stringify(this.response), body); }
      catch (_) {}
    }, {once: true});
    return send.call(this, body);
  };
  const fetch = window.fetch;
  window.fetch = function(...args) {
    const request = args[0];
    const url = request instanceof Request ? request.url : String(request);
    const body = args[1] && typeof args[1].body === "string" ? args[1].body : "";
    return fetch.apply(this, args).then(response => {
      response.clone().text().then(text => record(url, response.status, text, body)).catch(() => {});
      return response;
    });
  };
})();""".replace("__ALLOWED_PATHS__", allowed_paths)


def _target_id(value: str, kind: str) -> str:
    """Accept a Kuaishou identifier or its matching official profile/video URL."""
    target = str(value or "").strip()
    if "://" in target:
        try:
            parsed = urlsplit(target)
            _ = parsed.port
        except ValueError:
            raise ReachError(BAD_INPUT, "target must be a Kuaishou ID or official URL") from None
        if (parsed.scheme.lower() not in {"http", "https"}
                or parsed.hostname not in {"kuaishou.com", "www.kuaishou.com"}
                or parsed.username is not None or parsed.password is not None or parsed.port):
            raise ReachError(BAD_INPUT, "target must be a Kuaishou ID or official URL")
        parts = [part for part in parsed.path.split("/") if part]
        route = "short-video" if kind == "work" else "profile"
        if len(parts) != 2 or parts[0] != route:
            raise ReachError(BAD_INPUT, f"target must be a Kuaishou {route} URL")
        target = parts[1]
    if not _ID_RE.fullmatch(target):
        raise ReachError(BAD_INPUT, "target must be a valid Kuaishou ID or official URL")
    return target


def _page_url(action: str, value: str = "") -> str:
    """Build a fixed Kuaishou page URL from validated user input."""
    if action == "search":
        return f"{_ORIGIN}/search/video?searchKey={quote(value, safe='')}"
    if action == "hot":
        return f"{_ORIGIN}/new-reco"
    if action == "read":
        return f"{_ORIGIN}/short-video/{quote(_target_id(value, 'work'), safe='')}"
    if action == "user_works":
        return f"{_ORIGIN}/profile/{quote(_target_id(value, 'user'), safe='')}"
    raise ReachError(BAD_INPUT, f"unsupported Kuaishou action: {action}")


def _wait_for_page_target(target_id: str, timeout: float = 8.0) -> bool:
    """Wait until Chrome exposes the new tab's page WebSocket through CDP."""
    from agent_reach.runtime import cdp

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        targets = cdp._json("/json/list")
        if isinstance(targets, list) and any(
            isinstance(target, dict)
            and target.get("id") == target_id
            and target.get("type") == "page"
            for target in targets
        ):
            return True
        time.sleep(0.1)
    return False


def _visit_page(url: str, paths: tuple[str, ...], timeout: float) -> list[dict]:
    """Open one Kuaishou page in the Reach-owned browser and capture its read response."""
    from agent_reach.runtime import browser, cdp, session_reuse

    session_reuse.prepare("kuaishou")
    browser.ensure_running()
    created = cdp.call("Target.createTarget", {"url": "about:blank"})
    target_id = str((created or {}).get("targetId") or "")
    if not target_id:
        raise ReachError(UPSTREAM_BROKEN, "Could not create a Kuaishou tab in the Agent Reach browser")
    try:
        if not _wait_for_page_target(target_id):
            raise ReachError(UPSTREAM_BROKEN, "The Kuaishou browser tab did not become available")
        with cdp.TargetSession(target_id) as page:
            for method in ("Page.enable", "Runtime.enable"):
                if page.call(method) is None:
                    raise ReachError(UPSTREAM_BROKEN, "Could not prepare the Kuaishou browser page")
            script = _capture_script(paths)
            if page.call(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": script},
            ) is None:
                raise ReachError(UPSTREAM_BROKEN, "Could not observe Kuaishou page requests")
            if page.call("Page.navigate", {"url": url}) is None:
                raise ReachError(UPSTREAM_BROKEN, "Could not open the Kuaishou page")

            deadline = time.monotonic() + max(1.0, timeout)
            while time.monotonic() < deadline:
                evaluated = page.call("Runtime.evaluate", {
                    "expression": "JSON.stringify(window.__agentReachKuaishouResponses || [])",
                    "returnByValue": True,
                })
                remote = (evaluated or {}).get("result") or {}
                encoded = remote.get("value")
                try:
                    rows = json.loads(encoded) if isinstance(encoded, str) else []
                except json.JSONDecodeError:
                    rows = []
                if isinstance(rows, list) and rows:
                    return [row for row in rows if isinstance(row, dict)]
                time.sleep(0.2)
            raise ReachError(
                UPSTREAM_BROKEN,
                "Kuaishou did not issue the expected read request; check the page and login state",
                hint=_LOGIN_HINT,
            )
    finally:
        cdp.call("Target.closeTarget", {"targetId": target_id})
        browser.save_session()


def _response(rows: list[dict], path: str, operation: str = "") -> tuple[dict, dict]:
    """Select the matching API response and reject errors before mapping its data."""
    selected = None
    for row in rows:
        if row.get("path") != path:
            continue
        request_body = row.get("requestBody", "")
        if operation:
            try:
                request = json.loads(request_body) if request_body else {}
            except json.JSONDecodeError:
                continue
            if request.get("operationName") != operation:
                continue
        selected = row
        break
    if selected is None:
        raise ReachError(UPSTREAM_BROKEN, "Kuaishou did not return the expected read response")
    status = selected.get("status")
    if status == 401:
        raise ReachError(NEED_LOGIN, "Kuaishou rejected the current session", hint=_LOGIN_HINT)
    if status == 403:
        raise ReachError(PLATFORM_BLOCKED, "Kuaishou requires an official browser verification")
    if status == 404:
        raise ReachError(NOT_FOUND, "Kuaishou content was not found")
    if status == 429:
        raise ReachError(RATE_LIMITED, "Kuaishou rate-limited this request")
    if not isinstance(status, int) or status < 200 or status >= 300:
        raise ReachError(UPSTREAM_BROKEN, "Kuaishou returned an unsuccessful read response")
    try:
        payload = json.loads(str(selected.get("body") or ""))
    except json.JSONDecodeError:
        raise ReachError(UPSTREAM_BROKEN, "Kuaishou returned an unreadable read response") from None
    if not isinstance(payload, dict):
        raise ReachError(UPSTREAM_BROKEN, "Kuaishou returned an unexpected read response")
    if path == _GRAPHQL_PATH:
        if payload.get("errors"):
            raise ReachError(UPSTREAM_BROKEN, "Kuaishou rejected the GraphQL read request")
    elif payload.get("result") != 1:
        raise ReachError(UPSTREAM_BROKEN, "Kuaishou returned an unsuccessful business result")
    return selected, payload


def _published_at(value) -> str | None:
    """Normalize the verified Kuaishou timestamp field without changing its unit."""
    try:
        stamp = float(value)
        if stamp > 100_000_000_000:
            stamp /= 1000
        return datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def _work_item(row: dict[str, Any]) -> dict[str, Any] | None:
    """Map the verified photo/author fields into Agent Reach's shared item shape."""
    photo_value = row.get("photo")
    photo: dict[str, Any] = photo_value if isinstance(photo_value, dict) else row
    author_value = row.get("author")
    author: dict[str, Any] = author_value if isinstance(author_value, dict) else {}
    work_id = str(photo.get("id") or photo.get("photoId") or "")
    if not _ID_RE.fullmatch(work_id):
        return None
    caption = str(photo.get("caption") or "")
    return make_item(
        title=caption or work_id,
        url=f"{_ORIGIN}/short-video/{quote(work_id, safe='')}",
        author=str(author.get("name") or "") or None,
        published_at=_published_at(photo.get("timestamp")),
        text=caption or None,
        raw=row,
    )


def _feed_items(rows: list[dict[str, Any]], path: str, *, limit: int) -> list[dict[str, Any]]:
    """Read a first-page REST feed using the verified `feeds` response field."""
    _selected, payload = _response(rows, path)
    feeds = payload.get("feeds")
    if not isinstance(feeds, list):
        raise ReachError(UPSTREAM_BROKEN, "Kuaishou feed response did not contain a feeds list")
    mapped: list[dict[str, Any] | None] = [
        _work_item(feed) for feed in feeds if isinstance(feed, dict)
    ]
    items = [item for item in mapped if item is not None][:limit]
    if not items:
        raise ReachError(UPSTREAM_BROKEN, "Kuaishou returned no recognizable works")
    return items


class KuaishouChannel(Channel):
    name = "kuaishou"
    description = "快手作品搜索、热门、详情和用户作品"
    level = "experimental"
    login_url = "https://www.kuaishou.com/"
    domains = ("kuaishou.com",)
    prereqs = ("chrome",)

    actions = (
        Action(
            "search",
            "Search Kuaishou videos",
            (
                Param("query", "what to search for"),
                Param("limit", "max results (1..20)", required=False, type=int, default=5),
            ),
            (("browser-cdp", "_browser_search"),),
            live_test={"query": "黑丝白丝", "limit": 2},
            timeout=60,
        ),
        Action(
            "hot",
            "Trending Kuaishou videos",
            (Param("limit", "max results (1..20)", required=False, type=int, default=10),),
            (("browser-cdp", "_browser_hot"),),
            timeout=60,
        ),
        Action(
            "read",
            "Read a Kuaishou video detail",
            (Param("target", "video ID or official short-video URL"),),
            (("browser-cdp", "_browser_read"),),
            public_web=("kuaishou.com/short-video/",),
            timeout=60,
        ),
        Action(
            "user_works",
            "Read the first page of a public user's videos",
            (
                Param("target", "user eid or official profile URL"),
                Param("limit", "max results (1..20)", required=False, type=int, default=10),
            ),
            (("browser-cdp", "_browser_user_works"),),
            timeout=60,
        ),
    )

    def setup_problems(self):
        from agent_reach.runtime.browser_binding import setup_problems

        return setup_problems(self.name)

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "kuaishou.com")

    def validate_params(self, action: str, params: dict) -> None:
        if action in {"search", "hot", "user_works"}:
            try:
                limit = int(params.get("limit", 5))
            except (TypeError, ValueError):
                raise ReachError(BAD_INPUT, "limit must be an integer from 1 to 20") from None
            if not 1 <= limit <= 20:
                raise ReachError(BAD_INPUT, "limit must be an integer from 1 to 20")
        if action == "search" and not str(params.get("query") or "").strip():
            raise ReachError(BAD_INPUT, "query must not be empty")
        if action == "read":
            _target_id(params.get("target", ""), "work")
        if action == "user_works":
            _target_id(params.get("target", ""), "user")

    def _browser_search(self, *, query: str, limit: int, timeout: float) -> list:
        rows = _visit_page(
            _page_url("search", query.strip()), (_SEARCH_PATH,), timeout
        )
        return _feed_items(rows, _SEARCH_PATH, limit=limit)

    def _browser_hot(self, *, limit: int, timeout: float) -> list:
        rows = _visit_page(_page_url("hot"), (_HOT_PATH,), timeout)
        return _feed_items(rows, _HOT_PATH, limit=limit)

    def _browser_read(self, *, target: str, timeout: float) -> list:
        work_id = _target_id(target, "work")
        rows = _visit_page(_page_url("read", work_id), (_GRAPHQL_PATH,), timeout)
        _selected, payload = _response(rows, _GRAPHQL_PATH, "visionVideoDetail")
        detail = ((payload.get("data") or {}).get("visionVideoDetail")
                  if isinstance(payload.get("data"), dict) else None)
        if not isinstance(detail, dict) or detail.get("status") != 1:
            raise ReachError(NOT_FOUND, "Kuaishou video detail was not found")
        photo = detail.get("photo")
        if not isinstance(photo, dict) or str(photo.get("id") or "") != work_id:
            raise ReachError(UPSTREAM_BROKEN, "Kuaishou returned a different video than requested")
        item = _work_item(detail)
        if item is None:
            raise ReachError(UPSTREAM_BROKEN, "Kuaishou video detail is missing its photo ID")
        return [item]

    def _browser_user_works(self, *, target: str, limit: int, timeout: float) -> list:
        rows = _visit_page(
            _page_url("user_works", target), (_PROFILE_FEED_PATH,), timeout
        )
        return _feed_items(rows, _PROFILE_FEED_PATH, limit=limit)
