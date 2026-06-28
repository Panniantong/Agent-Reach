# -*- coding: utf-8 -*-
"""TikTok — video metadata via yt-dlp, search via Playwright or OpenCLI.

TikTok aggressively blocks server IPs from direct scraping.  Individual
video metadata works through yt-dlp (which proxies via its own infra),
but search requires a browser session.

Backend routing:
  1. yt-dlp      — individual video info (titles, stats, subtitles)
  2. Playwright   — headless browser search (no visible window needed)
  3. OpenCLI      — search via desktop Chrome login state (fallback)

Playwright is the preferred search backend because it works in headless
mode without requiring a visible browser window or Chrome extension.
OpenCLI is kept as a fallback for users who already have it configured.
"""

import json
import re
import subprocess
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from agent_reach.probe import probe_command

from .base import Channel


class TikTokChannel(Channel):
    name = "tiktok"
    description = "TikTok 视频"
    backends = ["yt-dlp", "Playwright", "OpenCLI"]
    tier = 1  # search needs browser; individual URLs work without

    def can_handle(self, url: str) -> bool:
        d = urlparse(url).netloc.lower()
        return "tiktok.com" in d

    def check(self, config=None):
        """Probe backends in order; first fully-usable backend wins.

        Two-phase selection (same as Twitter/XiaoHongShu):
        Collect all candidate statuses → first 'ok' wins → first 'warn'
        → first 'error'.  Prevents a 'warn' (installed but not configured)
        from hiding a fully-working backend further down the list.
        """
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "yt-dlp":
                result = self._check_ytdlp()
            elif backend == "Playwright":
                result = self._check_playwright()
            elif backend == "OpenCLI":
                result = self._check_opencli()
            else:
                continue

            if result is None:
                continue  # not installed — skip
            findings.append((backend, *result))

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend
                    return status, message

        if findings:  # only broken/timeout candidates remain
            return "error", "\n".join(m for _, _, m in findings)

        return "warn", (
            "TikTok 视频信息可通过 yt-dlp 获取。安装：\n"
            "  pip install yt-dlp\n"
            "搜索功能需要 Playwright（推荐，无头浏览器）：\n"
            "  pip install playwright && python -m playwright install chromium\n"
            "或 OpenCLI（桌面 Chrome）：\n"
            "  npm install -g opencli"
        )

    def _check_ytdlp(self):
        """Probe yt-dlp for TikTok video metadata.

        yt-dlp supports TikTok individual video URLs for metadata
        extraction. Search is NOT supported via yt-dlp.
        Returns None if not installed.
        """
        probe = probe_command(
            "yt-dlp", ["--version"], timeout=10, retries=1, package="yt-dlp"
        )
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", "yt-dlp 命令存在但无法执行。\n" + probe.hint
        if probe.status == "timeout":
            return "error", "yt-dlp 健康检查超时。\n" + probe.hint

        return "ok", (
            "yt-dlp 可获取 TikTok 视频信息（标题、描述、统计数据、字幕）。\n"
            "  用法：yt-dlp --dump-json <tiktok-url>\n"
            "  注意：搜索功能需要 Playwright 或 OpenCLI"
        )

    def _check_playwright(self):
        """Probe Playwright for headless TikTok search.

        Playwright runs a headless Chromium browser — no visible window
        needed.  Supports search, video detail extraction, and auto-retry
        on page load failures.
        Returns None if not installed.
        """
        # Check if playwright Python package is installed
        probe = probe_command(
            "python",
            ["-c", "import playwright; print('ok')"],
            timeout=10,
            retries=0,
        )
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return None  # python itself broken — skip
        if "ok" not in (probe.output or ""):
            return None  # playwright not installed

        # Check if Chromium browser is available
        browser_probe = probe_command(
            "python",
            [
                "-c",
                "from playwright.sync_api import sync_playwright; "
                "p = sync_playwright().start(); "
                "b = p.chromium.launch(headless=True); "
                "b.close(); p.stop(); print('ok')",
            ],
            timeout=30,
            retries=0,
        )
        if "ok" in (browser_probe.output or ""):
            return "ok", (
                "Playwright 可用（无头浏览器，无需可见窗口）。\n"
                "  支持：搜索、视频详情、自动重试、错误恢复\n"
                "  无需额外配置，直接使用"
            )

        # Playwright installed but Chromium not downloaded
        return "warn", (
            "Playwright 已安装但 Chromium 浏览器未下载。运行：\n"
            "  python -m playwright install chromium"
        )

    def _check_opencli(self):
        """Probe OpenCLI for TikTok search via browser login state."""
        from agent_reach.backends import opencli_status

        st = opencli_status()
        if not st.installed:
            return None
        if st.broken:
            return "error", st.hint
        if st.ready:
            return "ok", (
                "OpenCLI 可用（复用浏览器登录态）。\n"
                "  搜索：opencli tiktok search \"关键词\"\n"
                "  视频详情：opencli tiktok video <url>"
            )
        return "warn", st.hint

    # ------------------------------------------------------------------ #
    # Search & Read — called by agents via skill
    # ------------------------------------------------------------------ #

    def search(self, query: str, max_results: int = 5) -> List[dict]:
        """Search TikTok videos by keyword using Playwright headless browser.

        Returns list of video dicts with: title, url, author, likes, date.
        Falls back to empty list with hint if search fails.
        """
        max_results = max(1, min(10, max_results))

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return [{"error": "Playwright 未安装。运行：pip install playwright"}]

        results = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()

                # Navigate with retry logic
                search_url = f"https://www.tiktok.com/search?q={query.replace(' ', '+')}"
                for attempt in range(3):
                    try:
                        page.goto(search_url, wait_until="networkidle", timeout=30000)
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        page.reload(wait_until="networkidle", timeout=20000)

                # Wait for video cards to load
                try:
                    page.wait_for_selector('[data-e2e="search-card-desc"]', timeout=15000)
                except Exception:
                    # Try alternative selectors
                    try:
                        page.wait_for_selector('a[href*="/video/"]', timeout=10000)
                    except Exception:
                        browser.close()
                        return [{"error": "搜索结果加载失败，请稍后重试"}]

                # Extract video links and metadata
                video_links = page.query_selector_all('a[href*="/video/"]')
                seen_urls = set()

                for link in video_links:
                    if len(results) >= max_results:
                        break

                    href = link.get_attribute("href") or ""
                    if not href or href in seen_urls:
                        continue
                    seen_urls.add(href)

                    # Extract title from the link's text content or aria-label
                    title = ""
                    img = link.query_selector("img")
                    if img:
                        title = img.get_attribute("alt") or ""
                    if not title:
                        title = link.inner_text().strip()[:200]

                    # Extract author from URL pattern
                    author = ""
                    author_match = re.search(r"/@([\w.-]+)/", href)
                    if author_match:
                        author = author_match.group(1)

                    results.append({
                        "title": title,
                        "url": href if href.startswith("http") else f"https://www.tiktok.com{href}",
                        "author": author,
                    })

                browser.close()

        except Exception as e:
            return [{"error": f"搜索失败: {str(e)}", "hint": "请稍后重试或检查网络连接"}]

        if not results:
            return [{"error": "未找到结果", "hint": "尝试不同的搜索关键词"}]

        return results

    def read(self, url: str) -> dict:
        """Read a TikTok video's metadata using Playwright headless browser.

        Returns dict with: title, author, description, likes, comments, etc.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {"error": "Playwright 未安装。运行：pip install playwright"}

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()

                # Navigate with retry
                for attempt in range(3):
                    try:
                        page.goto(url, wait_until="networkidle", timeout=30000)
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        page.reload(wait_until="networkidle", timeout=20000)

                # Extract metadata from page
                result = {"url": url}

                # Title/description
                desc_el = page.query_selector('[data-e2e="browse-video-desc"]')
                if desc_el:
                    result["description"] = desc_el.inner_text().strip()

                # Author
                author_el = page.query_selector('[data-e2e="browse-username"]')
                if author_el:
                    result["author"] = author_el.inner_text().strip()

                # Stats
                for stat_name, selector in [
                    ("likes", '[data-e2e="browse-like-count"]'),
                    ("comments", '[data-e2e="browse-comment-count"]'),
                    ("shares", '[data-e2e="browse-share-count"]'),
                ]:
                    el = page.query_selector(selector)
                    if el:
                        result[stat_name] = el.inner_text().strip()

                # Music info
                music_el = page.query_selector('[data-e2e="browse-music"]')
                if music_el:
                    result["music"] = music_el.inner_text().strip()

                browser.close()
                return result

        except Exception as e:
            return {"error": f"读取失败: {str(e)}", "url": url}
