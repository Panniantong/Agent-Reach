"""Doctor must not trigger upstream browser-cookie refresh or persistence."""

from __future__ import annotations

import json
import subprocess
import time

from agent_reach.channels.reddit import RedditChannel
from agent_reach.channels.twitter import TwitterChannel
from agent_reach.channels.xiaohongshu import XiaoHongShuChannel


def _forbid_subprocess(*_args, **_kwargs):
    raise AssertionError("credential-backed health checks must not execute upstream CLIs")


def test_twitter_doctor_does_not_start_cli_without_explicit_credentials(
    monkeypatch,
):
    monkeypatch.delenv("TWITTER_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_CT0", raising=False)
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/local/bin/twitter" if name == "twitter" else None,
    )
    monkeypatch.setattr(subprocess, "run", _forbid_subprocess)

    channel = TwitterChannel()
    status, message = channel.check()

    assert status == "warn"
    assert channel.active_backend is None
    assert "Cookie-Editor" in message
    assert "浏览器" not in message or "不会" in message


def test_twitter_doctor_still_avoids_upstream_fallback_with_saved_credentials(
    monkeypatch,
):
    class Config:
        def get(self, key, default=None):
            return {
                "twitter_auth_token": "explicit-auth",
                "twitter_ct0": "explicit-ct0",
            }.get(key, default)

    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/local/bin/twitter" if name == "twitter" else None,
    )
    monkeypatch.setattr(subprocess, "run", _forbid_subprocess)

    status, message = TwitterChannel().check(Config())

    assert status == "warn"
    assert "已配置" in message
    assert "不会执行" in message


def test_reddit_doctor_does_not_create_or_refresh_missing_credentials(
    isolated_home, monkeypatch
):
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/local/bin/rdt" if name == "rdt" else None,
    )
    monkeypatch.setattr(subprocess, "run", _forbid_subprocess)

    channel = RedditChannel()
    status, message = channel.check()

    assert status == "warn"
    assert channel.active_backend is None
    assert "Cookie-Editor" in message
    assert not (isolated_home / ".config" / "rdt-cli").exists()


def test_reddit_doctor_reports_stale_saved_credential_without_refresh(
    isolated_home, monkeypatch
):
    credential_path = (
        isolated_home / ".config" / "rdt-cli" / "credential.json"
    )
    credential_path.parent.mkdir(parents=True)
    credential_path.write_text(
        json.dumps(
            {
                "cookies": {"reddit_session": "explicit-cookie"},
                "saved_at": time.time() - 8 * 86400,
            }
        ),
        encoding="utf-8",
    )
    original = credential_path.read_bytes()
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/local/bin/rdt" if name == "rdt" else None,
    )
    monkeypatch.setattr(subprocess, "run", _forbid_subprocess)

    status, message = RedditChannel().check()

    assert status == "warn"
    assert "超过 7 天" in message
    assert credential_path.read_bytes() == original


def test_xhs_doctor_does_not_create_or_extract_missing_cookies(
    isolated_home, monkeypatch
):
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/local/bin/xhs" if name == "xhs" else None,
    )
    monkeypatch.setattr(subprocess, "run", _forbid_subprocess)
    monkeypatch.setattr(
        XiaoHongShuChannel,
        "_check_opencli",
        lambda self: None,
    )
    monkeypatch.setattr(
        XiaoHongShuChannel,
        "_check_mcp",
        lambda self: None,
    )

    channel = XiaoHongShuChannel()
    status, message = channel.check()

    assert status == "warn"
    assert channel.active_backend is None
    assert "Cookie-Editor" in message
    assert not (isolated_home / ".xiaohongshu-cli").exists()


def test_xhs_doctor_reports_stale_cookie_without_refresh(
    isolated_home, monkeypatch
):
    cookie_path = isolated_home / ".xiaohongshu-cli" / "cookies.json"
    cookie_path.parent.mkdir(parents=True)
    cookie_path.write_text(
        json.dumps(
            {
                "a1": "explicit-cookie",
                "saved_at": time.time() - 8 * 86400,
            }
        ),
        encoding="utf-8",
    )
    original = cookie_path.read_bytes()
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/local/bin/xhs" if name == "xhs" else None,
    )
    monkeypatch.setattr(subprocess, "run", _forbid_subprocess)
    monkeypatch.setattr(
        XiaoHongShuChannel,
        "_check_opencli",
        lambda self: None,
    )
    monkeypatch.setattr(
        XiaoHongShuChannel,
        "_check_mcp",
        lambda self: None,
    )

    status, message = XiaoHongShuChannel().check()

    assert status == "warn"
    assert "超过 7 天" in message
    assert cookie_path.read_bytes() == original
