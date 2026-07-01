# -*- coding: utf-8 -*-
"""can_handle() must reject lookalike / spoofed hosts.

Every credentialed channel routes on its platform host. A lookalike host such
as ``x.com.evil.test`` or a userinfo spoof ``x.com@evil.test`` must NOT be
claimed by the platform channel — otherwise the channel would attach the
user's auth cookies to an attacker-controlled request.
"""

import pytest

from agent_reach.channels.bilibili import BilibiliChannel
from agent_reach.channels.github import GitHubChannel
from agent_reach.channels.linkedin import LinkedInChannel
from agent_reach.channels.reddit import RedditChannel
from agent_reach.channels.twitter import TwitterChannel
from agent_reach.channels.v2ex import V2EXChannel
from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
from agent_reach.channels.xiaoyuzhou import XiaoyuzhouChannel
from agent_reach.channels.xueqiu import XueqiuChannel
from agent_reach.channels.youtube import YouTubeChannel

# (channel factory, an accepted URL, its host used for the lookalike)
CASES = [
    (TwitterChannel, "https://x.com/jack", "x.com"),
    (TwitterChannel, "https://twitter.com/jack", "twitter.com"),
    (YouTubeChannel, "https://www.youtube.com/watch?v=x", "youtube.com"),
    (RedditChannel, "https://www.reddit.com/r/python/", "reddit.com"),
    (BilibiliChannel, "https://www.bilibili.com/video/BV1", "bilibili.com"),
    (LinkedInChannel, "https://www.linkedin.com/in/x", "linkedin.com"),
    (XiaoHongShuChannel, "https://www.xiaohongshu.com/explore/x", "xiaohongshu.com"),
    (XueqiuChannel, "https://xueqiu.com/S/SH600519", "xueqiu.com"),
    (GitHubChannel, "https://github.com/user/repo", "github.com"),
    (V2EXChannel, "https://www.v2ex.com/t/1", "v2ex.com"),
    (XiaoyuzhouChannel, "https://www.xiaoyuzhoufm.com/episode/x", "xiaoyuzhoufm.com"),
]


@pytest.mark.parametrize("factory,good_url,host", CASES)
def test_accepts_legit_host(factory, good_url, host):
    assert factory().can_handle(good_url)


@pytest.mark.parametrize("factory,good_url,host", CASES)
def test_rejects_suffix_lookalike(factory, good_url, host):
    assert not factory().can_handle(f"https://{host}.evil.test/foo")


@pytest.mark.parametrize("factory,good_url,host", CASES)
def test_rejects_prefix_lookalike(factory, good_url, host):
    assert not factory().can_handle(f"https://not{host}/foo")


@pytest.mark.parametrize("factory,good_url,host", CASES)
def test_rejects_userinfo_spoof(factory, good_url, host):
    assert not factory().can_handle(f"https://{host}@evil.test/foo")
