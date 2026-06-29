# -*- coding: utf-8 -*-
"""TikTok — yt-dlp backend for video metadata and creator profiles.

Public TikTok videos are accessible without authentication via yt-dlp.
No API key required (tier=0).
"""

import json
import subprocess
from typing import Any, List

from agent_reach.probe import probe_command
from agent_reach.utils.process import utf8_subprocess_env

from .base import Channel


class TikTokChannel(Channel):
    name = "tiktok"
    description = "TikTok 短视频和创作者主页"
    backends = ["yt-dlp"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "tiktok.com" in d

    def check(self, config=None):
        probe = probe_command("yt-dlp", ["--version"], timeout=10, package="yt-dlp")
        if probe.status == "missing":
            self.active_backend = None
            return "off", "yt-dlp 未安装。安装：pip install yt-dlp"
        if probe.status == "broken":
            self.active_backend = None
            return "error", f"yt-dlp 已安装但无法执行\n{probe.hint}"
        if not probe.ok:
            self.active_backend = None
            detail = probe.hint or probe.output or probe.status
            return "error", f"yt-dlp 无法正常运行：{detail}"
        self.active_backend = "yt-dlp"
        return "ok", "可提取视频信息和创作者主页"

    def read(self, url: str) -> dict:
        """Fetch metadata for a TikTok video URL.

        Returns a dict with keys: title, uploader, uploader_id, like_count,
        comment_count, view_count, upload_date, duration, tags, url.
        """
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-playlist", url],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env=utf8_subprocess_env(),
        )
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp 错误：{result.stderr.strip()}")
        data: Any = json.loads(result.stdout)
        return {
            "title": data.get("title", ""),
            "uploader": data.get("uploader", ""),
            "uploader_id": data.get("uploader_id", ""),
            "like_count": data.get("like_count"),
            "comment_count": data.get("comment_count"),
            "view_count": data.get("view_count"),
            "upload_date": data.get("upload_date", ""),
            "duration": data.get("duration"),
            "tags": data.get("tags", []),
            "url": data.get("webpage_url", url),
        }

    def get_user_videos(self, username: str, limit: int = 10) -> List[dict]:
        """Fetch recent videos from a TikTok creator profile.

        Args:
            username: TikTok username without @ prefix
            limit:    Maximum number of videos to return

        Returns a list of dicts with keys: title, url, view_count, like_count,
        upload_date.
        """
        profile_url = f"https://www.tiktok.com/@{username}"
        result = subprocess.run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--dump-json",
                "--playlist-end", str(limit),
                profile_url,
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=utf8_subprocess_env(),
        )
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp 错误：{result.stderr.strip()}")
        videos = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            try:
                item: Any = json.loads(line)
                videos.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "view_count": item.get("view_count"),
                    "like_count": item.get("like_count"),
                    "upload_date": item.get("upload_date", ""),
                })
            except json.JSONDecodeError:
                continue
        return videos

    def search(self, query: str, limit: int = 10) -> List[dict]:
        """TikTok 不提供公开搜索 API。

        建议改用 Exa channel 搜索 site:tiktok.com，或直接访问 TikTok 站内搜索。
        """
        return [
            {
                "error": (
                    "TikTok 未提供公开搜索 API。"
                    f"建议改用 Exa channel：site:tiktok.com {query}"
                )
            }
        ]
