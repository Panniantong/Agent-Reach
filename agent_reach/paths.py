"""Runtime path resolution for Agent Reach-owned data."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

AGENT_REACH_HOME_ENV = "AGENT_REACH_HOME"


def agent_reach_home(env: Mapping[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    configured = values.get(AGENT_REACH_HOME_ENV, "").strip()
    if not configured:
        return Path.home() / ".agent-reach"

    path = Path(configured).expanduser()
    if not path.is_absolute():
        raise ValueError("AGENT_REACH_HOME must be an absolute path")
    return path


def config_file(env: Mapping[str, str] | None = None) -> Path:
    return agent_reach_home(env) / "config.yaml"


def tools_dir(env: Mapping[str, str] | None = None) -> Path:
    return agent_reach_home(env) / "tools"


def xiaoyuzhou_tools_dir(env: Mapping[str, str] | None = None) -> Path:
    return tools_dir(env) / "xiaoyuzhou"


def xhs_cookie_file(env: Mapping[str, str] | None = None) -> Path:
    return agent_reach_home(env) / "xhs-cookies.json"


# ── Path report ──────────────────────────────────

import shutil

EXTERNAL_COMMANDS = ("gh", "node", "npm", "mcporter", "twitter", "rdt", "bili", "opencli")


def skill_registration_dirs(env: Mapping[str, str] | None = None) -> list[Path]:
    values = os.environ if env is None else env
    targets = [
        Path.home() / ".agents" / "skills",
        Path.home() / ".openclaw" / "skills",
        Path.home() / ".claude" / "skills",
    ]
    openclaw_home = values.get("OPENCLAW_HOME", "").strip()
    if openclaw_home:
        targets.insert(0, Path(openclaw_home).expanduser() / ".openclaw" / "skills")
    return targets


def path_report() -> dict[str, list[dict[str, object]]]:
    managed = [
        {"key": "home", "path": str(agent_reach_home()), "owner": "agent-reach"},
        {"key": "config", "path": str(config_file()), "owner": "agent-reach"},
        {"key": "tools", "path": str(tools_dir()), "owner": "agent-reach"},
        {"key": "xhs_cookies", "path": str(xhs_cookie_file()), "owner": "agent-reach"},
    ]
    registration = [
        {
            "key": f"skill_{index}",
            "path": str(parent / "agent-reach"),
            "owner": "agent-platform",
            "exists": (parent / "agent-reach").exists(),
        }
        for index, parent in enumerate(skill_registration_dirs(), start=1)
    ]
    external = [
        {
            "key": command,
            "path": shutil.which(command),
            "owner": "upstream",
        }
        for command in EXTERNAL_COMMANDS
    ]
    return {
        "managed": managed,
        "registration": registration,
        "external": external,
    }
