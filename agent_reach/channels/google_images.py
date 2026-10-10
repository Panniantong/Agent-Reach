# -*- coding: utf-8 -*-
"""Google Images — Custom Search JSON API (searchType=image), official and free-tier.

Google blocks automated scraping of its search/image result pages outright
(Terms of Service, active bot detection) — this channel deliberately does NOT
scrape google.com. It routes through Google's own Custom Search JSON API
instead, the only way to query Google Images programmatically without
violating Google's terms. The free tier is 100 queries/day; beyond that it's
metered per Google Cloud billing.

Doctor never fires a live query here: the free tier is capped at 100/day, and
burning one on every `doctor` run would be wasteful. check() only confirms
both credentials are present, matching how twitter-cli/gh credentials are
already handled (see .twitter/.github) — configured-but-unverified stays warn.
"""

from .base import Channel

_SETUP_STEPS = (
    "  1. https://programmablesearchengine.google.com/ 创建搜索引擎，"
    "勾选「搜索整个网络」并在设置里开启图片搜索\n"
    "  2. https://console.cloud.google.com/ 启用 Custom Search API，生成 API Key\n"
    "  3. agent-reach configure google-key\n"
    "     agent-reach configure google-cx"
)


class GoogleImagesChannel(Channel):
    name = "google_images"
    description = "Google 图片搜索（Custom Search API，免费额度 100 次/天）"
    backends = ["Google Custom Search API"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        self.active_backend = None
        if config is None:
            return "off", f"未配置 Google 图片搜索：\n{_SETUP_STEPS}"

        has_key = bool(config.get("google_api_key"))
        has_cx = bool(config.get("google_cx"))

        if has_key and has_cx:
            return "warn", (
                "Google API Key 和 Search Engine ID 均已配置；Doctor 不发起真实查询"
                "（避免消耗每日 100 次免费额度），凭据是否有效未实时验证。"
            )

        missing = []
        if not has_key:
            missing.append("google-key")
        if not has_cx:
            missing.append("google-cx")
        return "off", (
            f"Google 图片搜索未配置完整，缺少：{'、'.join(missing)}。\n{_SETUP_STEPS}"
        )
