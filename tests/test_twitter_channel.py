# -*- coding: utf-8 -*-

import json
from pathlib import Path
from unittest.mock import Mock, patch

from agent_reach.channels.twitter import TwitterChannel


def _config(auth="", ct0=""):
    cfg = Mock()
    cfg.get.side_effect = lambda key: {
        "twitter_auth_token": auth,
        "twitter_ct0": ct0,
    }.get(key)
    return cfg


def test_check_twitter_with_agent_reach_config():
    channel = TwitterChannel()
    with patch("shutil.which", side_effect=lambda name: "/usr/local/bin/twitter" if name == "twitter" else None):
        status, message = channel.check(_config("token123", "ct0abc"))
    assert status == "ok"
    assert "非交互" in message
    assert "config.yaml" in message


def test_check_twitter_warns_when_binary_present_but_no_credentials(tmp_path, monkeypatch):
    channel = TwitterChannel()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with patch("shutil.which", side_effect=lambda name: "/usr/local/bin/twitter" if name == "twitter" else None):
        status, message = channel.check(_config())
    assert status == "warn"
    assert "twitter-cookies" in message


def test_check_bird_uses_saved_env_credentials(tmp_path, monkeypatch):
    channel = TwitterChannel()
    bird_dir = tmp_path / ".config" / "bird"
    bird_dir.mkdir(parents=True)
    (bird_dir / "credentials.env").write_text('AUTH_TOKEN="aaa"\nCT0="bbb"\n', encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    def which_side_effect(name):
        if name == "bird":
            return "/usr/local/bin/bird"
        return None

    with patch("shutil.which", side_effect=which_side_effect):
        status, message = channel.check(_config())
    assert status == "ok"
    assert "非交互" in message
    assert "credentials.env" in message


def test_check_twitter_uses_xfetch_session(tmp_path, monkeypatch):
    channel = TwitterChannel()
    xfetch_dir = tmp_path / ".config" / "xfetch"
    xfetch_dir.mkdir(parents=True)
    (xfetch_dir / "session.json").write_text(
        json.dumps({"authToken": "aaa", "ct0": "bbb"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    with patch("shutil.which", side_effect=lambda name: "/usr/local/bin/twitter" if name == "twitter" else None):
        status, message = channel.check(_config())
    assert status == "ok"
    assert "session.json" in message


def test_check_nothing_installed():
    channel = TwitterChannel()
    with patch("shutil.which", return_value=None):
        status, message = channel.check()
    assert status == "warn"
    assert "twitter-cli" in message
