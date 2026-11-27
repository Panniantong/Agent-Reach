# -*- coding: utf-8 -*-
"""Twitter thread target parsing."""

import pytest

from agent_reach.channels import twitter
from agent_reach.channels.twitter import TwitterChannel


@pytest.mark.parametrize(
    "target",
    [
        "1234567890",
        "https://x.com/OpenAI/status/1234567890",
        "https://x.com/OpenAI/status/1234567890/",
        "https://x.com/OpenAI/status/1234567890?s=20",
        "https://x.com/OpenAI/status/1234567890/photo/1",
        "https://twitter.com/OpenAI/status/1234567890/video/1",
        "https://x.com/OpenAI/status/1234567890/analytics",
        "https://x.com/i/web/status/1234567890",
    ],
)
def test_thread_uses_the_status_id(monkeypatch, target):
    calls = []
    monkeypatch.setattr(twitter, "_x", lambda args, timeout: calls.append(args) or [{}])

    TwitterChannel()._opencli_thread(target=target, timeout=5)

    assert calls == [["thread", "1234567890"]]
