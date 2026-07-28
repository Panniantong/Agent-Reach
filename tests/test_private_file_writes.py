"""Security regressions for local credential and tool configuration writes."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from argparse import Namespace

import pytest

from agent_reach import cli
from agent_reach.cookie_extract import _sync_bird_env, _sync_xfetch_session
from agent_reach.utils import paths


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
def test_atomic_private_text_write_is_0600(tmp_path):
    target = tmp_path / "private" / "secret.txt"

    paths.atomic_write_private_text(target, "secret")

    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700


def test_atomic_private_text_write_preserves_old_file_on_replace_failure(
    tmp_path, monkeypatch
):
    target = tmp_path / "private" / "secret.txt"
    target.parent.mkdir()
    target.write_text("keep-old", encoding="utf-8")

    def fail_replace(*_args, **_kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(paths.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failure"):
        paths.atomic_write_private_text(target, "new-secret")

    assert target.read_text(encoding="utf-8") == "keep-old"
    assert list(target.parent.glob(".secret.txt.*.tmp")) == []


def test_legacy_xfetch_sync_refuses_target_symlink(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    session_path = tmp_path / ".config" / "xfetch" / "session.json"
    session_path.parent.mkdir(parents=True)
    victim = tmp_path / "victim.json"
    victim.write_text('{"keep": "unchanged"}', encoding="utf-8")
    try:
        session_path.symlink_to(victim)
    except OSError:
        pytest.skip("symlinks are not supported on this platform")

    assert _sync_xfetch_session("new-auth", "new-ct0") is False
    assert victim.read_text(encoding="utf-8") == '{"keep": "unchanged"}'
    assert session_path.is_symlink()


def test_legacy_xfetch_sync_refuses_parent_symlink(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    victim_dir = tmp_path / "victim-dir"
    victim_dir.mkdir()
    xfetch_dir = config_dir / "xfetch"
    try:
        xfetch_dir.symlink_to(victim_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not supported on this platform")

    assert _sync_xfetch_session("new-auth", "new-ct0") is False
    assert not (victim_dir / "session.json").exists()
    assert xfetch_dir.is_symlink()


def test_legacy_xfetch_sync_refuses_ancestor_symlink(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    victim_dir = tmp_path / "victim-config"
    victim_dir.mkdir()
    config_dir = tmp_path / ".config"
    try:
        config_dir.symlink_to(victim_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not supported on this platform")

    assert _sync_xfetch_session("new-auth", "new-ct0") is False
    assert list(victim_dir.iterdir()) == []
    assert config_dir.is_symlink()


def test_legacy_xfetch_sync_refuses_oversized_existing_session(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    session_path = tmp_path / ".config" / "xfetch" / "session.json"
    session_path.parent.mkdir(parents=True)
    previous = json.dumps({"untrusted": "x" * (1024 * 1024)})
    session_path.write_text(previous, encoding="utf-8")

    assert _sync_xfetch_session("new-auth", "new-ct0") is False
    assert session_path.read_text(encoding="utf-8") == previous


def test_legacy_bird_sync_refuses_target_symlink(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    env_path = tmp_path / ".config" / "bird" / "credentials.env"
    env_path.parent.mkdir(parents=True)
    victim = tmp_path / "victim.env"
    victim.write_text("KEEP=unchanged\n", encoding="utf-8")
    try:
        env_path.symlink_to(victim)
    except OSError:
        pytest.skip("symlinks are not supported on this platform")

    assert _sync_bird_env("new-auth", "new-ct0") is False
    assert victim.read_text(encoding="utf-8") == "KEEP=unchanged\n"
    assert env_path.is_symlink()


def test_xhs_cookie_editor_json_ignores_non_xhs_domains(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda name: None)
    exported = [
        {
            "name": "web_session",
            "value": "valid-root",
            "domain": ".xiaohongshu.com",
            "path": "/",
        },
        {
            "name": "a1",
            "value": "valid-subdomain",
            "domain": "www.xiaohongshu.com",
            "path": "/",
        },
        {
            "name": "foreign",
            "value": "must-not-persist",
            "domain": ".example.com",
            "path": "/",
        },
        {
            "name": "lookalike",
            "value": "must-not-persist",
            "domain": ".notxiaohongshu.com",
            "path": "/",
        },
    ]

    cli._configure_xhs_cookies(json.dumps(exported))

    cookie_path = tmp_path / ".agent-reach" / "xhs-cookies.json"
    saved = json.loads(cookie_path.read_text(encoding="utf-8"))
    assert [cookie["name"] for cookie in saved] == ["web_session", "a1"]
    output = capsys.readouterr().out
    assert "忽略" in output
    assert "2" in output


def test_xhs_cookie_editor_json_fails_without_valid_xhs_cookie(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "shutil.which",
        lambda name: pytest.fail("invalid cookies must fail before tool lookup"),
    )
    exported = [
        {
            "name": "session",
            "value": "foreign",
            "domain": ".example.com",
        },
        {
            "name": "lookalike",
            "value": "foreign",
            "domain": ".xiaohongshu.com.evil.test",
        },
    ]

    monkeypatch.setattr("agent_reach.config.Config", lambda: object())
    with pytest.raises(SystemExit) as exc:
        cli._cmd_configure(
            Namespace(
                from_browser=None,
                key="xhs-cookies",
                value=[json.dumps(exported)],
                sync_legacy_twitter=False,
            )
        )

    assert exc.value.code == 1
    assert not (tmp_path / ".agent-reach" / "xhs-cookies.json").exists()
    output = capsys.readouterr().out
    assert "没有有效的 xiaohongshu.com" in output


def test_xhs_local_fallback_refuses_target_symlink(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda name: None)
    cookie_path = tmp_path / ".agent-reach" / "xhs-cookies.json"
    cookie_path.parent.mkdir()
    victim = tmp_path / "victim.json"
    victim.write_text('{"keep": "unchanged"}', encoding="utf-8")
    try:
        cookie_path.symlink_to(victim)
    except OSError:
        pytest.skip("symlinks are not supported on this platform")

    result = cli._configure_xhs_cookies("web_session=xhs-secret")

    assert result is False
    assert victim.read_text(encoding="utf-8") == '{"keep": "unchanged"}'
    assert cookie_path.is_symlink()
    assert "Could not save cookies" in capsys.readouterr().out


def test_xhs_docker_success_via_configure_command_does_not_exit(
    monkeypatch, capsys
):
    monkeypatch.setattr("agent_reach.config.Config", lambda: object())
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )

    def fake_run(args, **_kwargs):
        if args[1] == "ps":
            return subprocess.CompletedProcess(
                args, 0, stdout="xiaohongshu-mcp\n", stderr=""
            )
        if args[1:3] == ["exec", "xiaohongshu-mcp"]:
            return subprocess.CompletedProcess(
                args, 0, stdout="/app/data/cookies.json\n", stderr=""
            )
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    cli._cmd_configure(
        Namespace(
            from_browser=None,
            key="xhs-cookies",
            value=["web_session=xhs-secret"],
            sync_legacy_twitter=False,
        )
    )

    assert "Cookies written to" in capsys.readouterr().out


def test_xhs_docker_failure_via_configure_command_exits_one(
    monkeypatch, capsys
):
    monkeypatch.setattr("agent_reach.config.Config", lambda: object())
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )

    def fake_run(args, **_kwargs):
        if args[1] == "ps":
            return subprocess.CompletedProcess(
                args, 0, stdout="xiaohongshu-mcp\n", stderr=""
            )
        if args[1:3] == ["exec", "xiaohongshu-mcp"]:
            return subprocess.CompletedProcess(
                args, 0, stdout="/app/data/cookies.json\n", stderr=""
            )
        if args[1] == "cp":
            return subprocess.CompletedProcess(
                args, 1, stdout="", stderr="copy failed"
            )
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
        cli._cmd_configure(
            Namespace(
                from_browser=None,
                key="xhs-cookies",
                value=["web_session=xhs-secret"],
                sync_legacy_twitter=False,
            )
        )

    assert exc.value.code == 1
    assert "Failed to copy cookies" in capsys.readouterr().out


def test_ytdlp_config_write_refuses_target_symlink(
    tmp_path, monkeypatch, capsys
):
    import shutil

    import agent_reach.utils.paths as paths

    monkeypatch.setattr(paths.sys, "platform", "darwin")
    monkeypatch.setattr(
        paths.Path,
        "home",
        classmethod(lambda cls: tmp_path),
    )
    monkeypatch.delenv("XDG_CONFIG_HOME")
    config_path = tmp_path / ".config" / "yt-dlp" / "config"
    config_path.parent.mkdir(parents=True)
    victim = tmp_path / "victim.conf"
    victim.write_text("# keep unchanged\n", encoding="utf-8")
    try:
        config_path.symlink_to(victim)
    except OSError:
        pytest.skip("symlinks are not supported on this platform")

    def fake_which(name):
        if name in {"gh", "node", "npm", "yt-dlp"}:
            return f"/usr/bin/{name}"
        return None

    def fake_run(args, **_kwargs):
        if args[-1:] == ["--version"] and args[0].endswith("yt-dlp"):
            return subprocess.CompletedProcess(
                args, 0, stdout="2026.07.04\n", stderr=""
            )
        stdout = "/tmp/npm-root\n" if args[1:3] == ["root", "-g"] else ""
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    cli._install_system_deps()

    assert victim.read_text(encoding="utf-8") == "# keep unchanged\n"
    assert config_path.is_symlink()
    assert "Could not configure yt-dlp JS runtime" in capsys.readouterr().out


def test_transcribe_cli_scrubs_credentials_from_errors(
    monkeypatch, capsys
):
    import agent_reach.transcribe as transcribe_module

    secret_url = (
        "https://alice:super-secret@example.test/audio"
        "?access_token=hidden-token"
    )

    def fail_transcribe(*_args, **_kwargs):
        raise transcribe_module.TranscribeError(
            f"yt-dlp failed for {secret_url}"
        )

    monkeypatch.setattr(transcribe_module, "transcribe", fail_transcribe)

    with pytest.raises(SystemExit) as exc:
        cli._cmd_transcribe(
            Namespace(
                source=secret_url,
                provider="auto",
                output=None,
            )
        )

    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "alice:super-secret" not in output
    assert "hidden-token" not in output
    assert "***" in output


def test_safe_install_with_proxy_makes_no_persistent_writes(
    isolated_home, monkeypatch, capsys
):
    observed_configs = []
    skill_calls = []

    monkeypatch.setattr(cli, "_install_system_deps_safe", lambda: None)
    monkeypatch.setattr(cli, "_install_mcporter_safe", lambda: None)
    monkeypatch.setattr(
        "agent_reach.doctor.check_all",
        lambda config: observed_configs.append(config) or {},
    )
    monkeypatch.setattr(
        "agent_reach.doctor.format_report",
        lambda _results: "report",
    )
    monkeypatch.setattr(
        cli,
        "_install_skill",
        lambda: skill_calls.append("installed"),
    )

    cli._cmd_install(
        Namespace(
            env="local",
            proxy="http://user:pass@proxy.example:8080",
            safe=True,
            dry_run=False,
            channels="twitter",
        )
    )

    assert len(observed_configs) == 1
    assert observed_configs[0].read_only is True
    assert skill_calls == []
    assert not (isolated_home / ".agent-reach").exists()
    assert not (isolated_home / ".agent-reach" / "tools").exists()
    assert not (isolated_home / ".openclaw" / "skills" / "agent-reach").exists()
    assert not (isolated_home / ".claude" / "skills" / "agent-reach").exists()
    assert not (isolated_home / ".agents" / "skills" / "agent-reach").exists()
    output = capsys.readouterr().out
    assert "SAFE MODE" in output
    assert "Would save network proxy" in output
