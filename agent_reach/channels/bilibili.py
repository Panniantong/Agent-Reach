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
    description = "B站视频、字幕和搜索"
    backends = ["bili-cli", "OpenCLI", "B站搜索 API"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from ..utils.urlmatch import host_matches
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

        # 有后端断链时，即使别的候选兜底成功也要把处方带出来
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
            "没有可用的 B站后端（搜索 API 也不可达，可能是网络问题）。推荐：\n"
            "  pipx install bilibili-cli（搜索/热门/视频详情，无需登录）\n"
            "  或桌面装 OpenCLI（额外解锁字幕）：agent-reach install --channels opencli"
        )

    def _check_bili_cli(self):
        """bili-cli candidate. None = not installed."""
        probe = probe_command("bili", ["--version"], timeout=10, package="bilibili-cli")
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", "bili 命令存在但无法执行\n" + probe.hint
        if not probe.ok:
            return "warn", f"bili-cli 探测失败（{probe.status}），运行 `bili status` 查看详情"
        return "ok", (
            "bili-cli 可用（搜索/热门/排行/视频详情/音频，无需登录；"
            "字幕需 OpenCLI。上游 2026-03 起停更）"
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
                "OpenCLI 可用（复用浏览器登录态）。用法："
                "opencli bilibili search/video/subtitle/ranking -f yaml"
            )
        return "warn", st.hint

    def _check_search_api(self):
        """Zero-dependency search API fallback. None = unreachable."""
        if not _search_api_ok():
            return None
        return "ok", (
            "B站搜索 API 可达（仅搜索，curl 直连）。"
            "完整功能建议安装 bili-cli：pipx install bilibili-cli"
        )
