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
