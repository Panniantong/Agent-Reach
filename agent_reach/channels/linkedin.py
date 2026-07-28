# -*- coding: utf-8 -*-
"""LinkedIn — OpenCLI backend using the user's logged-in Chrome session."""

from ._opencli_site import OpenCLISiteChannel


class LinkedInChannel(OpenCLISiteChannel):
    name = "linkedin"
    description = "LinkedIn 职业社交"
    site = "linkedin"
    domains = ("linkedin.com",)
    usage = (
        "opencli linkedin search(jobs)/job-detail/profile-read/posts/timeline "
        "-f yaml；找人用 people-search（消耗 LinkedIn 每月商业使用额度）"
    )
    login_hint = "linkedin.com"
