# -*- coding: utf-8 -*-
"""Tests for agent_reach.utils.urlmatch.host_matches and channel routing."""

import pytest

from agent_reach.utils.urlmatch import host_matches


class TestHostMatches:
    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/u/r",
            "https://www.github.com/u/r",
            "https://api.github.com/repos",
            "HTTPS://GitHub.com/u/r",
            "https://github.com:443/u/r",
        ],
    )
    def test_matches_domain_and_subdomains(self, url):
        assert host_matches(url, "github.com")

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com.evil.com/u/r",   # look-alike suffix
            "https://evil-github.com/u/r",        # look-alike prefix
            "https://github.com@evil.com/u/r",    # userinfo trick — real host is evil.com
            "https://notgithub.com/u/r",
            "https://example.com/github.com",     # only in path
        ],
    )
    def test_rejects_lookalikes_and_userinfo(self, url):
        assert not host_matches(url, "github.com")

    def test_multiple_domains(self):
        assert host_matches("https://youtu.be/abc", "youtube.com", "youtu.be")
        assert host_matches("https://www.youtube.com/watch", "youtube.com", "youtu.be")
        assert not host_matches("https://vimeo.com/1", "youtube.com", "youtu.be")

    def test_non_url_inputs(self):
        assert not host_matches("github.com/u/r", "github.com")  # no scheme → no host
        assert not host_matches("", "github.com")
        assert not host_matches("not a url", "github.com")


class TestChannelRoutingNoLongerBypassable:
    def test_credentialed_channels_reject_userinfo_lookalike(self):
        # The exact bypass class: an attacker URL whose netloc *contains* the
        # real domain but whose host is evil.com must not be claimed by the
        # credentialed channel.
        from agent_reach.channels.github import GitHubChannel
        from agent_reach.channels.twitter import TwitterChannel
        from agent_reach.channels.xueqiu import XueqiuChannel

        assert not GitHubChannel().can_handle("https://github.com@evil.com/x")
        assert not GitHubChannel().can_handle("https://github.com.evil.com/x")
        assert not TwitterChannel().can_handle("https://x.com.evil.com/x")
        assert not XueqiuChannel().can_handle("https://xueqiu.com@evil.com/x")

    def test_legitimate_urls_still_route(self):
        from agent_reach.channels.github import GitHubChannel
        from agent_reach.channels.reddit import RedditChannel

        assert GitHubChannel().can_handle("https://github.com/panniantong/agent-reach")
        assert RedditChannel().can_handle("https://www.reddit.com/r/python")
        assert RedditChannel().can_handle("https://redd.it/abc")
