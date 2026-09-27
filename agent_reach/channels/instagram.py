# -*- coding: utf-8 -*-
"""Instagram — OpenCLI backend using the user's logged-in Chrome session."""

from ._opencli_site import OpenCLISiteChannel


class InstagramChannel(OpenCLISiteChannel):
    name = "instagram"
    description = "Instagram Users, Pages, and Targeted User Posts"
    site = "instagram"
    domains = ("instagram.com", "instagr.am")
    usage = "opencli instagram search/profile/user/explore -f yaml"
    login_hint = "instagram.com"
