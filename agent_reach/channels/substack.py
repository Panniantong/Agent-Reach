# -*- coding: utf-8 -*-
"""Substack — multi-backend discovery: OpenCLI / Exa via mcporter.

Scope (deliberate): discovery only — `search` (find posts/newsletters) and
`publication` (latest posts from a named newsletter). Both are PUBLIC on the
OpenCLI side (verified live 2026-07: `opencli substack search` is tagged
[public], no cookie). The logged-in `feed` command is intentionally out of
scope so this channel never carries login state.

Honest tiering: tier 0 because a genuine zero-config discovery path exists —
Exa semantic search scoped to substack.com needs no browser, no key. OpenCLI
is preferred when its bridge is live because results come from Substack's own
search (fresher, exact); Exa is the approximate fallback. `publication` reads
degrade on the Exa path (semantic approximation, not the real archive feed).

Unlike login-bound OpenCLI channels (Reddit/Instagram), a live bridge here is
sufficient evidence of usability: there is no login state left to verify for
public commands, so ready → "ok" rather than the usual "warn".
"""

import shutil

from .base import Channel

_OPENCLI_USAGE = (
    "opencli substack search \"query\" -f yaml   # 搜索文章和 Newsletter\n"
    "  opencli substack publication <name> -f yaml # 指定 Newsletter 最新文章"
)

_EXA_USAGE = (
    "mcporter call 'exa.web_search_exa(query=\"... site:substack.com\")'"
)


class SubstackChannel(Channel):
    name = "substack"
    description = "Substack 文章搜索与 Newsletter"
    backends = ["OpenCLI", "Exa via mcporter"]
    tier = 0  # zero-config path exists: Exa fallback — see module docstring

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        # host_matches covers publication subdomains (lenny.substack.com).
        # Custom domains (e.g. stratechery.com) can't be enumerated — those
        # fall through to the generic web channel by design.
        return host_matches(url, "substack.com")

    def check(self, config=None):
        """Probe candidates in order; first usable backend wins."""
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "OpenCLI":
                result = self._check_opencli()
            else:
                result = self._check_exa()
            if result is None:
                continue
            findings.append((backend, *result))

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend if status == "ok" else None
                    return status, message

        if findings:
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "未安装任何 Substack 后端。两条路径任选：\n"
            "  桌面（推荐，精确搜索）：agent-reach install --channels substack\n"
            "       （OpenCLI 公开命令，无需登录 Substack）\n"
            "  零配置（近似搜索）：npm install -g mcporter\n"
            "       mcporter config add exa https://mcp.exa.ai/mcp --scope home"
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
            # Public commands + live bridge: nothing left unverified that a
            # login could invalidate, so this is honestly "ok" (contrast
            # Reddit, where login state keeps ready at "warn").
            return "ok", f"Substack 搜索可用（OpenCLI 公开命令）：\n  {_OPENCLI_USAGE}"
        return "warn", st.hint

    def _check_exa(self):
        """Exa fallback candidate. None = mcporter not installed."""
        from .mcporter import McporterConfigError, inspect_mcporter_config

        if not shutil.which("mcporter"):
            return None
        try:
            inspection = inspect_mcporter_config()
        except McporterConfigError as exc:
            return "error", f"mcporter 配置检查失败：{exc}"
        if "exa" in inspection.server_names:
            # Degraded but genuinely serving discovery: semantic search over
            # the public web scoped to substack.com. publication 读取降级。
            return "ok", (
                "Substack 搜索通过 Exa 降级可用（近似语义搜索；"
                "publication 精确读取需要 OpenCLI 桥接）：\n"
                f"  {_EXA_USAGE}\n"
                "  恢复完整能力：打开 Chrome（OpenCLI 扩展所在 profile）"
            )
        return "off", (
            "mcporter 已装但 Exa 未配置。运行：\n"
            "  mcporter config add exa https://mcp.exa.ai/mcp --scope home"
        )
