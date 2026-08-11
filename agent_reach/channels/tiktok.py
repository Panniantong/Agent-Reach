# -*- coding: utf-8 -*-
"""TikTok — OpenCLI backend using the user's logged-in Chrome session."""

from ._opencli_site import OpenCLISiteChannel


class TikTokChannel(OpenCLISiteChannel):
    name = "tiktok"
    description = "TikTok 用户、公开视频和当前账号创作者指标"
    site = "tiktok"
    domains = ("tiktok.com",)
    usage = "opencli tiktok profile/search/user/explore/creator-videos -f yaml"
    login_hint = "tiktok.com"
