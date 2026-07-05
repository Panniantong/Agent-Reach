# -*- coding: utf-8 -*-
"""Douyin 抖音 — multi-backend: OpenCLI / yt-dlp.

OpenCLI (browser session) is the full backend — search / user-videos /
videos / hashtag by reusing the user's logged-in Chrome. yt-dlp is a
login-free fallback that pulls a single video's stream + metadata by URL
(it has a native Douyin extractor) but does NOT do search or profile
listing — so it only wins when OpenCLI is unavailable (e.g. on a server).
"""

from agent_reach.probe import probe_command

from .base import Channel


class DouyinChannel(Channel):
    name = "douyin"
    description = "抖音视频、用户主页和搜索"
    backends = ["OpenCLI", "yt-dlp"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        # "douyin.com" substring also covers the v.douyin.com short-link host
        return "douyin.com" in d or "iesdouyin.com" in d

    def check(self, config=None):
        """Probe candidates in order; first fully-usable backend wins.

        与 twitter/bilibili 同一套两段式：先收集全部候选状态，第一个 ok
        获胜；没有 ok 才轮到第一个 warn——否则「装了但没登录」的 OpenCLI
        会把免登录、完整可用的 yt-dlp 挡在后面。
        """
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "OpenCLI":
                result = self._check_opencli()
            else:
                result = self._check_ytdlp()
            if result is None:
                continue  # not installed — not a candidate
            findings.append((backend, *result))

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend
                    return status, message

        if findings:  # only broken candidates left
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "未安装任何抖音后端。推荐：\n"
            "  桌面：agent-reach install --channels opencli\n"
            "       （复用 Chrome 登录态，解锁搜索/用户主页/话题）\n"
            "  或免登录抓单条视频：pip install yt-dlp"
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
                "opencli douyin search/user-videos/videos/hashtag -f yaml"
            )
        return "warn", st.hint

    def _check_ytdlp(self):
        """yt-dlp candidate — login-free single-video pull. None = not installed."""
        probe = probe_command("yt-dlp", ["--version"], timeout=10, package="yt-dlp")
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", "yt-dlp 命令存在但无法执行\n" + probe.hint
        if not probe.ok:  # timeout / error：装了但跑不动
            detail = probe.hint or probe.output or probe.status
            return "error", f"yt-dlp 无法正常运行：{detail}"
        return "ok", (
            "yt-dlp 可用（免登录按 URL 抓单条视频+元数据；搜索/用户主页需 OpenCLI）。"
            "用法：yt-dlp --dump-json <抖音视频链接>"
        )
