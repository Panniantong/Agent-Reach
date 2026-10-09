# -*- coding: utf-8 -*-
"""Threads — OpenCLI backend using the user's logged-in Chrome session."""

from ._opencli_site import OpenCLISiteChannel


class ThreadsChannel(OpenCLISiteChannel):
    name = "threads"
    description = "Threads 帖子、回复和用户主页"
    site = "threads"
    domains = ("threads.com", "threads.net")
    usage = "opencli threads search/post/user -f yaml"
    login_hint = "threads.com"
