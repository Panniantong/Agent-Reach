# -*- coding: utf-8 -*-
"""Instagram — via instaloader (free, open source).

Backend: instaloader (9.8K stars, Python CLI + library)
Swap to: any Instagram access tool
"""

import re
import shutil
import subprocess
from urllib.parse import urlparse
from .base import Channel, ReadResult, SearchResult
from typing import List


class InstagramChannel(Channel):
    name = "instagram"
    description = "Instagram 帖子和 Profile"
    backends = ["instaloader"]
    tier = 2  # Needs login for full access

    def can_handle(self, url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        return "instagram.com" in domain or "instagr.am" in domain

    def check(self, config=None):
        # Check both CLI and Python module
        has_cli = shutil.which("instaloader")
        has_module = False
        try:
            import instaloader
            has_module = True
        except ImportError:
            pass

        if not has_cli and not has_module:
            return "off", (
                "需要安装 instaloader：pip install instaloader\n"
                "  安装后可读取 Instagram 帖子和 Profile\n"
                "  登录解锁更多功能：instaloader --login YOUR_USERNAME"
            )
        return "ok", "可读取公开帖子和 Profile。登录后可访问更多内容"

    async def read(self, url: str, config=None) -> ReadResult:
        # Try instaloader (module or CLI)
        try:
            import instaloader
            return await self._read_instaloader(url, config)
        except ImportError:
            pass
        # Fallback: Jina Reader
        return await self._read_jina(url)

    async def _read_instaloader(self, url: str, config=None) -> ReadResult:
        """Read Instagram content using instaloader Python API."""
        import asyncio
        import concurrent.futures

        def _sync_read():
            import instaloader
            L = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
                max_connection_attempts=1,  # Don't retry on rate limit
            )

            # Try to load session if available
            if config and config.get("instagram_username"):
                try:
                    L.load_session_from_file(config.get("instagram_username"))
                except Exception:
                    pass

            path = urlparse(url).path.strip("/")

            if "/p/" in url or "/reel/" in url:
                return self._read_post_sync(L, url, path)
            else:
                return self._read_profile_sync(L, url, path)

        try:
            # Run with 15s timeout to avoid instaloader's 30-min retry
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = await asyncio.wait_for(
                    loop.run_in_executor(pool, _sync_read),
                    timeout=15,
                )
                return result
        except (asyncio.TimeoutError, Exception):
            # Any error or timeout → Jina fallback
            return await self._read_jina(url)

    def _read_post_sync(self, L, url: str, path: str) -> ReadResult:
        """Read a single Instagram post (sync, runs in executor)."""
        import instaloader

        # Extract shortcode from URL
        match = re.search(r"/(?:p|reel)/([A-Za-z0-9_-]+)", url)
        if not match:
            raise ValueError("Cannot extract shortcode from URL")

        shortcode = match.group(1)
        try:
            post = instaloader.Post.from_shortcode(L.context, shortcode)

            lines = []
            if post.caption:
                lines.append(post.caption)
            lines.append("")
            lines.append(f"👤 @{post.owner_username}")
            lines.append(f"❤️ {post.likes} likes")
            if post.comments:
                lines.append(f"💬 {post.comments} comments")
            lines.append(f"📅 {post.date_utc.strftime('%Y-%m-%d %H:%M')}")
            if post.location:
                lines.append(f"📍 {post.location}")
            if post.hashtags:
                lines.append(f"#️⃣ {' '.join('#' + h for h in post.hashtags)}")

            return ReadResult(
                title=f"@{post.owner_username}: {(post.caption or '')[:80]}",
                content="\n".join(lines),
                url=url,
                author=f"@{post.owner_username}",
                date=post.date_utc.strftime("%Y-%m-%d"),
                platform="instagram",
                extra={"likes": post.likes, "comments": post.comments},
            )
        except Exception:
            raise  # Let executor timeout handle fallback

    def _read_profile_sync(self, L, url: str, path: str) -> ReadResult:
        """Read an Instagram profile (sync, runs in executor)."""
        import instaloader

        # Extract username from path
        username = path.split("/")[0] if path else ""
        if not username or username in ("p", "reel", "stories", "explore"):
            raise ValueError("Cannot extract username from URL")

        try:
            profile = instaloader.Profile.from_username(L.context, username)

            lines = []
            lines.append(f"👤 {profile.full_name} (@{profile.username})")
            if profile.biography:
                lines.append(f"📝 {profile.biography}")
            if profile.external_url:
                lines.append(f"🔗 {profile.external_url}")
            lines.append("")
            lines.append(f"📊 {profile.mediacount} posts · "
                         f"{profile.followers} followers · "
                         f"{profile.followees} following")
            if profile.is_verified:
                lines.append("✅ Verified")
            if profile.is_business_account and profile.business_category_name:
                lines.append(f"🏢 {profile.business_category_name}")

            # Get recent posts (up to 5)
            lines.append("")
            lines.append("📸 Recent posts:")
            count = 0
            for post in profile.get_posts():
                if count >= 5:
                    break
                caption = (post.caption or "")[:100].replace("\n", " ")
                lines.append(f"  • ❤️{post.likes} | {post.date_utc.strftime('%m-%d')} | {caption}")
                count += 1

            return ReadResult(
                title=f"{profile.full_name} (@{profile.username}) - Instagram",
                content="\n".join(lines),
                url=url,
                author=f"@{profile.username}",
                platform="instagram",
                extra={
                    "followers": profile.followers,
                    "posts": profile.mediacount,
                },
            )
        except Exception:
            raise  # Let executor timeout handle fallback

    async def _read_jina(self, url: str) -> ReadResult:
        """Fallback: use Jina Reader."""
        import requests
        try:
            resp = requests.get(
                f"https://r.jina.ai/{url}",
                headers={"Accept": "text/markdown"},
                timeout=15,
            )
            resp.raise_for_status()
            text = resp.text
            return ReadResult(
                title=text[:100] if text else url,
                content=text,
                url=url,
                platform="instagram",
            )
        except Exception:
            return ReadResult(
                title="Instagram",
                content=(
                    f"⚠️ 无法读取此 Instagram 内容: {url}\n\n"
                    "提示：\n"
                    "- 确保 URL 正确\n"
                    "- 安装 instaloader: pip install instaloader\n"
                    "- 登录以访问更多内容: instaloader --login YOUR_USERNAME"
                ),
                url=url,
                platform="instagram",
            )

    async def search(self, query: str, config=None, **kwargs) -> List[SearchResult]:
        """Search Instagram via Exa."""
        limit = kwargs.get("limit", 10)
        from agent_reach.channels.exa_search import ExaSearchChannel
        exa = ExaSearchChannel()
        return await exa.search(f"site:instagram.com {query}", config=config, limit=limit)
