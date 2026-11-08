"""Kuaishou download action, CDN boundaries, file integrity and cleanup contracts."""

import hashlib
import json
from pathlib import Path

import pytest
import requests

from agent_reach.channels import kuaishou_download as media
from agent_reach.channels.kuaishou import KuaishouChannel
from agent_reach.runtime import cli, state
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import BAD_INPUT, RATE_LIMITED, TIMEOUT, UPSTREAM_BROKEN, ReachError

MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
MEDIA_URL = "https://v1.kwaicdn.com/video.mp4?pkey=private-test-signature"


class Response:
    def __init__(self, body=MP4, *, status=200, headers=None, failure=None):
        self.body, self.status_code, self.failure = body, status, failure
        self.headers = headers if headers is not None else {
            "Content-Type": "video/mp4", "Content-Length": str(len(body)),
        }
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def iter_content(self, chunk_size):
        yield self.body[:12]
        if self.failure:
            raise self.failure
        yield self.body[12:]


def mock_detail(monkeypatch):
    item = {"title": "A walk", "url": "https://www.kuaishou.com/short-video/work-1",
            "author": "Creator", "published_at": None, "text": "A walk",
            "raw": {"photo": {"id": "work-1", "photoUrl": MEDIA_URL}}}
    monkeypatch.setattr(KuaishouChannel, "_browser_read", lambda *a, **kw: [item])


def test_download_cli_writes_mp4_and_returns_local_metadata(tmp_path, monkeypatch, capsys):
    mock_detail(monkeypatch)
    response = Response()
    monkeypatch.setattr(media.requests, "get", lambda *a, **kw: response)
    target = tmp_path / "exports" / "video.mp4"

    code = cli.main(["kuaishou", "download", "work-1", "--output", str(target)])
    result = json.loads(capsys.readouterr().out)

    assert code == 0 and result["ok"] is True
    assert result["action"] == "download"
    assert target.read_bytes() == MP4
    assert response.closed
    assert result["items"][0]["raw"] == {
        "path": str(target), "bytes": len(MP4), "sha256": hashlib.sha256(MP4).hexdigest(),
    }
    assert "private-test-signature" not in json.dumps(result)
    assert list(target.parent.iterdir()) == [target]


def test_download_defaults_to_managed_directory(monkeypatch):
    mock_detail(monkeypatch)
    monkeypatch.setattr(media.requests, "get", lambda *a, **kw: Response())

    result = run_action(KuaishouChannel(), "download", {"target": "work-1"})

    assert result["ok"] is True
    target = state.root() / "downloads" / "kuaishou" / "work-1.mp4"
    assert Path(result["items"][0]["raw"]["path"]) == target
    assert target.read_bytes() == MP4
    assert state.owned_path(target.parent)


