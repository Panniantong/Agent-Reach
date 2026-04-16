# -*- coding: utf-8 -*-
"""Reddit — search and read via rdt-cli (public-clis/rdt-cli).

NOTE: Reddit requires authentication since 2024. All API requests
(including public subreddit reads) return HTTP 403 without a valid
session cookie. Run `rdt login` after installation to authenticate.
"""

import json
import shutil
from pathlib import Path

from .base import Channel

_CREDENTIAL_FILE = "~/.config/rdt-cli/credential.json"


class RedditChannel(Channel):
    name = "reddit"
    description = "Reddit 帖子和评论"
    backends = ["rdt-cli"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "reddit.com" in d or "redd.it" in d

    def check(self, config=None):
        rdt = shutil.which("rdt")
        if not rdt:
            return "off", (
                "需要安装 rdt-cli（推荐使用最新版 v0.4.2+）：\n"
                "  pip install 'rdt-cli>=0.4.2'\n"
                "或：\n"
                "  uv tool install rdt-cli\n"
                "最新源码：https://github.com/public-clis/rdt-cli\n"
                "安装后运行 `rdt login` 登录（需先在浏览器登录 reddit.com）"
            )

        # Keep doctor/status non-interactive and fast.
        cred_path = Path.home() / ".config" / "rdt-cli" / "credential.json"
        try:
            if cred_path.exists():
                data = json.loads(cred_path.read_text(encoding="utf-8"))
                cookies = data.get("cookies") or {}
                session = cookies.get("reddit_session") or data.get("reddit_session")
                username = data.get("username") or ""
                if session:
                    suffix = f"（已保存账号：{username}）" if username else ""
                    return "ok", (
                        f"检测到本地 Reddit 凭证{suffix}。"
                        "doctor 跳过在线校验，保持非交互"
                    )
        except (json.JSONDecodeError, OSError):
            pass

        return "warn", (
            "rdt-cli 已安装，但当前未检测到本地凭证。Reddit 自 2024 年起要求认证，"
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
