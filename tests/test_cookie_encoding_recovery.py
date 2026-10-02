"""Corrupt saved cookies should yield recovery guidance, not decoder errors."""

import json
import subprocess

import pytest

from agent_reach.channels.reddit import RedditChannel
from agent_reach.channels.xiaohongshu import XiaoHongShuChannel


@pytest.mark.parametrize(
    "channel,method,relative_path,valid_payload",
    [
        (
            RedditChannel,
            "_check_rdt",
            ".config/rdt-cli/credential.json",
            {"cookies": {"reddit_session": "explicit-test-value"}},
        ),
        (
            XiaoHongShuChannel,
            "_check_xhs_cli",
            ".xiaohongshu-cli/cookies.json",
            {"a1": "explicit-test-value"},
        ),
    ],
)
@pytest.mark.parametrize("corrupt", [True, False])
def test_saved_cookie_encoding_recovery(
    monkeypatch, isolated_home, channel, method, relative_path, valid_payload, corrupt
):
    cookie_file = isolated_home / relative_path
    cookie_file.parent.mkdir(parents=True)
    content = b"\xff\xfe\x00" if corrupt else json.dumps(valid_payload).encode("utf-8")
    cookie_file.write_bytes(content)
    monkeypatch.setattr("shutil.which", lambda _: "/test/explicitly-installed-tool")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("must not run browser cookie extraction"),
    )

    instance = channel()
    instance.active_backend = None
    status, message = getattr(instance, method)()

    assert status == "warn"
    assert instance.active_backend is None
    assert cookie_file.read_bytes() == content
    assert "explicit-test-value" not in message
    if corrupt:
        assert "无法安全读取" in message
    else:
        assert "未实时验证" in message
