# -*- coding: utf-8 -*-
"""Diffbot Web Search — check if the `db` CLI (diffbot-python) + token are ready.

An additional web search option alongside Exa. The invocation path is the
`db` command-line tool shipped by diffbot-python — after install the agent
calls it directly (`db web-search "query" -f text`), same as every other CLI
channel in this project. We only install / configure / health-check it.
"""

import os
from pathlib import Path

from agent_reach.probe import probe_command

from .base import Channel

#: Where Diffbot hands out free-tier API tokens.
_DIFFBOT_SIGNUP = "https://app.diffbot.com/get-started/"
#: The `db` CLI reads the token from this env var or ~/.diffbot/credentials.
_TOKEN_ENV_VAR = "DIFFBOT_API_TOKEN"
_CREDENTIALS_PATH = Path.home() / ".diffbot" / "credentials"


def _credentials_file_has_token() -> bool:
    """True if ~/.diffbot/credentials carries a non-empty DIFFBOT_API_TOKEN.

    This is the `db` CLI's own credential file (see diffbot._auth), so honoring
    it keeps doctor in sync with what `db web-search` will actually find.
    """
    try:
        if not _CREDENTIALS_PATH.exists():
            return False
        for line in _CREDENTIALS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{_TOKEN_ENV_VAR}="):
                return bool(line.split("=", 1)[1].strip())
    except OSError:
        pass
    return False


def has_token(config=None) -> bool:
    """Whether `db` can find a Diffbot token from any source it consults.

    Resolution mirrors diffbot._auth: agent-reach config (which itself falls
    back to the DIFFBOT_API_TOKEN env var) → env var → ~/.diffbot/credentials.
    """
    if config is not None and config.get("diffbot_api_token"):
        return True
    if os.environ.get(_TOKEN_ENV_VAR):
        return True
    return _credentials_file_has_token()


class DiffbotSearchChannel(Channel):
    name = "diffbot_search"
    description = "Diffbot 全网搜索"
    backends = ["Diffbot CLI (db)"]
    tier = 1  # 需免费 Token

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        self.active_backend = None
        probe = probe_command("db", ["--version"], timeout=10, package="diffbot-python")
        if probe.status == "missing":
            return "off", (
                "需要 Diffbot CLI（diffbot-python）。安装：\n"
                "  pipx install diffbot-python   （或 uv tool install diffbot-python）\n"
                "再配置 API Token（有免费额度）：\n"
                f"  agent-reach configure diffbot-key <token>   获取：{_DIFFBOT_SIGNUP}"
            )
        if probe.status == "broken":
            return "error", probe.hint or "db 无法执行，重装：pipx reinstall diffbot-python"
        if not probe.ok:  # timeout / error
            return "error", f"db 执行异常：{probe.hint or probe.output or probe.status}"
        if not has_token(config):
            return "warn", (
                "Diffbot CLI 已装，但缺少 API Token。配置后即可用：\n"
                f"  agent-reach configure diffbot-key <token>   获取：{_DIFFBOT_SIGNUP}\n"
                f"  （或 export {_TOKEN_ENV_VAR}=...）"
            )
        self.active_backend = self.backends[0]
        return "ok", 'Diffbot 全网搜索可用（db web-search "query" -f text）'
