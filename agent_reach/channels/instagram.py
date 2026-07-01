# -*- coding: utf-8 -*-
"""Instagram — OpenCLI backend using the user's logged-in Chrome session."""

from ._opencli_site import OpenCLISiteChannel


class InstagramChannel(OpenCLISiteChannel):
    name = "instagram"
    description = "Instagram 用户、主页和指定用户帖子"
    site = "instagram"
    domains = ("instagram.com", "instagr.am")
    usage = "opencli instagram search/profile/user/explore -f yaml"
    login_hint = "instagram.com"
