# -*- coding: utf-8 -*-
"""Web search — task-aware Tavily primary with Exa specialization/fallback."""

import os
import re
import shutil

import requests

from .base import Channel
from .mcporter import McporterConfigError, inspect_mcporter_config


class ExaSearchChannel(Channel):
    name = "exa_search"
    description = "全网搜索（Tavily 默认；Exa 专项/备选）"
    TAVILY_BACKEND = "Tavily via REST"
    EXA_BACKEND = "Exa via mcporter"
    backends = [TAVILY_BACKEND, EXA_BACKEND]
    tier = 0
    _TAVILY_USAGE_URL = "https://api.tavily.com/usage"
    EXA_TASKS = frozenset(
        {
            "academic",
            "arxiv",
            "company",
            "companies",
            "企业",
            "公司",
            "financial_report",
            "财报",
            "金融报告",
            "学术",
            "论文",
            "people",
            "person",
            "paper",
            "papers",
            "rag",
            "research_paper",
            "retrieval",
            "semantic",
            "semantic_search",
            "semantic_discovery",
            "similar",
            "similar_page",
            "similar_pages",
            "technical_research",
            "research_papers",
            "financial_reports",
            "company_profile",
            "people_search",
            "person_profile",
            "rag_retrieval",
            "retrieval_augmented_generation",
            "相似",
            "语义",
            "语义搜索",
            "检索",
            "人物",
        }
    )

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def _configured_backend(self, config=None):
        if not config:
            return None
        override = None
        for key in ("search_backend", "web_search_backend", f"{self.name}_backend"):
            override = config.get(key)
            if override:
                break
        if not override:
            return None

        aliases = {
            "tavily": self.TAVILY_BACKEND,
            "exa": self.EXA_BACKEND,
        }
        target = aliases.get(str(override).strip().casefold(), str(override).strip())
        for backend in self.backends:
            if backend.casefold() == target.casefold() or backend.casefold().startswith(
                target.casefold()
            ):
                return backend
        return None

    def backend_for_task(self, task=None, config=None):
        """Choose the backend for a named search task.

        Tavily remains the default for general/news/extract/crawl/research
        workflows. Exa is preferred for semantic retrieval and specialized
        paper, company, people, financial-report, or similar-page discovery.
        An explicit backend override always wins.
        """
        configured = self._configured_backend(config)
        if configured:
            return configured
        normalized = self._normalize_task(task)
        return self.EXA_BACKEND if normalized in self.EXA_TASKS else self.TAVILY_BACKEND

    @staticmethod
    def _normalize_task(task):
        """Normalize task labels without treating generic research as Exa."""
        normalized = str(task or "general").strip().casefold()
        normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", normalized)
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        for prefix in ("category_", "task_", "type_", "类别_", "任务_", "类型_"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
                break
        return normalized

    def ordered_backends(self, config=None, task=None):
        """Order backends for a task, with explicit config taking precedence."""
        candidates = list(self.backends)
        preferred = self._configured_backend(config)
        if not preferred and task is not None:
            preferred = self.backend_for_task(task)
        if not preferred:
            return candidates

        for index, backend in enumerate(candidates):
            if backend == preferred:
                candidates.insert(0, candidates.pop(index))
                break
        return candidates

    def check(self, config=None, task=None):
        self.active_backend = None
        findings = []
        saw_warn = False
        saw_error = False
        for backend in self.ordered_backends(config, task=task):
            if backend == self.TAVILY_BACKEND:
                status, message = self._check_tavily(config)
            else:
                status, message = self._check_exa()

            if status == "ok":
                self.active_backend = backend
                return status, message
            saw_warn = saw_warn or status == "warn"
            saw_error = saw_error or status == "error"
            findings.append(f"{backend}: {message}")

        status = "error" if saw_error else "warn" if saw_warn else "off"
        return status, "\n".join(findings)

    def _check_tavily(self, config=None):
        """Validate the key without spending a search credit."""
        api_key = config.get("tavily_api_key") if config else None
        api_key = api_key or os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return "off", (
                "Tavily 未配置 API key。运行：\n"
                "  agent-reach configure tavily-key"
            )

        try:
            response = requests.get(
                self._TAVILY_USAGE_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
        except requests.RequestException:
            return "warn", "Tavily API 暂时无法连接；将继续尝试 Exa。"

        if response.status_code == 200:
            try:
                usage = response.json().get("key", {})
            except (TypeError, ValueError):
                usage = {}
            used = usage.get("usage")
            limit = usage.get("limit")
            suffix = f"（已用 {used}/{limit} credits）" if isinstance(
                used, (int, float)
            ) and isinstance(limit, (int, float)) else ""
            return "ok", f"Tavily API 可用{suffix}"
        if response.status_code == 401:
            return "warn", "Tavily API key 无效；将继续尝试 Exa。"
        if response.status_code == 429:
            return "warn", "Tavily API 请求受限；将继续尝试 Exa。"
        return "warn", f"Tavily API 检查失败（HTTP {response.status_code}）；将继续尝试 Exa。"

    def _check_exa(self):
        if not shutil.which("mcporter"):
            return "off", (
                "需要 mcporter + Exa MCP。安装：\n"
                "  npm install -g mcporter\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp --scope home"
            )
        try:
            inspection = inspect_mcporter_config()
        except McporterConfigError as exc:
            return "error", f"mcporter 配置检查失败：{exc}"
        if "exa" in inspection.server_names:
            return "warn", (
                "Exa 已写入 mcporter 配置，但 Doctor 未启动远端服务做"
                "连通验证，不能仅凭配置宣称可用。"
            )
        if inspection.imports_unchecked:
            return "warn", (
                "mcporter 本地配置未发现 Exa；配置还启用了 editor imports，"
                "Doctor 为避免扩大凭据读取范围没有展开，当前未验证。"
            )
        return "off", (
            "mcporter 已装但 Exa 未配置。运行：\n"
            "  mcporter config add exa https://mcp.exa.ai/mcp --scope home"
        )
