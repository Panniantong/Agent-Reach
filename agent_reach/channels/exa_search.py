# -*- coding: utf-8 -*-
"""Exa Search — route an optional direct REST backend before Exa MCP."""

import json
import os
import shutil

from agent_reach.probe import probe_command

from .base import Channel
from .mcporter import McporterConfigError, inspect_mcporter_config

_REST_BACKEND = "Exa REST API"
_MCP_BACKEND = "Exa via mcporter"


class ExaSearchChannel(Channel):
    name = "exa_search"
    description = "全网语义搜索"
    backends = [_REST_BACKEND, _MCP_BACKEND]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        self.active_backend = None
        api_key = config.get("exa_api_key") if config is not None else None
        if not api_key:
            api_key = os.environ.get("EXA_API_KEY")

        direct_problem = None
        for backend in self.ordered_backends(config):
            if backend == _REST_BACKEND:
                if not api_key:
                    continue
                probe = probe_command(
                    "agent-reach-exa",
                    ["status", "--json"],
                    timeout=10,
                    package="agent-reach",
                    env={"EXA_API_KEY": str(api_key)},
                )
                if probe.ok:
                    try:
                        payload = json.loads(probe.output)
                    except json.JSONDecodeError:
                        direct_problem = "agent-reach-exa status 返回了无效 JSON"
                    else:
                        if not isinstance(payload, dict):
                            direct_problem = "agent-reach-exa status 返回了无效状态"
                        elif payload.get("configured") is True:
                            return "warn", (
                                "Exa REST API Key 已配置；Doctor 不发起计费搜索，"
                                "所以未验证网络、额度或限流。首次真实调用再验证。"
                            )
                        direct_problem = "agent-reach-exa 未确认 API Key 配置"
                elif probe.status == "missing":
                    direct_problem = "agent-reach-exa 命令缺失，请重装 agent-reach"
                elif probe.status == "broken":
                    direct_problem = probe.hint or "agent-reach-exa 安装损坏"
                else:
                    direct_problem = probe.hint or probe.output or "agent-reach-exa 检查失败"
                continue

            if not shutil.which("mcporter"):
                continue
            try:
                inspection = inspect_mcporter_config()
            except McporterConfigError as exc:
                if direct_problem:
                    return "error", f"{direct_problem}；mcporter 配置检查也失败：{exc}"
                return "error", f"mcporter 配置检查失败：{exc}"
            if "exa" in inspection.server_names:
                prefix = f"{direct_problem}；已回退 MCP。" if direct_problem else ""
                return "warn", (
                    f"{prefix}Exa 已写入 mcporter 配置，但 Doctor 未启动远端服务做"
                    "连通验证，不能仅凭配置宣称可用。"
                )
            if inspection.imports_unchecked:
                return "warn", (
                    "mcporter 本地配置未发现 Exa；配置还启用了 editor imports，"
                    "Doctor 为避免扩大凭据读取范围没有展开，当前未验证。"
                )

        if direct_problem:
            return "error", direct_problem
        return "off", (
            "Exa 未配置。可任选一种方式：\n"
            "  agent-reach configure exa-key\n"
            "或安装 mcporter 后运行：\n"
            "  mcporter config add exa https://mcp.exa.ai/mcp --scope home"
        )
