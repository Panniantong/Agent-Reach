# -*- coding: utf-8 -*-
"""Douyin -- OpenCLI backend using the user's logged-in Chrome session."""

from ._opencli_site import OpenCLISiteChannel


class DouyinChannel(OpenCLISiteChannel):
    name = "douyin"
    description = "抖音视频、用户和话题"
    site = "douyin"
    domains = ("douyin.com",)
    usage = "opencli douyin search/video/user/feed -f yaml"
    login_hint = "douyin.com"
