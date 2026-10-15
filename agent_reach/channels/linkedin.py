# -*- coding: utf-8 -*-
"""LinkedIn — job search through mcp-server-linkedin via mcporter."""

import json
from typing import Any, Dict

from agent_reach.backends.mcporter import configured_server_names
from agent_reach.runtime.result import NEED_SETUP, UPSTREAM_BROKEN, ReachError, make_item
from agent_reach.runtime.run import CommandFailed, run_cmd

from .base import Action, Channel, Param

_LINKEDIN_MCP_VERSION = "4.26.2"


def _own_config_path():
    from agent_reach.runtime import state

    return state.root() / "mcporter.json"


def _own_servers() -> dict:
    path = _own_config_path()
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")).get("mcpServers") or {})
    except (OSError, ValueError):
        return {}


def _write_own_servers(servers: dict) -> None:
    from agent_reach.runtime import state
    from agent_reach.utils.paths import atomic_write_private_text, make_private_dir

    make_private_dir(state.root())
    atomic_write_private_text(_own_config_path(), json.dumps({"mcpServers": servers}, indent=2))


class LinkedInChannel(Channel):
    name = "linkedin"
    description = "LinkedIn 职业社交"

    level = "optional"
    tools = ("mcporter",)
    prereqs = ("node", "uv")
    session = "linkedin-mcp"
    session_home = False
    login_argv = (
        "uvx", f"mcp-server-linkedin@{_LINKEDIN_MCP_VERSION}", "--login",
        "--user-data-dir", "{session}/profile", "--claim-profile-root",
    )

    def on_add(self) -> None:
        from agent_reach.runtime.sessions import session_dir
        from agent_reach.runtime.tools import resolve

        servers = _own_servers()
        servers["linkedin"] = {
            # absolute path: uvx may be our private copy, which mcporter's PATH does not have
            "command": resolve("uvx") or "uvx",
            "args": [
                f"mcp-server-linkedin@{_LINKEDIN_MCP_VERSION}",
                "--user-data-dir", f"{session_dir(self.session)}/profile", "--claim-profile-root",
            ],
            "env": {"UV_HTTP_TIMEOUT": "300"},
        }
        _write_own_servers(servers)

    def on_remove(self) -> None:
        servers = _own_servers()
        if servers.pop("linkedin", None) is not None:
            _write_own_servers(servers)

    actions = (
        Action(
            "jobs",
            "Search LinkedIn jobs",
            (
                Param("query", "job keywords"),
                Param("location", "city or country", required=False),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("linkedin-mcp", "_mcp_jobs"),),
            live_test={"query": "python", "limit": 2},
            timeout=120,
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "linkedin.com")

    # ── unified entry backends ──

    def _mcp_jobs(self, *, query: str, location, limit: int, timeout: float) -> list:
        # Prefer our own registration; fall back to one the user set up globally.
        if "linkedin" in _own_servers():
            base, server = ["mcporter", "--config", str(_own_config_path())], "linkedin"
        else:
            out = run_cmd(["mcporter", "config", "list", "--json"], timeout=min(timeout, 20))
            names = configured_server_names(out)
            _server = next((n for n in ("linkedin", "mcp-server-linkedin", "linkedin-scraper", "linkedin-scraper-mcp") if n in names), None)
            base = ["mcporter"]
            if _server is None:
                raise ReachError(NEED_SETUP, "LinkedIn is not set up", hint="Run `agent-reach add linkedin`, then `agent-reach login linkedin`.")
            server = _server
        # The official server names the query `keywords`; the scraper variants use `query`.
        args: Dict[str, Any] = {"keywords": query} if server in ("linkedin", "mcp-server-linkedin") else {"query": query, "max_results": limit}
        if location:
            args["location"] = location
        try:
            raw = run_cmd(
                [*base, "call", f"{server}.search_jobs", "--args", json.dumps(args), "--output", "json"],
                timeout=timeout,
            )
        except CommandFailed as exc:
            raise ReachError(UPSTREAM_BROKEN, exc.message) from None
        try:
            data = json.loads(raw)
        except ValueError:
            raise ReachError(UPSTREAM_BROKEN, "LinkedIn MCP returned unreadable output") from None
        rows = data if isinstance(data, list) else (data.get("results") or data.get("jobs") or [])
        return [
            make_item(
                title=r.get("title"),
                url=r.get("job_url") or r.get("url"),
                author=r.get("company"),
                text=" · ".join(x for x in (r.get("company"), r.get("location")) if x),
                raw=r,
            )
            for r in rows[:limit]
            if isinstance(r, dict)
        ]
