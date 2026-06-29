# -*- coding: utf-8 -*-
"""Verify credential files written by cookie sync helpers and CLI helpers
are owner-only (0o600) and that values containing shell metacharacters do
not break the shell-sourceable env file produced by _sync_bird_env().

Companion to tests/test_config.py::test_save_creates_file_with_restricted_permissions —
the same threat-model claim ("Cookie/Token only stored locally, 600
permissions") covers these paths.
"""

import json
import os
import stat
import subprocess
import sys

import pytest

from agent_reach.cli import _configure_xhs_cookies
from agent_reach.cookie_extract import _sync_bird_env, _sync_xfetch_session


def _owner_only(path: str) -> bool:
    mode = os.stat(path).st_mode
    return not (mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH))


def _owner_only_dir(path: str) -> bool:
    mode = os.stat(path).st_mode
    return not (
        mode
        & (
            stat.S_IRGRP
            | stat.S_IWGRP
            | stat.S_IXGRP
            | stat.S_IROTH
            | stat.S_IWOTH
            | stat.S_IXOTH
        )
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX perm semantics only")
def test_sync_xfetch_session_writes_0600(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _sync_xfetch_session("auth_xxx", "ct0_yyy")
    session_path = tmp_path / ".config" / "xfetch" / "session.json"
    assert session_path.exists(), "expected ~/.config/xfetch/session.json"
    assert _owner_only_dir(str(session_path.parent)), "xfetch dir must be 0o700"
    assert _owner_only(str(session_path)), "session.json must be 0o600"
    # Round-trip the content so we know we didn't accidentally corrupt JSON.
    data = json.loads(session_path.read_text(encoding="utf-8"))
    assert data["authToken"] == "auth_xxx"
    assert data["ct0"] == "ct0_yyy"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX perm semantics only")
def test_sync_xfetch_session_tightens_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    session_path = tmp_path / ".config" / "xfetch" / "session.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text('{"authToken": "old"}', encoding="utf-8")
    os.chmod(session_path, 0o644)

    _sync_xfetch_session("auth_xxx", "ct0_yyy")

    assert _owner_only(str(session_path)), "existing session.json must be tightened"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX perm semantics only")
def test_sync_bird_env_writes_0600(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _sync_bird_env("auth_xxx", "ct0_yyy")
    env_path = tmp_path / ".config" / "bird" / "credentials.env"
    assert env_path.exists(), "expected ~/.config/bird/credentials.env"
    assert _owner_only_dir(str(env_path.parent)), "bird dir must be 0o700"
    assert _owner_only(str(env_path)), "credentials.env must be 0o600"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX perm semantics only")
def test_sync_bird_env_tightens_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    env_path = tmp_path / ".config" / "bird" / "credentials.env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("AUTH_TOKEN=old\n", encoding="utf-8")
    os.chmod(env_path, 0o644)

    _sync_bird_env("auth_xxx", "ct0_yyy")

    assert _owner_only(str(env_path)), "existing credentials.env must be tightened"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh needed for sourcing")
def test_sync_bird_env_quotes_shell_metachars(tmp_path, monkeypatch):
    """Tokens containing ", $, `, ; etc. must not break out of the assignment.

    Prior implementation used `f'AUTH_TOKEN="{auth_token}"'` which an attacker-
    controlled cookie containing a literal `"` could break out of, turning a
    later `source ~/.config/bird/credentials.env` into arbitrary shell.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    # Side-effect markers live under tmp_path (auto-cleaned by pytest) rather
    # than a shared absolute /tmp path — otherwise one vulnerable run leaves a
    # marker behind that fails every later run on the same machine/CI runner.
    pwn_auth = tmp_path / "pwn-auth"
    pwn_ct0 = tmp_path / "pwn-ct0"
    hostile_auth = f'inj"; touch {pwn_auth}; #'
    hostile_ct0 = f"ct0_$(touch {pwn_ct0})"
    _sync_bird_env(hostile_auth, hostile_ct0)
    env_path = tmp_path / ".config" / "bird" / "credentials.env"

    # Sourcing the file must NOT execute the injected payload. Read back the
    # exported values from a subshell instead — they should equal the originals.
    probe = (
        f". {env_path}; "
        f'printf "AUTH=%s\\nCT0=%s\\n" "$AUTH_TOKEN" "$CT0"'
    )
    result = subprocess.run(
        ["sh", "-c", probe],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    lines = dict(
        line.split("=", 1) for line in result.stdout.strip().splitlines() if "=" in line
    )
    assert lines["AUTH"] == hostile_auth, "auth_token round-trip broke — injection possible"
    assert lines["CT0"] == hostile_ct0, "ct0 round-trip broke — injection possible"
    # And no side-effect files materialised.
    assert not pwn_auth.exists()
    assert not pwn_ct0.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX perm semantics only")
def test_configure_xhs_cookies_tightens_local_fallback_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda name: None if name == "docker" else name)

    cookie_path = tmp_path / ".agent-reach" / "xhs-cookies.json"
    cookie_path.parent.mkdir()
    cookie_path.write_text("[]", encoding="utf-8")
    os.chmod(cookie_path, 0o644)

    _configure_xhs_cookies("web_session=xhs_secret")

    assert _owner_only_dir(str(cookie_path.parent)), "~/.agent-reach must be 0o700"
    assert _owner_only(str(cookie_path)), "existing xhs-cookies.json must be tightened"
    data = json.loads(cookie_path.read_text(encoding="utf-8"))
    assert data[0]["name"] == "web_session"
    assert data[0]["value"] == "xhs_secret"
