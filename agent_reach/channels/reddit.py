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
import time
from pathlib import Path

from agent_reach.utils.paths import (
    PrivatePathError,
    read_small_text_no_follow,
)

from .base import Channel

_CREDENTIAL_FILE = "~/.config/rdt-cli/credential.json"
_CREDENTIAL_TTL_SECONDS = 7 * 86400
_MAX_CREDENTIAL_BYTES = 1024 * 1024
# Pinned to the 0.4.2 state — PyPI still only has 0.4.1 (upstream issue #10).
_RDT_GIT_SOURCE = "git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66"

class RedditChannel(Channel):
    name = "reddit"
    description = "Reddit posts and comments"
    backends = ["OpenCLI", "rdt-cli"]
    tier = 1  # no zero-config path exists — see module docstring

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "reddit.com", "redd.it")

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
                    self.active_backend = backend if status == "ok" else None
                    return status, message

        if findings:
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "No Reddit backend is installed. NOTE: Reddit does not have a zero-configuration path "
            "(Anonymous .json has been blocked, and the official API requires manual approval). You must use the login state. Recommended: \n"
            "  Desktop: agent-reach install --system --channels opencli\n"
            "       (Reuse Chrome login status, available after logging in to reddit.com) \n"
            f"  Server/legacy: pipx install '{_RDT_GIT_SOURCE}'\n"
            "       Then `rdt login` or manually write the Cookie (see doctor tip) \n"
            "Mainland China needs a proxy to access Reddit"
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
            return "warn", (
                "The OpenCLI bridge is connected, but the Reddit login and actual commands are not verified live; "
                "Doctor does not execute platform commands and is therefore not currently marked as available."
            )
        return "warn", st.hint

    def _check_rdt(self):
        """Inspect rdt's saved credential without invoking its auto-refresh."""
        if not shutil.which("rdt"):
            return None

        credential_path = Path.home() / ".config" / "rdt-cli" / "credential.json"
        try:
            payload = read_small_text_no_follow(
                credential_path,
                max_bytes=_MAX_CREDENTIAL_BYTES,
            )
        except PrivatePathError as exc:
            return "warn", (
                f"rdt-cli is installed, but credential.json is not safe to read: {exc}."
            )
        except OSError:
            return "warn", (
                "rdt-cli is installed, but credential.json is not safe to read; "
                "Doctor has not executed `rdt status` which will automatically refresh the cookie."
            )
        if payload is None:
            return "warn", self._rdt_login_hint()
        try:
            data = json.loads(payload)
        except (UnicodeError, json.JSONDecodeError, ValueError):
            return "warn", (
                "rdt-cli is installed, but the saved credential.json cannot be parsed safely; "
                "Doctor has not executed `rdt status` which will automatically refresh the cookie."
            )
        if not isinstance(data, dict):
            return "warn", self._rdt_login_hint()
        cookies = data.get("cookies")
        if not isinstance(cookies, dict) or not cookies.get("reddit_session"):
            return "warn", self._rdt_login_hint()

        saved_at = data.get("saved_at")
        if isinstance(saved_at, (int, float)) and (
            time.time() - saved_at > _CREDENTIAL_TTL_SECONDS
        ):
            return "warn", (
                "rdt-cli is installed, but saved cookies are older than 7 days. Doctor does not allow "
                "upstream browser-cookie reads or file refreshes. Update explicitly with Cookie-Editor."
            )
        return "warn", (
            "rdt-cli is installed with explicitly saved Reddit cookies. Doctor does not execute "
            "`rdt status` to avoid automatic browser-cookie refreshes; credentials are not verified live."
        )

    @staticmethod
    def _rdt_login_hint():
        return (
            "rdt-cli is installed but no explicit cookies are available. Please use Cookie-Editor: \n"
            "  1. Install the Cookie-Editor extension from the Chrome App Store: \n"
            "     https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm\n"
            "  2. Open reddit.com in your browser (make sure you are logged in) \n"
            "  3. Click the Cookie-Editor icon, find `reddit_session`, and copy its Value\n"
            f"  4. Write the following content to {_CREDENTIAL_FILE}: \n"
            '     {"cookies": {"reddit_session": "<Paste Value>"}, '
            '"source": "manual", "username": "<your username>", '
            '"modhash": null, "saved_at": 0, "last_verified_at": null}\n\n'
            "Doctor will not run `rdt status` which automatically reads the browser and writes files."
        )
