# -*- coding: utf-8 -*-
"""Facebook — OpenCLI backend using the user's logged-in Chrome session."""

from ._opencli_site import OpenCLISiteChannel


class FacebookChannel(OpenCLISiteChannel):
    name = "facebook"
    description = "Facebook 帖子、主页和群组"
    site = "facebook"
    domains = ("facebook.com", "fb.com", "fb.watch")
    usage = "opencli facebook search/profile/feed/groups -f yaml"
    login_hint = "facebook.com"
