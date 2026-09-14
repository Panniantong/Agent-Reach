# -*- coding: utf-8 -*-
"""Nowcoder — OpenCLI browser-backed search and interview experiences."""

from ._opencli_site import OpenCLISiteChannel


class NowcoderChannel(OpenCLISiteChannel):
    """牛客公开面经与求职内容的 OpenCLI 路由。"""

    name = "nowcoder"
    description = "牛客面经与求职内容"
    site = "nowcoder"
    domains = ("nowcoder.com",)
    usage = "opencli nowcoder search/experience/detail -f yaml"
    login_hint = "nowcoder.com"
    requires_login = False
