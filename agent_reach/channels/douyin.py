# -*- coding: utf-8 -*-
"""Douyin 抖音 — OpenCLI backend using the user's logged-in Chrome session."""

from ._opencli_site import OpenCLISiteChannel


class DouyinChannel(OpenCLISiteChannel):
    name = "douyin"
    description = "抖音视频、用户主页和搜索"
    site = "douyin"
    domains = ("douyin.com", "iesdouyin.com", "v.douyin.com")
    usage = "opencli douyin search/user-videos/videos/hashtag -f yaml"
    login_hint = "douyin.com"
    # ponytail: 纯 OpenCLI（复用 Chrome 登录态）。若要免登录抓视频/字幕，
    # 参照 twitter.py 升级成多后端，加 yt-dlp 作 backends[1] fallback（yt-dlp 原生支持抖音）。
