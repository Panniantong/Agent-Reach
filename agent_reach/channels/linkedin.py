# -*- coding: utf-8 -*-
"""LinkedIn — OpenCLI backend using the user's logged-in Chrome session.

Replaces the previous linkedin-scraper-mcp backend, which required a
separately installed localhost MCP server. OpenCLI reuses the browser
session that is already there. Health reporting stays deliberately
conservative: OpenCLISiteChannel.check() never claims "ok" from the
bridge alone, because Doctor does not execute platform commands.
"""

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
