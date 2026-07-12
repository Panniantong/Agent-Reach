# -*- coding: utf-8 -*-
"""Zhihu — OpenCLI backend using the user's logged-in Chrome session."""

from ._opencli_site import OpenCLISiteChannel


class ZhihuChannel(OpenCLISiteChannel):
    name = "zhihu"
    description = "知乎问答、文章和热榜"
    site = "zhihu"
    domains = ("zhihu.com",)
    usage = "opencli zhihu search/question/hot/user/answer-detail -f yaml"
    login_hint = "zhihu.com"
