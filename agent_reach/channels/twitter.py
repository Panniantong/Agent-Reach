# -*- coding: utf-8 -*-
"""Twitter/X: inspect configured read backends without triggering cookie access."""

import os
import shutil

from agent_reach.utils.url import host_matches

from .base import Channel


def twitter_cli_child_env(config=None) -> dict[str, str]:
    """Return saved credentials missing from the current process environment.

    The returned mapping is meant for a single child process.  Existing shell
    variables remain authoritative and ``os.environ`` is never mutated.
    """
    if config is None:
        return {}

    child_env = {}
    for env_name, config_key in (
        ("TWITTER_AUTH_TOKEN", "twitter_auth_token"),
        ("TWITTER_CT0", "twitter_ct0"),
    ):
        if env_name in os.environ:
            continue
        value = config.get(config_key)
        if value:
            child_env[env_name] = str(value)
    return child_env


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X 推文"
    backends = ["twitter-cli", "OpenCLI", "Xquik API", "bird CLI (legacy)"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "x.com", "twitter.com")

    def check(self, config=None):
        """Probe candidates in order; first fully-usable backend wins.

        与其他多后端渠道同一套两段式：先收集全部候选状态，第一个 ok 获胜；
        没有 ok 才轮到第一个 warn——否则「装了但未登录」的 twitter-cli
        会把排在后面、完整可用的 OpenCLI 挡在门外。
        """
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "twitter-cli":
                result = self._check_twitter_cli(config)
            elif backend == "OpenCLI":
                result = self._check_opencli()
            elif backend == "Xquik API":
                result = self._check_xquik_api(config)
            elif backend == "bird CLI (legacy)":
                result = self._check_bird()
            else:
                continue

            if result is None:
                continue  # 未安装——不参与候选
            findings.append((backend, *result))

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend if status == "ok" else None
                    return status, message

        if findings:  # 只剩 broken/timeout 候选
            return "error", "\n".join(m for _, _, m in findings)

        return "warn", (
            "Twitter CLI 未安装。安装方式：\n"
            "  pipx install twitter-cli\n"
            "或：\n"
            "  uv tool install twitter-cli"
        )

    def _check_xquik_api(self, config=None):
        """Report explicit Xquik configuration without sending the API key."""
        key = config.get("xquik_api_key") if config else None
        key = key or os.environ.get("XQUIK_API_KEY")
        if not key:
            return None
        return "warn", (
            "Xquik API 密钥已配置；Doctor 不会发送或验证密钥。"
            "请按 setup-twitter.md 中的只读示例手动验证。"
        )

    def _check_twitter_cli(self, config=None):
        """Inspect explicit credentials without starting twitter-cli.

        Upstream ``twitter status`` automatically reads browser cookies when
        credentials are missing *or invalid*. Doctor cannot disable that
        fallback, so executing it would violate the Cookie-Editor-only policy.
        """
        if not shutil.which("twitter"):
            return None

        child_env = twitter_cli_child_env(config)
        auth_token = os.environ.get("TWITTER_AUTH_TOKEN") or child_env.get(
            "TWITTER_AUTH_TOKEN"
        )
        ct0 = os.environ.get("TWITTER_CT0") or child_env.get("TWITTER_CT0")
        if auth_token and ct0:
            return "warn", (
                "twitter-cli 已安装，且 Cookie-Editor 凭据已配置；"
                "Doctor 不会执行 `twitter status`，因为上游在验证失败时会"
                "自动读取浏览器 Cookie。请在你明确同意时手动验证。"
            )
        return "warn", (
            "twitter-cli 已安装但没有完整的显式凭据。请用 Cookie-Editor "
            "从 x.com 导出后运行：\n"
            "  agent-reach configure twitter-cookies "
            "'<Cookie-Editor Header String>'\n"
            "Doctor 不会自动读取浏览器 Cookie。"
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
                "OpenCLI 桥接已连接，但 Twitter/X 登录态和实际命令未实时验证；"
                "Doctor 不执行平台命令，因此当前不标记为可用。"
            )
        return "warn", st.hint

    def _check_bird(self):
        """Inspect legacy bird credentials without launching browser fallback."""
        for cmd in ("bird", "birdx"):
            if not shutil.which(cmd):
                continue
            if os.environ.get("AUTH_TOKEN") and os.environ.get("CT0"):
                return (
                    "warn",
                    f"{cmd} 已安装且显式环境凭据存在；Doctor 为避免上游"
                    "浏览器 Cookie 回退，不执行 `check`，未实时验证。",
                )
            return "warn", (
                f"{cmd} 已安装但未检测到显式 AUTH_TOKEN/CT0；"
                "仅使用 Cookie-Editor 手动导出的凭据。"
            )
        return None
