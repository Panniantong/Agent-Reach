# -*- coding: utf-8 -*-
"""Cross-channel backends.

A backend here is an upstream runtime that serves MULTIPLE channels
(e.g. OpenCLI covers xiaohongshu/reddit/twitter/facebook/instagram through
the Agent Reach browser).
"""

from .opencli import OPENCLI_EXTENSION_URL, opencli_call, opencli_items  # noqa: F401
