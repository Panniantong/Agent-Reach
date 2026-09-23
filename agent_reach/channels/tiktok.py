# -*- coding: utf-8 -*-
"""TikTok — yt-dlp reads a public video URL; OpenCLI unlocks search/profile.

yt-dlp ships a native TikTok extractor that generally handles a single
public video URL (including vm./vt. short links) without login. Unlike
Bilibili, this is not a hard, permanent block — TikTok's anti-bot
occasionally serves a JS-challenge page that breaks extraction, but
retrying or switching network usually recovers it, so yt-dlp stays a real
backend here (tracked upstream: yt-dlp/yt-dlp#15418).

Search, profile, explore and any interaction commands have no
zero-config path — TikTok requires a logged-in browser session for those,
served through OpenCLI (see docs/adapters in jackwener/opencli).
"""

from agent_reach.probe import probe_command
from agent_reach.utils.url import host_matches

from .base import Channel

_YTDLP_UPGRADE_COMMAND = 'python -m pip install -U "yt-dlp[default]"'


class TikTokChannel(Channel):
    name = "tiktok"
    description = "TikTok 视频阅读（yt-dlp）+ 搜索/主页（需登录）"
    backends = ["yt-dlp", "OpenCLI"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "tiktok.com")

    def check(self, config=None):
        """Probe candidates in order; first fully-usable backend wins.

        与 Bilibili 同一套两段式：先收集全部候选状态，第一个 ok 获胜；
        没有 ok 才轮到第一个 warn。
        """
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "yt-dlp":
                result = self._check_ytdlp()
            elif backend == "OpenCLI":
                result = self._check_opencli()
            else:
                continue
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
            "TikTok 后端均不可用。安装 yt-dlp 可读取单条公开视频（无需登录）：\n"
            f"  {_YTDLP_UPGRADE_COMMAND}\n"
            "搜索/主页/关注列表需要 OpenCLI（浏览器登录态）：\n"
            "  agent-reach install --system --channels opencli"
        )

    def _check_ytdlp(self):
        """yt-dlp candidate. None = not installed."""
        probe = probe_command("yt-dlp", ["--version"], timeout=10, package="yt-dlp")
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", "yt-dlp 命令存在但无法执行\n" + probe.hint
        if not probe.ok:
            return "warn", f"yt-dlp 探测失败（{probe.status}）"
        return "ok", (
            "yt-dlp 可读取单条公开 TikTok 视频（信息+字幕，无需登录）。"
            "TikTok 反爬偶发导致提取失败属已知上游问题，重试或换网络通常可恢复。"
            "搜索/主页/关注列表需 OpenCLI。"
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
                "OpenCLI 桥接已连接，但 TikTok 登录态和实际命令未实时验证；"
                "Doctor 不执行平台命令，因此当前不标记为可用。"
            )
        return "warn", st.hint
