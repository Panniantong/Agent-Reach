# -*- coding: utf-8 -*-
"""GitHub — check if gh CLI is available."""

from agent_reach.probe import probe_command

from .base import Channel


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub 仓库和代码"
    backends = ["gh CLI"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from ..utils.urlmatch import host_matches
        return host_matches(url, "github.com")

    def check(self, config=None):
        # 真跑 gh auth status 探活。注意：未登录时 rc!=0 是正常业务态（warn），不是 error。
        probe = probe_command("gh", ["auth", "status"], timeout=10, package="gh")
        if probe.status == "missing":
            self.active_backend = None
            return "warn", "gh CLI 未安装。安装：https://cli.github.com"
        if probe.status == "broken":
            # gh 是二进制安装（brew/官方包），不是 pip 包——处方不用 pipx/uv 文案
            self.active_backend = None
            return "error", (
                "gh 命令存在但无法执行——安装已损坏。重装即可修复：\n"
                "  brew reinstall gh\n"
                "或从 https://cli.github.com 重新安装 gh CLI"
            )
        if probe.status == "timeout":
            # gh 本体能启动（工具是活的），只是状态检查超时
            self.active_backend = "gh CLI"
            return "warn", "gh CLI 状态检查超时，运行 gh auth status 查看详情"
        if probe.ok:
            self.active_backend = "gh CLI"
            return "ok", "完整可用（读取、搜索、Fork、Issue、PR 等）"
        # rc != 0：gh 活着但未认证（gh auth status 的正常业务态）
        self.active_backend = "gh CLI"
        return "warn", "gh CLI 已安装但未认证。运行 gh auth login 可解锁完整功能"
