# -*- coding: utf-8 -*-
"""抖音 (Douyin) — yt-dlp + 浏览器 Cookie。

抖音风控要求请求携带 Cookie（yt-dlp 裸连报 "Fresh cookies needed"），
所以本频道在 yt-dlp 探活之外还要确认 Cookie 来源已配置：

  - ``douyin_cookies_from``：浏览器名，yt-dlp ``--cookies-from-browser`` 直读
  - ``douyin_cookies``：Cookie header 字符串，yt-dlp ``--add-headers`` 注入

yt-dlp 持续维护且原生支持抖音（2026-07 桌面 Chrome 实测：元数据 + 音频
均可取），满足频道回归标准 —— PR #347 移除旧抖音频道的原因是当时的
上游工具停更，而非平台不可达。
"""

from agent_reach.probe import probe_command

from .base import Channel

_DOUYIN_HOSTS = ("douyin.com", "iesdouyin.com")


def is_douyin_url(url: str) -> bool:
    """Return True if url belongs to Douyin (incl. v.douyin.com short links)."""
    from urllib.parse import urlparse

    d = urlparse(url).netloc.lower()
    return any(h in d for h in _DOUYIN_HOSTS)


def douyin_cookie_args(config) -> list:
    """Build yt-dlp CLI args carrying the configured Douyin cookies.

    ``douyin_cookies_from``（浏览器名）优先于 ``douyin_cookies``（header
    字符串）：浏览器直读始终拿到最新 Cookie，手动粘贴的字符串会过期。
    """
    if config is None:
        return []
    browser = config.get("douyin_cookies_from")
    if browser:
        return ["--cookies-from-browser", browser]
    cookie = config.get("douyin_cookies")
    if cookie:
        return ["--add-headers", f"Cookie:{cookie}"]
    return []


class DouyinChannel(Channel):
    name = "douyin"
    description = "抖音视频"
    backends = ["yt-dlp"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        return is_douyin_url(url)

    def check(self, config=None):
        # 真跑 yt-dlp --version 探活，区分未装 / venv 断链 / 跑不动
        probe = probe_command("yt-dlp", ["--version"], timeout=10, package="yt-dlp")
        if probe.status == "missing":
            self.active_backend = None
            return "off", "yt-dlp 未安装。安装：pip install yt-dlp"
        if probe.status == "broken":
            self.active_backend = None
            return "error", f"yt-dlp 已安装但无法执行\n{probe.hint}"
        if not probe.ok:  # timeout / error：装了但跑不动
            self.active_backend = None
            detail = probe.hint or probe.output or probe.status
            return "error", f"yt-dlp 无法正常运行：{detail}"
        # yt-dlp 本体是活的；Cookie 是否配置只影响 ok/warn，不影响后端归属
        self.active_backend = "yt-dlp"
        if not douyin_cookie_args(config):
            return "warn", (
                "yt-dlp 可用，但抖音风控要求登录态 Cookie（裸连报 Fresh cookies needed）。\n"
                "  浏览器里登录过 douyin.com 后运行：\n"
                "  agent-reach configure douyin-cookies chrome\n"
                "  或：agent-reach configure --from-browser chrome"
            )
        return "ok", (
            "可提取抖音视频元数据和音频（yt-dlp + Cookie）。"
            "用法见 references/video.md 抖音小节"
        )

    def transcribe(self, url: str, *, provider: str = "auto", config=None) -> str:
        """Download a Douyin video's audio and return its transcript.

        Delegates to :func:`agent_reach.transcribe.transcribe`, which injects
        the configured Douyin cookies into yt-dlp for Douyin URLs.
        """
        from agent_reach.transcribe import transcribe as _transcribe

        return _transcribe(url, provider=provider, config=config)
