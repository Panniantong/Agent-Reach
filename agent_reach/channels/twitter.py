# -*- coding: utf-8 -*-
"""Twitter/X — check if twitter-cli or bird CLI is available."""

import json
import shutil
from pathlib import Path
from .base import Channel


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X 推文"
    backends = ["twitter-cli", "bird CLI (legacy)"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "x.com" in d or "twitter.com" in d

    def check(self, config=None):
        # Prefer twitter-cli, fallback to bird/birdx
        twitter = shutil.which("twitter")
        bird = shutil.which("bird") or shutil.which("birdx")

        if twitter or bird:
            creds = self._find_local_credentials(config)
            if creds:
                return "ok", (
                    f"检测到本地凭证（{creds}）。"
                    "doctor 跳过在线校验，保持非交互"
                )
            if twitter:
                return "warn", (
                    "twitter-cli 已安装，但当前未检测到本地凭证。配置方式：\n"
                    "  agent-reach configure twitter-cookies AUTH_TOKEN CT0\n"
                    "或：\n"
                    "  agent-reach configure twitter-cookies \"auth_token=xxx; ct0=yyy; ...\""
                )
            return "warn", (
                "bird CLI 已安装，但当前未检测到本地凭证。"
                "设置环境变量文件：~/.config/bird/credentials.env"
            )
        else:
            return "warn", (
                "Twitter CLI 未安装。安装方式：\n"
                "  pipx install twitter-cli\n"
                "或：\n"
                "  uv tool install twitter-cli"
            )

    def _find_local_credentials(self, config=None):
        try:
            if config:
                auth = (config.get("twitter_auth_token") or "").strip()
                ct0 = (config.get("twitter_ct0") or "").strip()
                if auth and ct0:
                    return "~/.agent-reach/config.yaml"
        except Exception:
            pass

        session_path = Path.home() / ".config" / "xfetch" / "session.json"
        try:
            if session_path.exists():
                data = json.loads(session_path.read_text(encoding="utf-8"))
                if data.get("authToken") and data.get("ct0"):
                    return str(session_path)
        except Exception:
            pass

        bird_env = Path.home() / ".config" / "bird" / "credentials.env"
        try:
            if bird_env.exists():
                text = bird_env.read_text(encoding="utf-8")
                if "AUTH_TOKEN=" in text and "CT0=" in text:
                    return str(bird_env)
        except Exception:
            pass

        return None
