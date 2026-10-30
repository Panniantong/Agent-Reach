# -*- coding: utf-8 -*-
"""Boss search through the verified public API and an explicitly selected existing CDP page."""

import json
import os
from pathlib import Path

from agent_reach.runtime.result import (
    NEED_LOGIN,
    NEED_SETUP,
    PLATFORM_BLOCKED,
    RATE_LIMITED,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)
from agent_reach.runtime.run import CommandFailed, run_cmd
from agent_reach.runtime.sessions import session_dir
from agent_reach.runtime.tools import resolve
from agent_reach.utils.url import host_matches

from .base import Action, Channel, Param


class BossChannel(Channel):
    name = "boss"
    description = "Boss直聘 职位搜索与 JD"
    level = "optional"
    login_url = "https://www.zhipin.com/web/user/?ka=header-login"
    session = "boss-agent-cli"
    session_home = False
    login_argv = ("boss", "--data-dir", "{session}/.boss-agent", "--cdp-url", "http://127.0.0.1:9222", "login", "--cdp")
    legacy_state = (".boss-agent",)
    tools = ("boss-agent-cli",)
    prereqs = ("chrome",)
    actions = (
        Action(
            "search",
            "Search jobs using a configured browser session",
            (
                Param("query", "job keywords"),
                Param("city", "city, e.g. 深圳", required=False),
                Param("limit", "max results", required=False, type=int, default=10),
            ),
            (("opencli", "_opencli_search"), ("boss-agent-cli", "_cli_search")),
            live_test={"query": "Python", "city": "深圳", "limit": 3},
            timeout=90,
            public_web=("zhipin.com/job_detail/",),
        ),
        Action("read", "Read a direct BOSS job URL", (Param("target", "full job URL"),),
               (("boss-agent-cli", "_cli_read"), ("opencli", "_opencli_read")), timeout=90,
               public_web=("zhipin.com/job_detail/",)),
    )

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "zhipin.com")

    # ── unified entry backends ──

    def _cli_search(self, *, query: str, city, limit: int, timeout: float) -> list:
        return self._native({"action": "search", "query": query, "city": city, "limit": limit}, timeout)

    def _cli_read(self, *, target: str, timeout: float) -> list:
        import re

        match = re.search(r"/job_detail/([A-Za-z0-9_-]+)\.html", str(target))
        if not host_matches(str(target), "zhipin.com") or not match:
            raise ReachError("BAD_INPUT", "Expected a direct BOSS job URL")
        return self._native({"action": "read", "job_id": match.group(1)}, timeout)

    def _native(self, payload: dict, timeout: float) -> list:
        from agent_reach.runtime import state
        from agent_reach.runtime.browser_binding import wait_lock
        from agent_reach.runtime.onboarding import require_boss_cdp
        endpoint = require_boss_cdp()
        exe = resolve("boss")
        if not exe:
            raise ReachError(NEED_SETUP, "Run agent-reach add boss first")
        python = Path(exe).with_name("python.exe" if os.name == "nt" else "python")
        stamp = state.load().get("session_reuse", {}).get("boss", {}).get("at")
        payload = {**payload, "cdp_url": endpoint, "data_dir": str(session_dir(self.session) / ".boss-agent"),
                   "session_stamp": stamp}
        limit = payload.get("limit", 1)
        runner = Path(__file__).parents[1] / "backends" / "boss_native.py"
        try:
            with wait_lock(endpoint, wait=timeout):
                out = run_cmd([str(python), str(runner), json.dumps(payload)], timeout=timeout)
        except CommandFailed as exc:
            out = exc.stdout
            if "{" not in out:
                raise
        try:
            payload = json.loads(out[out.index("{"):])
        except ValueError:
            raise ReachError(UPSTREAM_BROKEN, "boss-agent-cli returned unreadable output") from None
        if not payload.get("ok"):
            err = payload.get("error") or {}
            code = str(err.get("code", "")).upper()
            message = str(err.get("message", "boss-agent-cli failed"))[:300]
            if code in {"PLATFORM_BLOCKED", "ACCOUNT_RISK", "ENVIRONMENT_RISK", "CAPTCHA_REQUIRED"} or any(
                word in message for word in ("code 36", "code 37", "环境异常", "环境存在异常", "验证码", "安全验证", "风控")
            ):
                raise ReachError(PLATFORM_BLOCKED, message)
            if code in {"RATE_LIMITED", "RATE_LIMIT"}:
                raise ReachError(RATE_LIMITED, message)
            if code == "NEED_SETUP":
                raise ReachError(NEED_SETUP, message)
            if "AUTH" in code or "LOGIN" in code:
                raise ReachError(
                    NEED_LOGIN, message,
                    hint="Run agent-reach login boss; reuse the selected CDP browser and sync only after confirming login.",
                )
            raise ReachError(UPSTREAM_BROKEN, message)
        data = payload.get("data")
        rows = data if isinstance(data, list) else ((data or {}).get("items") or (data or {}).get("jobs") or [])
        items = []
        for r in rows[:limit]:
            if not isinstance(r, dict):
                continue
            job_id = r.get("job_id")
            items.append(
                make_item(
                    title=r.get("title"),
                    url=f"https://www.zhipin.com/job_detail/{job_id}.html" if job_id else None,
                    author=r.get("company"),
                    text=r.get("description") or " · ".join(str(x) for x in (r.get("salary"), r.get("city"), r.get("experience"), r.get("education")) if x),
                    raw=r,
                )
            )
        return items


    def _opencli_search(self, *, query, city, limit, timeout):
        from agent_reach.backends.opencli import opencli_call, opencli_items
        rows = opencli_call("boss", ["search", query, "--city", city or "全国", "--limit", str(limit)], timeout=timeout)
        return opencli_items(rows)[:limit]


    def _opencli_read(self, *, target: str, timeout: float) -> list:
        import re

        from agent_reach.backends.opencli import opencli_call, opencli_items
        if not host_matches(str(target), "zhipin.com"):
            raise ReachError("BAD_INPUT", "Expected a direct zhipin.com job URL")
        match = re.search(r"/job_detail/([A-Za-z0-9_-]+)\.html", str(target))
        if not match:
            raise ReachError("BAD_INPUT", "Expected a direct BOSS job URL")
        try:
            rows = opencli_call("boss", ["detail", match.group(1)], timeout=timeout,
                                login_hint="Run agent-reach login boss; complete login yourself in the dedicated browser.")
        except ReachError as exc:
            # Upstream's detector also matches hidden login components on readable
            # job pages. Its message alone cannot establish an expired session.
            if exc.code == NEED_LOGIN and "BOSS redirected the job detail page to the login flow" in exc.message:
                raise ReachError(UPSTREAM_BROKEN, "OpenCLI could not extract this BOSS JD; its login signal is ambiguous",
                                 hint="Check the existing job page. Do not ask for repeated login based on this adapter error.") from None
            raise
        return opencli_items(rows)[:1]
