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
import urllib.request

from agent_reach.probe import probe_command

from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TIMEOUT = 10
_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=test&page=1"


def _search_api_ok() -> bool:
    """Return True if Bilibili search API responds with code 0."""
    req = urllib.request.Request(_SEARCH_API, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data.get("code") == 0
    except Exception:
        return False


class BilibiliChannel(Channel):
    name = "bilibili"
    description = "Bilibili videos, subtitles, and search"
    backends = ["bili-cli", "OpenCLI", "Bilibili Search API"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "bilibili.com", "b23.tv")

    def check(self, config=None):
        """Probe candidates in order; first fully-usable backend wins."""
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "bili-cli":
                result = self._check_bili_cli()
            elif backend == "OpenCLI":
                result = self._check_opencli()
            else:
                result = self._check_search_api()
            if result is None:
                continue
            findings.append((backend, *result))

        # Preserve recovery guidance for broken backends even when another candidate succeeds
        broken_notes = [m for _, s, m in findings if s == "error"]

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend if status == "ok" else None
                    if broken_notes:
                        message += "\n[Fallback backend issue] " + "; ".join(broken_notes)
                    return status, message

        if findings:
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "No usable Bilibili backend is available (the Search API is also unreachable, possibly due to networking). Recommended:\n"
            "  pipx install bilibili-cli (search/hot/video details, no login required)\n"
            "  Or install OpenCLI on desktop to add subtitle support: agent-reach install --system --channels opencli"
        )

    def _check_bili_cli(self):
        """bili-cli candidate. None = not installed."""
        probe = probe_command("bili", ["--version"], timeout=10, package="bilibili-cli")
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", "The bili command exists but cannot execute\n" + probe.hint
        if not probe.ok:
            return "warn", f"bili-cli probe failed ({probe.status}); run `bili status` for details"
        return "ok", (
            "bili-cli is available (search/hot/rankings/video details/audio, no login required; "
            "subtitles require OpenCLI. Upstream has been inactive since 2026-03)"
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
                "OpenCLI bridge is connected, but the Bilibili page, login state, and actual commands"
                "were not verified live; Doctor does not execute platform commands, so this is not marked available yet."
            )
        return "warn", st.hint

    def _check_search_api(self):
        """Zero-dependency search API fallback. None = unreachable."""
        if not _search_api_ok():
            return None
        return "ok", (
            "Bilibili Search API is reachable (search only, direct curl access)."
            "For full functionality, install bili-cli: pipx install bilibili-cli"
        )
