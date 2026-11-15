import json

import pytest

from agent_reach.channels import bilibili
from agent_reach.channels.bilibili import BilibiliChannel
from agent_reach.runtime.dispatch import run_action


class _Response:
    def __init__(self, url):
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def geturl(self):
        return self._url


@pytest.mark.parametrize(
    "target",
    [
        "http://127.0.0.1:8000/b23.tv/not-a-video",
        "https://example.test/?next=b23.tv/not-a-video",
    ],
)
def test_read_rejects_disguised_b23_links_before_network(monkeypatch, target):
    requested = []

    def fake_urlopen(request, timeout):
        requested.append(request.full_url)
        return _Response(request.full_url)

    monkeypatch.setattr(bilibili.urllib.request, "urlopen", fake_urlopen)

    result = run_action(
        BilibiliChannel(), "read", {"target": target}, only_backend="bili-cli"
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "BAD_INPUT"
    assert requested == []


@pytest.mark.parametrize(
    ("target", "expected_request"),
    [
        ("https://www.bilibili.com/video/BV1GJ411x7h7", None),
        ("https://b23.tv/example", "https://b23.tv/example"),
        ("b23.tv/example", "https://b23.tv/example"),
    ],
)
def test_read_accepts_bv_and_official_b23_links(monkeypatch, target, expected_request):
    requested = []

    def fake_urlopen(request, timeout):
        requested.append(request.full_url)
        return _Response("https://www.bilibili.com/video/BV1GJ411x7h7")

    def fake_run_cmd(argv, **kwargs):
        assert argv == ["bili", "video", "BV1GJ411x7h7", "--json"]
        return json.dumps({"ok": True, "data": {"video": {"bvid": "BV1GJ411x7h7"}}})

    monkeypatch.setattr(bilibili.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(bilibili, "run_cmd", fake_run_cmd)

    result = run_action(
        BilibiliChannel(), "read", {"target": target}, only_backend="bili-cli"
    )

    assert result["ok"] is True
    assert result["items"][0]["url"] == "https://www.bilibili.com/video/BV1GJ411x7h7"
    assert requested == ([expected_request] if expected_request else [])
