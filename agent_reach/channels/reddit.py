# -*- coding: utf-8 -*-
"""Reddit — multi-backend: OpenCLI / rdt-cli. Login is mandatory.

Honest tiering (live-verified 2026-06): there is NO zero-config path.
Anonymous .json endpoints are blocked (403 anti-bot, all variants), and
the official API closed self-service registration in 2025-11 (manual
approval, individual scripts rarely granted — PRAW is only an option for
users who already hold credentials). Every working backend rides a
logged-in session: OpenCLI reuses the browser's, rdt-cli imports cookies.
"""

import json
import shutil
import subprocess

from agent_reach.utils.process import utf8_subprocess_env

from .base import Channel

_CREDENTIAL_FILE = "~/.config/rdt-cli/credential.json"
# Pinned to the 0.4.2 state — PyPI still only has 0.4.1 (upstream issue #10).
_RDT_GIT_SOURCE = "git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66"

#: shell exit codes for "found but not executable/not found" (aligned with agent_reach.probe)
_BROKEN_EXIT_CODES = (126, 127)

#: rdt should be installed from fixed git source (PyPI is outdated), broken hint differs from probe's default pipx/uv
_RDT_BROKEN_HINT = (
    "rdt command exists but can't execute — usually venv interpreter lost after system Python upgrade.\n"
    "PyPI version is outdated, recommend forcing reinstall from fixed git source:\n"
    f"  pipx install --force '{_RDT_GIT_SOURCE}'"
)


class RedditChannel(Channel):
    name = "reddit"
    description = "Reddit posts and comments"
    backends = ["OpenCLI", "rdt-cli"]
    tier = 1  # no zero-config path exists — see module docstring

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "reddit.com" in d or "redd.it" in d

    def check(self, config=None):
        """Probe candidates in order; first fully-usable backend wins."""
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "OpenCLI":
                result = self._check_opencli()
            else:
                result = self._check_rdt()
            if result is None:
                continue
            findings.append((backend, *result))

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend
                    return status, message

        if findings:
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "No Reddit backend installed. Note: Reddit has no zero-config path "
            "(anonymous .json is blocked, official API requires manual approval), login is required. Recommend:\n"
            "  Desktop: agent-reach install --channels opencli\n"
            "       (reuses Chrome login session, works if you've logged into reddit.com)\n"
            f"  Server/existing: pipx install '{_RDT_GIT_SOURCE}'\n"
            "       Then `rdt login` or manually write cookies (see doctor hints)\n"
            "Accessing Reddit from mainland China requires a proxy"
        )

    def _check_opencli(self):
        """OpenCLI candidate. None = not installed."""
        from agent_reach.backends import opencli_status

        st = opencli_status()
        if not st.installed:
            return None
        if st.broken:
            return "error", st.hint
        if st.ready:
            return "ok", (
                "OpenCLI available (reuses browser login session). Usage: "
                "opencli reddit search/read/subreddit/hot -f yaml"
            )
        return "warn", st.hint

    def _check_rdt(self):
        """rdt-cli candidate. None = not installed."""
        rdt = shutil.which("rdt")
        if not rdt:
            return None

        # 不走 probe_command：实测 `rdt status --json` 成功时（rc=0）也会向 stderr
        # 打网络重试日志，probe 把 stdout+stderr 合并后 JSON 解析必炸。
        # 故保留手写 subprocess（stdout 单独捕获），但异常分类对齐 probe 语义：
        # exec 失败/126/127 → broken（venv 断链处方），TimeoutExpired → 超时。
        try:
            r = subprocess.run(
                [rdt, "status", "--json"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                env=utf8_subprocess_env(),
            )
        except subprocess.TimeoutExpired:
            return "error", "rdt timed out (>10s), Reddit status unknown. Retry later or run `rdt status` for details"
        except OSError:
            # Includes FileNotFoundError: which hit but exec failed = venv broken (probe's broken)
            return "error", _RDT_BROKEN_HINT

        if r.returncode in _BROKEN_EXIT_CODES:
            return "error", _RDT_BROKEN_HINT

        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else "no output"
            return "error", f"rdt exited abnormally (exit {r.returncode}): {tail}. Run `rdt status` for details"

        # 进程正常退出 → rdt 本身是活的（无论登录与否）
        try:
            data = json.loads(r.stdout or "")
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            return "warn", "rdt-cli available but status output unparseable, run `rdt status` to check login status"

        info = data.get("data")
        if not isinstance(info, dict):
            info = {}
        authenticated = info.get("authenticated", False)
        username = info.get("username") or ""

        if authenticated:
            suffix = f" (logged in as: {username})" if username else ""
            return "ok", (
                f"rdt-cli available{suffix} (search posts, read full text, view comments; "
                "upstream stopped updating 2026-03, desktop users should migrate to OpenCLI)"
            )

        return "warn", (
            "rdt-cli installed but not logged in. Reddit requires authentication since 2024, "
            "all requests return 403 when not logged in.\n\n"
            "Method 1 (automatic): Run `rdt login`\n"
            "  First log into reddit.com in browser, then run this command to auto-extract cookies.\n\n"
            "Method 2 (manual, for Chrome/Edge 127+ when auto-extraction fails):\n"
            "  1. Install Cookie-Editor extension from Chrome Web Store:\n"
            "     https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm\n"
            "  2. Open reddit.com in browser (ensure logged in)\n"
            "  3. Click Cookie-Editor icon, find `reddit_session`, copy its Value\n"
            f"  4. Write the following to {_CREDENTIAL_FILE}:\n"
            '     {"cookies": {"reddit_session": "<paste Value>"}, '
            '"source": "manual", "username": "<your username>", '
            '"modhash": null, "saved_at": 0, "last_verified_at": null}\n\n'
            "Verify: `rdt status --json` to confirm authenticated: true"
        )
