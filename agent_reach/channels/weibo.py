# -*- coding: utf-8 -*-
"""Weibo 微博 — OpenCLI backend using the user's logged-in Chrome session."""

from ._opencli_site import OpenCLISiteChannel


class WeiboChannel(OpenCLISiteChannel):
    name = "weibo"
    description = "微博帖子、用户主页和搜索"
    site = "weibo"
    domains = ("weibo.com", "weibo.cn", "m.weibo.cn", "t.cn")
    usage = "opencli weibo search/post/user/user-posts/comments/hot -f yaml"
    login_hint = "weibo.com"
