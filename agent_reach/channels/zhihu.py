# -*- coding: utf-8 -*-
"""Zhihu 知乎 — OpenCLI backend using the user's logged-in Chrome session."""

from ._opencli_site import OpenCLISiteChannel


class ZhihuChannel(OpenCLISiteChannel):
    name = "zhihu"
    description = "知乎问题、回答、专栏和搜索"
    site = "zhihu"
    domains = ("zhihu.com", "zhuanlan.zhihu.com")
    usage = "opencli zhihu search/question/answer-detail/user/user-answers/hot -f yaml"
    login_hint = "zhihu.com"
