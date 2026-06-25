# -*- coding: utf-8 -*-
"""Diffbot Knowledge Graph (DQL) — check if `db dql` + token are ready.

Structured querying of the Diffbot Knowledge Graph via DQL (Diffbot Query
Language), alongside the web-search channel. The invocation path is the
`db dql` command group shipped by diffbot-python — after setup the agent
navigates the ontology (`db dql ontology ...`) to discover types/fields, crafts
a DQL string, probes variants (`db dql probe`), then exports (`db dql export`).
agent-reach only installs / configures / health-checks it; see
references/diffbot-kg.md for the query-crafting workflow.

Shares the Diffbot API token with the web-search channel (same `db` CLI), so
token resolution is reused from diffbot_search.
"""

from pathlib import Path

from agent_reach.probe import probe_command

from .base import Channel
from .diffbot_search import has_token

#: Where Diffbot hands out free-tier API tokens.
_DIFFBOT_SIGNUP = "https://app.diffbot.com/get-started/"
#: `db dql init` caches the ontology here; `db dql ontology` reads it.
_ONTOLOGY_PATH = Path.home() / ".diffbot" / "ontology.json"


class DiffbotKGChannel(Channel):
    name = "diffbot_kg"
    description = "Diffbot 知识图谱（DQL）"
    backends = ["Diffbot CLI (db dql)"]
    tier = 1  # 需免费 Token

    def can_handle(self, url: str) -> bool:
        return False  # Structured-query channel, not URL-based

    def check(self, config=None):
        self.active_backend = None
        probe = probe_command("db", ["--version"], timeout=10, package="diffbot-python")
        if probe.status == "missing":
            return "off", (
                "需要 Diffbot CLI（diffbot-python）。安装：\n"
                "  pipx install diffbot-python   （或 uv tool install diffbot-python）\n"
                "再配置 API Token（有免费额度）：\n"
                f"  agent-reach configure diffbot-token <token>   获取：{_DIFFBOT_SIGNUP}"
            )
        if probe.status == "broken":
            return "error", probe.hint or "db 无法执行，重装：pipx reinstall diffbot-python"
        if not probe.ok:  # timeout / error
            return "error", f"db 执行异常：{probe.hint or probe.output or probe.status}"
        if not has_token(config):
            return "warn", (
                "Diffbot CLI 已装，但缺少 API Token。配置后即可查询知识图谱：\n"
                f"  agent-reach configure diffbot-token <token>   获取：{_DIFFBOT_SIGNUP}\n"
                "  （或 export DIFFBOT_API_TOKEN=...）"
            )
        # Token present → DQL queries (probe/export) work; they hit the API
        # directly. The ontology cache is only needed for `db dql ontology`
        # field navigation, so nudge `db dql init` when it's absent.
        self.active_backend = self.backends[0]
        if not _ONTOLOGY_PATH.exists():
            return "ok", (
                "Diffbot 知识图谱可用（db dql）。首次使用先运行 `db dql init` 缓存本体"
                "（ontology），之后用 `db dql ontology` 导航字段构造 DQL。"
            )
        return "ok", (
            "Diffbot 知识图谱可用（db dql ontology 导航字段 → db dql probe 验证 → "
            "db dql export 取数）"
        )
