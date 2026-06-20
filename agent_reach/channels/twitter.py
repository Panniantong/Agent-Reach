# -*- coding: utf-8 -*-
"""Twitter/X — check if twitter-cli or bird CLI is available."""

from .base import Channel
from agent_reach.probe import probe_command


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X tweets"
    backends = ["twitter-cli", "OpenCLI", "bird CLI (legacy)"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "x.com" in d or "twitter.com" in d

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
            "Twitter CLI not installed. Install:\n"
            "  pipx install twitter-cli\n"
            "or:\n"
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
            return "error", "twitter-cli command exists but can't execute.\n" + probe.hint
        if probe.status == "timeout":
            return "error", "twitter-cli health check timed out (retried 1 time).\n" + probe.hint

        output = probe.output
        if "ok: true" in output:
            return "ok", (
                "twitter-cli fully available (search, read tweets, timeline, long posts/Articles, "
                "user queries, Threads)"
            )
        if "not_authenticated" in output:
            return "warn", (
                "twitter-cli installed but not authenticated. Setup:\n"
                "  export TWITTER_AUTH_TOKEN=\"xxx\"\n"
                "  export TWITTER_CT0=\"yyy\"\n"
                "or ensure you're logged into x.com in browser"
            )
        return "warn", (
            "twitter-cli installed but authentication check failed. Run:\n"
            "  twitter -v status for details"
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
                "OpenCLI available (reuses browser login session). Usage: "
                "opencli twitter search/article/user-posts -f yaml"
            )
        return "warn", st.hint

    def _check_bird(self):
        """Probe bird/birdx (legacy fallback). Returns None if none installed, else (status, message)."""
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
                    f"{cmd} command exists but can't execute (bird is npm package, "
                    "reinstall with npm install -g @steipete/bird).\n" + probe.hint,
                )
                continue  # bird broken, try birdx
            if probe.status == "timeout":
                last_failure = (
                    "error",
                    f"{cmd} health check timed out (retried 1 time).\n" + probe.hint,
                )
                continue

            output = probe.output
            if probe.ok:
                return "ok", "bird CLI available (read, search tweets, including long posts/X Articles)"
            if "Missing credentials" in output or "missing" in output.lower():
                return "warn", (
                    "bird CLI installed but not authenticated. Set environment variables:\n"
                    "  export AUTH_TOKEN=\"xxx\"\n"
                    "  export CT0=\"yyy\""
                )
            return "warn", (
                "bird CLI installed but authentication check failed."
            )
        return last_failure
