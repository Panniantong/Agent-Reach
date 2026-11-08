# -*- coding: utf-8 -*-
"""Contract tests for channel adapters."""

from agent_reach.channels import get_all_channels


def test_channel_registry_contract():
    channels = get_all_channels()
    assert channels, "channel registry must not be empty"
    names = [ch.name for ch in channels]
    assert len(names) == len(set(names)), "channel names must be unique"
    assert "xiaoyuzhou" in names

    for ch in channels:
        assert isinstance(ch.name, str) and ch.name
        assert isinstance(ch.description, str) and ch.description
        assert ch.level in {"default", "optional", "experimental"}
        assert ch.actions, f"{ch.name} exposes no actions"
        for action in ch.actions:
            for _label, method in action.backends:
                assert callable(getattr(ch, method, None)), f"{ch.name}.{method}"


def test_channel_can_handle_contract():
    url_samples = {
        "github": "https://github.com/panniantong/agent-reach",
        "twitter": "https://x.com/user/status/1",
        "youtube": "https://youtube.com/watch?v=abc",
        "reddit": "https://reddit.com/r/python",
        "facebook": "https://www.facebook.com/zuck",
        "instagram": "https://www.instagram.com/openai/",
        "bilibili": "https://www.bilibili.com/video/BV1xx411",
        "xiaohongshu": "https://www.xiaohongshu.com/explore/123",
        "linkedin": "https://www.linkedin.com/in/test",
        "xueqiu": "https://xueqiu.com/S/SH600519",
        "web": "https://example.com",
    }
    for ch in get_all_channels():
        sample = url_samples.get(ch.name, "https://example.com")
        result = ch.can_handle(sample)
        assert isinstance(result, bool)
