# -*- coding: utf-8 -*-
"""Reddit — search and read via rdt-cli (public-clis/rdt-cli).

NOTE: Reddit requires authentication since 2024. All API requests
(including public subreddit reads) return HTTP 403 without a valid
session cookie. Run `rdt login` after installation to authenticate.
"""

import json
import shutil
import subprocess

from .base import Channel

_CREDENTIAL_FILE = "~/.config/rdt-cli/credential.json"


class RedditChannel(Channel):
    name = "reddit"
    description = "Reddit 帖子和评论"
    description_en = "Reddit posts and comments"
    backends = ["rdt-cli"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "reddit.com" in d or "redd.it" in d

    def check(self, config=None):
        from agent_reach.lang import use_english

        rdt = shutil.which("rdt")
        if not rdt:
            if use_english():
                return "off", (
                    "rdt-cli needs to be installed (v0.4.2+ recommended):\n"
                    "  pip install 'rdt-cli>=0.4.2'\n"
                    "or:\n"
                    "  uv tool install rdt-cli\n"
                    "Source: https://github.com/public-clis/rdt-cli\n"
                    "After install, run `rdt login` (login to reddit.com in your browser first)"
                )
            return "off", (
                "需要安装 rdt-cli（推荐使用最新版 v0.4.2+）：\n"
                "  pip install 'rdt-cli>=0.4.2'\n"
                "或：\n"
                "  uv tool install rdt-cli\n"
                "最新源码：https://github.com/public-clis/rdt-cli\n"
                "安装后运行 `rdt login` 登录（需先在浏览器登录 reddit.com）"
            )

        try:
            r = subprocess.run(
                [rdt, "status", "--json"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            data = json.loads(r.stdout or "{}")
            authenticated = data.get("data", {}).get("authenticated", False)
            username = data.get("data", {}).get("username") or ""

            if authenticated:
                if use_english():
                    suffix = f" (logged in: {username})" if username else ""
                    return "ok", (f"rdt-cli available{suffix} (search posts, read full text, view comments)")
                suffix = f"（已登录：{username}）" if username else ""
                return "ok", (f"rdt-cli 可用{suffix}（搜索帖子、阅读全文、查看评论）")

            if use_english():
                return "warn", (
                    "rdt-cli installed but not logged in. Reddit requires authentication since 2024, "
                    "all unauthenticated requests return 403.\n\n"
                    "Method 1 (auto): Run `rdt login`\n"
                    "  Login to reddit.com in your browser first, then run this command to auto-extract cookies.\n\n"
                    "Method 2 (manual, for Chrome/Edge 127+ when auto-extract fails):\n"
                    "  1. Install Cookie-Editor extension from Chrome Web Store:\n"
                    "     https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm\n"
                    "  2. Open reddit.com in your browser (make sure you're logged in)\n"
                    "  3. Click Cookie-Editor icon, find `reddit_session`, copy its Value\n"
                    f"  4. Write the following to {_CREDENTIAL_FILE}:\n"
                    '     {"cookies": {"reddit_session": "<paste Value>"}, '
                    '"source": "manual", "username": "<your username>", '
                    '"modhash": null, "saved_at": 0, "last_verified_at": null}\n\n'
                    "Verify: `rdt status --json` confirms authenticated: true"
                )
            return "warn", (
                "rdt-cli 已安装但未登录。Reddit 自 2024 年起要求认证，"
                "未登录时所有请求均返回 403。\n\n"
                "方法一（自动）：运行 `rdt login`\n"
                "  先在浏览器登录 reddit.com，再运行此命令自动提取 Cookie。\n\n"
                "方法二（手动，适用于 Chrome/Edge 127+ 无法自动提取时）：\n"
                "  1. Chrome 应用商店安装 Cookie-Editor 扩展：\n"
                "     https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm\n"
                "  2. 在浏览器打开 reddit.com（确保已登录）\n"
                "  3. 点击 Cookie-Editor 图标，找到 `reddit_session`，复制其 Value\n"
                f"  4. 将以下内容写入 {_CREDENTIAL_FILE}：\n"
                '     {"cookies": {"reddit_session": "<粘贴 Value>"}, '
                '"source": "manual", "username": "<你的用户名>", '
                '"modhash": null, "saved_at": 0, "last_verified_at": null}\n\n'
                "验证：`rdt status --json` 确认 authenticated: true"
            )

        except (json.JSONDecodeError, FileNotFoundError, subprocess.TimeoutExpired):
            if use_english():
                return "warn", "rdt-cli installed but status check failed. Run `rdt status` for details"
            return "warn", "rdt-cli 已安装但状态检查失败，运行 `rdt status` 查看详情"
