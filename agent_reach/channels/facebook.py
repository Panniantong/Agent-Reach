# -*- coding: utf-8 -*-
"""Facebook — public videos via yt-dlp, text posts via Jina Reader."""

import shutil
from urllib.parse import urlparse

from .base import Channel


class FacebookChannel(Channel):
    """Facebook public videos and posts.

    - Public videos: extracted via yt-dlp
    - Text posts / articles: fetched via Jina Reader (no installation required)
    """

    name = "facebook"
    description = "Facebook 公开帖子和视频"
    backends = ["yt-dlp", "Jina Reader"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        """Return True for facebook.com, m.facebook.com, fb.com and fb.watch URLs."""
        d = urlparse(url).netloc.lower()
        return "facebook.com" in d or "fb.com" in d or "fb.watch" in d

    def check(self, config=None):
        """Check backend availability.

        Returns:
            ('ok', msg)   — yt-dlp present; full video + text support
            ('warn', msg) — yt-dlp missing; text posts still work via Jina Reader
            ('off', msg)  — neither backend available (should not happen; Jina Reader is built-in)
        """
        has_ytdlp = bool(shutil.which("yt-dlp"))
        if has_ytdlp:
            return "ok", "可提取公开视频元数据；文字帖子可通过 Jina Reader 读取"
        return "warn", (
            "yt-dlp 未安装，视频提取不可用。安装：pip install yt-dlp\n"
            "  文字帖子仍可通过 Jina Reader 读取。"
        )

    def read(self, url: str) -> str:
        """Fetch content from a Facebook URL.

        Videos are routed to yt-dlp; text posts / articles use Jina Reader.
        Raises NotImplementedError until upstream integration is wired in.
        """
        raise NotImplementedError(
            "Direct read() not yet implemented. "
            "For videos call yt-dlp directly; for text posts use Jina Reader at "
            "https://r.jina.ai/<url>."
        )

    def search(self, query: str) -> str:
        """Search Facebook content.

        Facebook has no public search API. Raises NotImplementedError.
        """
        raise NotImplementedError(
            "Facebook search is not supported — no public search API available."
        )