@pytest.mark.parametrize("kind", ["existing", "directory", "extension", "parent-file", "bad-target"])
def test_invalid_download_input_never_opens_browser(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(KuaishouChannel, "_browser_read",
                        lambda *a, **kw: pytest.fail("invalid output opened a browser"))
    output = tmp_path / "video.mp4"
    target = "work-1"
    if kind == "existing":
        output.write_bytes(b"keep existing file")
    elif kind == "directory":
        output.mkdir()
    elif kind == "extension":
        output = tmp_path / "video.txt"
    elif kind == "parent-file":
        parent = tmp_path / "file"
        parent.write_text("keep")
        output = parent / "video.mp4"
    else:
        target = "https://example.org/work-1"

    result = run_action(KuaishouChannel(), "download", {"target": target, "output": str(output)})

    assert result["ok"] is False
    assert result["error"]["code"] == BAD_INPUT
    if kind == "existing":
        assert output.read_bytes() == b"keep existing file"


@pytest.mark.parametrize("photo,expected", [
    ({"photoUrl": MEDIA_URL, "mainMvUrls": "https://v2.kwaicdn.com/other.mp4"}, MEDIA_URL),
    ({"mainMvUrls": [{"url": MEDIA_URL}]}, MEDIA_URL),
    ({"manifest": {"adaptationSet": [{"representation": [{}, {"url": MEDIA_URL}]}]}}, MEDIA_URL),
    ({"manifestH265": {"adaptationSet": [{"representation": [{"url": MEDIA_URL}]}]}}, MEDIA_URL),
])
def test_selects_video_fields_in_baseline_order(photo, expected):
    assert media._video_url(photo) == expected


def test_missing_stream_fails_before_network_or_creating_output(tmp_path, monkeypatch):
    monkeypatch.setattr(media.requests, "get", lambda *a, **kw: pytest.fail("missing stream requested HTTP"))
    target = tmp_path / "new" / "video.mp4"

    with pytest.raises(ReachError) as error:
        media.download_video({}, target, timeout=10)

    assert error.value.code == UPSTREAM_BROKEN
    assert not target.parent.exists()


def test_redirects_keep_referer_and_validate_destination(tmp_path, monkeypatch):
    calls = []
    responses = [Response(status=302, headers={"Location": "https://v2.kwaicdn.com/video.mp4"}),
                 Response()]

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return responses[len(calls) - 1]

    monkeypatch.setattr(media.requests, "get", get)

    media.download_video({"photoUrl": MEDIA_URL}, tmp_path / "video.mp4", timeout=10)

    assert [url.split("?", 1)[0] for url, _ in calls] == [
        "https://v1.kwaicdn.com/video.mp4", "https://v2.kwaicdn.com/video.mp4",
    ]
    assert all(kwargs["headers"]["Referer"] == "https://www.kuaishou.com/" for _, kwargs in calls)
    assert all(kwargs["allow_redirects"] is False for _, kwargs in calls)
    assert all(response.closed for response in responses)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/private", "https://kwaicdn.com.evil.test/video.mp4",
    "https://user:password@v1.kwaicdn.com/video.mp4", "file:///tmp/video.mp4",
])
def test_rejects_unsupported_initial_or_redirected_media_hosts(tmp_path, monkeypatch, url):
    calls = []
    before = set(tmp_path.iterdir())

    def get(source, **kwargs):
        calls.append(source)
        return Response(status=302, headers={"Location": url})

    monkeypatch.setattr(media.requests, "get", get)
    with pytest.raises(ReachError) as error:
        media.download_video({"photoUrl": url}, tmp_path / "initial.mp4", timeout=10)
    assert error.value.code == UPSTREAM_BROKEN
    assert calls == []

    with pytest.raises(ReachError) as error:
        media.download_video({"photoUrl": MEDIA_URL}, tmp_path / "redirect.mp4", timeout=10)
    assert error.value.code == UPSTREAM_BROKEN
    assert calls == [MEDIA_URL]
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("response,code", [
    (Response(status=429), RATE_LIMITED),
    (Response(status=403), UPSTREAM_BROKEN),
    (Response(headers={"Content-Type": "text/html"}), UPSTREAM_BROKEN),
    (Response(body=b"not a video"), UPSTREAM_BROKEN),
    (Response(headers={"Content-Length": "1000"}), UPSTREAM_BROKEN),
    (Response(failure=requests.ConnectionError("signed URL: " + MEDIA_URL)), UPSTREAM_BROKEN),
    (Response(failure=requests.Timeout("signed URL: " + MEDIA_URL)), TIMEOUT),
])
def test_failed_transfers_leave_no_partial_file_or_credentials(tmp_path, monkeypatch, response, code):
    before = set(tmp_path.iterdir())
    monkeypatch.setattr(media.requests, "get", lambda *a, **kw: response)

    with pytest.raises(ReachError) as error:
        media.download_video({"photoUrl": MEDIA_URL}, tmp_path / "video.mp4", timeout=10)

    assert error.value.code == code
    assert "private-test-signature" not in str(error.value)
    assert set(tmp_path.iterdir()) == before
    assert response.closed


def test_destination_created_during_transfer_is_not_replaced(tmp_path, monkeypatch):
    target = tmp_path / "video.mp4"
    before = set(tmp_path.iterdir())

    class RacingResponse(Response):
        def iter_content(self, chunk_size):
            target.write_bytes(b"another download won")
            yield MP4

    monkeypatch.setattr(media.requests, "get", lambda *a, **kw: RacingResponse())

    with pytest.raises(ReachError) as error:
        media.download_video({"photoUrl": MEDIA_URL}, target, timeout=10)

    assert error.value.code == BAD_INPUT
    assert target.read_bytes() == b"another download won"
    assert set(tmp_path.iterdir()) == before | {target}


def test_expired_download_budget_never_publishes_file(tmp_path, monkeypatch):
    clock = [0.0]
    before = set(tmp_path.iterdir())

    class SlowResponse(Response):
        def iter_content(self, chunk_size):
            clock[0] = 5.0
            yield MP4

    monkeypatch.setattr(media.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(media.requests, "get", lambda *a, **kw: SlowResponse())

    with pytest.raises(ReachError) as error:
        media.download_video({"photoUrl": MEDIA_URL}, tmp_path / "video.mp4", timeout=1)

    assert error.value.code == TIMEOUT
    assert set(tmp_path.iterdir()) == before
