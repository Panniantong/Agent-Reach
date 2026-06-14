# -*- coding: utf-8 -*-
"""Twitter/X — check if twitter-cli or bird CLI is available."""

from .base import Channel
from agent_reach.probe import probe_command


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X 推文"
    backends = ["twitter-cli", "OpenCLI", "bird CLI (legacy)"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from ..utils.urlmatch import host_matches
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
                result = self._check_twitter_cli()
            elif backend == "OpenCLI":
                result = self._check_opencli()
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
                    self.active_backend = backend
                    return status, message

        if findings:  # 只剩 broken/timeout 候选
            return "error", "\n".join(m for _, _, m in findings)

        return "warn", (
            "Twitter CLI 未安装。安装方式：\n"
            "  pipx install twitter-cli\n"
            "或：\n"
            "  uv tool install twitter-cli"
        )

    def _check_twitter_cli(self):
        """探测 twitter-cli。返回 None 表示未安装，否则返回 (status, message)。

        `twitter status` 才是健康信号：已登录时输出 "ok: true"，
        未登录时以非零退出码输出 "not_authenticated"——工具本身是活的，
        所以 probe 的 error 状态也要看 output 内容再分类。
        """
        probe = probe_command(
            "twitter", ["status"], timeout=15, retries=1, package="twitter-cli"
        )
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", "twitter-cli 命令存在但无法执行。\n" + probe.hint
        if probe.status == "timeout":
            return "error", "twitter-cli 健康检查超时（已重试 1 次）。\n" + probe.hint

        output = probe.output
        if "ok: true" in output:
            return "ok", (
                "twitter-cli 完整可用（搜索、读推文、时间线、长文/Article、"
                "用户查询、Thread）"
            )
        if "not_authenticated" in output:
            return "warn", (
                "twitter-cli 已安装但未认证。设置方式：\n"
                "  export TWITTER_AUTH_TOKEN=\"xxx\"\n"
                "  export TWITTER_CT0=\"yyy\"\n"
                "或确保已在浏览器中登录 x.com"
            )
        return "warn", (
            "twitter-cli 已安装但认证检查失败。运行：\n"
            "  twitter -v status 查看详细信息"
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
            return "ok", (
                "OpenCLI 可用（复用浏览器登录态）。用法："
                "opencli twitter search/article/user-posts -f yaml"
            )
        return "warn", st.hint

    def _check_bird(self):
        """探测 bird/birdx（legacy 回退）。返回 None 表示均未安装，否则返回 (status, message)。"""
        last_failure = None
        for cmd in ("bird", "birdx"):
            probe = probe_command(
                cmd, ["check"], timeout=15, retries=1, package="@steipete/bird"
            )
            if probe.status == "missing":
                continue
            if probe.status == "broken":
                last_failure = (
                    "error",
                    f"{cmd} 命令存在但无法执行（bird 是 npm 包，可用 "
                    "npm install -g @steipete/bird 重装）。\n" + probe.hint,
                )
                continue  # bird 坏了再试 birdx
            if probe.status == "timeout":
                last_failure = (
                    "error",
                    f"{cmd} 健康检查超时（已重试 1 次）。\n" + probe.hint,
                )
                continue

            output = probe.output
            if probe.ok:
                return "ok", "bird CLI 可用（读取、搜索推文，含长文/X Article）"
            if "Missing credentials" in output or "missing" in output.lower():
                return "warn", (
                    "bird CLI 已安装但未配置认证。设置环境变量：\n"
                    "  export AUTH_TOKEN=\"xxx\"\n"
                    "  export CT0=\"yyy\""
                )
            return "warn", (
                "bird CLI 已安装但认证检查失败。"
            )
        return last_failure
