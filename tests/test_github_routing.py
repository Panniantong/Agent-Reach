"""`read <url>` sends a github.com link to the GitHub channel only when that channel can read it."""

import json

import pytest

from agent_reach.channels.base import Action, Channel, Param
from agent_reach.channels.github import GitHubChannel
from agent_reach.runtime import cli as unified

READABLE = [
    "https://github.com/yt-dlp/yt-dlp",
    "https://github.com/yt-dlp/yt-dlp.git",
    "https://github.com/cli/cli/issues/42",
    "https://github.com/cli/cli/pull/7?x=1",
    "https://www.github.com/openai/openai-python",
    "https://github.com:443/openai/openai-python",
]

NOT_READABLE = [
    "https://github.com/yt-dlp/yt-dlp/blob/master/README.md",
    "https://github.com/yt-dlp/yt-dlp/tree/master/yt_dlp/extractor",
    "https://github.com/cli/cli/pull/7/files",
    "https://github.com/yt-dlp/yt-dlp/releases/tag/2024.12.13",
    "https://github.com/yt-dlp",
    "https://github.com/",
    "https://docs.github.com/en/rest/repos/contents",
    "https://gist.github.com/someone/0123456789abcdef",
    "https://api.github.com/repos/openai/openai-python",
]


@pytest.mark.parametrize("url", READABLE)
def test_github_claims_links_it_can_read(url):
    assert GitHubChannel().can_handle(url)


@pytest.mark.parametrize("url", NOT_READABLE)
def test_github_leaves_other_github_links_to_the_web_reader(url):
    assert not GitHubChannel().can_handle(url)


class FakeWebChannel(Channel):
    name = "web"
    description = "web"
    level = "default"
    actions = (Action("read", "read", (Param("target", "t"),), (("only", "_read"),)),)

    def can_handle(self, url):
        return True

    def _read(self, **kw):
        return [{"title": kw["target"]}]


@pytest.mark.parametrize("url", NOT_READABLE[:4])
def test_read_falls_back_to_web_for_github_links_the_github_channel_rejects(
    monkeypatch, capsys, url
):
    monkeypatch.setattr(unified, "get_all_channels", lambda: [GitHubChannel(), FakeWebChannel()])
    code = unified.main(["read", url])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert code == 0
    assert out["channel"] == "web"
    assert out["items"][0]["title"] == url
