# -*- coding: utf-8 -*-
"""Web Search — multi-backend: Exa via mcporter / DuckDuckGo.

Exa provides higher-quality semantic search (especially for English/tech
content) but requires mcporter (npm). DuckDuckGo is free, zero-config,
and works everywhere — a reliable fallback when Exa isn't set up, and
an alternative path to content from platforms that are hard to access
directly (login-walled, geo-blocked, etc.).

Backend routing: Exa first (quality), DuckDuckGo second (zero-config).
"""

import shutil
import subprocess
import sys

from agent_reach.probe import probe_command
from agent_reach.utils.process import utf8_subprocess_env

from .base import Channel

#: mcporter 是 npm 包，断链处方与默认的 pipx/uv 不同
_MCPORTER_BROKEN_HINT = "mcporter 无法执行（node 环境损坏），重装：\n  npm install -g mcporter"

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _ddg_cli_available() -> bool:
    """True if the `ddgs` CLI (from duckduckgo-search) is on PATH and runnable."""
    ddgs = shutil.which("ddgs")
    if not ddgs:
        return False
    try:
        r = subprocess.run(
            [ddgs, "--version"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=utf8_subprocess_env(),
        )
        return r.returncode == 0
    except Exception:
        return False


def _ddg_python_available() -> bool:
    """True if duckduckgo_search can be imported (no CLI but package installed)."""
    try:
        subprocess.run(
            [sys.executable, "-c", "from duckduckgo_search import DDGS; print('ok')"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=utf8_subprocess_env(),
        )
        return True
    except Exception:
        return False


class WebSearchChannel(Channel):
    name = "web_search"
    description = "全网搜索"
    backends = ["Exa via mcporter", "DuckDuckGo"]
    tier = 0  # DuckDuckGo provides a zero-config path

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        """Probe candidates in order; first fully-usable backend wins."""
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend.startswith("Exa"):
                result = self._check_exa()
            else:
                result = self._check_ddg()
            if result is None:
                continue
            findings.append((backend, *result))

        broken_notes = [m for _, s, m in findings if s == "error"]

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend
                    if broken_notes:
                        message += "\n[备选后端异常] " + "；".join(broken_notes)
                    return status, message

        if findings:
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "没有可用的搜索后端。推荐安装（二选一）：\n"
            "  pip install duckduckgo-search  ← 免费，零配置，装好即用\n"
            "  或：npm install -g mcporter && mcporter config add exa https://mcp.exa.ai/mcp"
        )

    def _check_exa(self):
        """Exa via mcporter candidate. None = mcporter not installed."""
        probe = probe_command(
            "mcporter", ["config", "list"], timeout=10, package="mcporter"
        )
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", _MCPORTER_BROKEN_HINT
        if not probe.ok:
            return "error", f"mcporter 执行异常：{probe.hint or probe.output or probe.status}"
        if "exa" in probe.output.lower():
            return "ok", "全网语义搜索可用（Exa，免费，无需 API Key）"
        return "warn", (
            "mcporter 已装但 Exa 未配置。运行：\n"
            "  mcporter config add exa https://mcp.exa.ai/mcp"
        )

    def _check_ddg(self):
        """DuckDuckGo candidate. None = not installed."""
        if _ddg_cli_available():
            return "ok", (
                "DuckDuckGo 搜索可用（ddgs CLI，免费，零配置）。用法：\n"
                '  ddgs text "query" -n 5'
            )
        if _ddg_python_available():
            return "ok", (
                "DuckDuckGo 搜索可用（Python 包，免费，零配置）。用法：\n"
                '  python -c "from duckduckgo_search import DDGS; '
                'print(list(DDGS().text(\'query\', max_results=5)))"'
            )
        return None  # Not installed
