# -*- coding: utf-8 -*-
"""Firecrawl — 深度网页抓取、搜索与结构化提取。需要 Firecrawl API Key。"""

import json
import os
from typing import Optional

from .base import Channel


class FirecrawlChannel(Channel):
    name = "firecrawl"
    description = "Firecrawl深度网页抓取"
    backends = ["Firecrawl API"]
    tier = 1  # 需要免费 API Key

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_api_key(config=None) -> Optional[str]:
        """Resolve the Firecrawl API key from config or environment."""
        if config is not None:
            key = config.get("firecrawl_api_key")
            if key:
                return key
        return os.environ.get("FIRECRAWL_API_KEY")

    @staticmethod
    def _check_import() -> Optional[str]:
        """Try importing firecrawl; return None on success or a hint on failure."""
        try:
            import firecrawl  # noqa: F401
            return None
        except ImportError:
            return (
                "未安装 firecrawl-py。安装：\n"
                "  pip install firecrawl-py\n"
                "或：uv pip install firecrawl-py"
            )

    @staticmethod
    def _make_client(api_key: str):
        """Create a FirecrawlApp instance. Import is done lazily here so the
        channel can report missing dependencies gracefully in check()."""
        from firecrawl import FirecrawlApp
        return FirecrawlApp(api_key=api_key)

    # ------------------------------------------------------------------ #
    # Channel interface
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        """Firecrawl 是通用网页抓取渠道，接受任意 URL。"""
        return True

    def check(self, config=None):
        """检测 firecrawl-py 安装和 API Key 配置状态。

        返回 (status, message)，其中 status 为 'ok' / 'off' / 'error'。
        """
        self.active_backend = None

        # 1) 检查包是否安装
        import_hint = self._check_import()
        if import_hint is not None:
            return "off", import_hint

        # 2) 检查 API Key 是否已配置
        api_key = self._get_api_key(config)
        if not api_key:
            return "off", (
                "Firecrawl API Key 未设置。注册免费 Key 后配置：\n"
                "  agent-reach config set firecrawl_api_key fc-xxx\n"
                "或设置环境变量：\n"
                "  export FIRECRAWL_API_KEY=fc-xxx\n"
                "免费注册：https://firecrawl.dev"
            )

        # 3) 轻量连通性探测（credit usage 查询）
        try:
            client = self._make_client(api_key)
            usage = client.get_credit_usage()
        except Exception as exc:
            # A failed probe means the key is likely invalid or network is down.
            # We still report "warn" (key is present, just not confirmed healthy)
            self.active_backend = self.backends[0]
            return "warn", (
                f"Firecrawl API Key 已配置，但连通性探测失败：{exc}\n"
                "请检查网络或确认 Key 有效。"
            )

        self.active_backend = self.backends[0]
        # usage is a CreditUsage object; try to extract remaining credits
        remaining = ""
        try:
            rem = getattr(usage, "remaining", None)
            if rem is not None:
                remaining = f"，剩余额度 {rem}"
        except Exception:
            pass
        return "ok", f"Firecrawl API 可用{remaining}"

    # ------------------------------------------------------------------ #
    # Public methods
    # ------------------------------------------------------------------ #

    def read(self, url: str) -> str:
        """使用 Firecrawl scrape 抓取网页，返回 Markdown 全文。

        与 WebChannel.read() 保持相同签名，方便替换。
        """
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("Firecrawl API Key 未设置，请先配置 firecrawl_api_key")
        client = self._make_client(api_key)
        doc = client.scrape(url, formats=["markdown"])
        return doc.markdown or ""

    def crawl(self, url: str, max_depth: int = 2, limit: int = 10) -> str:
        """深度爬取网站，返回抓取结果摘要（JSON）。

        Args:
            url: 起始 URL。
            max_depth: 最大爬取深度（默认 2）。
            limit: 最多抓取页数（默认 10）。
        Returns:
            JSON 字符串，每页包含 url、title、markdown 片段。
        """
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("Firecrawl API Key 未设置，请先配置 firecrawl_api_key")
        client = self._make_client(api_key)
        job = client.crawl(
            url,
            max_discovery_depth=max_depth,
            limit=limit,
            scrape_options={"formats": ["markdown"]},
        )
        # crawl() returns a CrawlJob; poll if needed
        return self._wait_and_collect(client, job)

    def search(self, query: str, limit: int = 5) -> str:
        """使用 Firecrawl 搜索网络，返回结果摘要（JSON）。

        Args:
            query: 搜索关键词。
            limit: 返回结果数上限（默认 5）。
        Returns:
            JSON 字符串，每项包含 url、title、description。
        """
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("Firecrawl API Key 未设置，请先配置 firecrawl_api_key")
        client = self._make_client(api_key)
        result = client.search(query, limit=limit)
        # result is a SearchData pydantic model; dump to dict
        data = result.model_dump() if hasattr(result, "model_dump") else result
        return json.dumps(data, ensure_ascii=False, indent=2)

    def extract(
        self,
        urls: list,
        prompt: str,
        schema: dict = None,
    ) -> str:
        """使用 AI 从网页中提取结构化数据。

        Args:
            urls: 目标 URL 列表。
            prompt: 提取指令（自然语言描述需要的字段）。
            schema: 可选的 JSON Schema（默认 None）。
        Returns:
            JSON 字符串，包含提取的结构化数据。
        """
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("Firecrawl API Key 未设置，请先配置 firecrawl_api_key")
        client = self._make_client(api_key)
        kwargs = {"prompt": prompt}
        if schema is not None:
            kwargs["schema"] = schema
        result = client.extract(urls, **kwargs)
        data = result.model_dump() if hasattr(result, "model_dump") else result
        return json.dumps(data, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _maybe_pages(obj):
        """Return a list of page objects from *obj* if present and iterable."""
        for attr in ("pages", "data"):
            raw = getattr(obj, attr, None)
            if raw is not None and not isinstance(raw, (str, bytes)):
                try:
                    iter(raw)
                    return raw
                except TypeError:
                    pass
        return None

    def _wait_and_collect(self, client, job) -> str:
        """Wait for a crawl job to complete and collect markdown results.

        Firecrawl v2 crawl() returns a CrawlJob which may already contain
        pages if the job completed synchronously, or we need to poll using
        get_crawl_status().
        """
        import time

        # Try getting pages directly from the job
        pages = self._maybe_pages(job)
        if pages is not None:
            return self._format_crawl_pages(pages)

        # Poll for results
        job_id = getattr(job, "id", None)
        if not job_id or isinstance(job_id, type):
            return json.dumps({"error": "无法获取爬取任务 ID"}, ensure_ascii=False)

        max_wait = 120  # 最多等待 2 分钟
        interval = 3
        elapsed = 0
        while elapsed < max_wait:
            time.sleep(interval)
            elapsed += interval
            status = client.get_crawl_status(job_id)
            state = getattr(status, "status", None) or getattr(status, "state", None)
            if state in ("completed", "done", "finished"):
                pages = self._maybe_pages(status)
                if pages is not None:
                    return self._format_crawl_pages(pages)
                return json.dumps(
                    {"error": "爬取完成但无页面数据"}, ensure_ascii=False
                )
            if state in ("failed", "error", "cancelled"):
                return json.dumps(
                    {"error": f"爬取失败，状态: {state}"}, ensure_ascii=False
                )

        return json.dumps({"error": "爬取超时"}, ensure_ascii=False)

    @staticmethod
    def _format_crawl_pages(pages) -> str:
        """Format crawl page results as a readable JSON list."""
        items = []
        for page in pages:
            item = {}
            if hasattr(page, "url"):
                item["url"] = page.url
            elif hasattr(page, "metadata"):
                meta = page.metadata
                if isinstance(meta, dict):
                    item["url"] = meta.get("url", meta.get("sourceURL", ""))
                elif hasattr(meta, "url"):
                    item["url"] = meta.url
            if hasattr(page, "title"):
                item["title"] = page.title
            elif hasattr(page, "metadata") and isinstance(page.metadata, dict):
                item["title"] = page.metadata.get("title", "")
            markdown = getattr(page, "markdown", None)
            if markdown:
                item["markdown"] = markdown[:500]  # 截取前 500 字符作为摘要
            items.append(item)
        return json.dumps(items, ensure_ascii=False, indent=2)
