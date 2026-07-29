# -*- coding: utf-8 -*-
"""Regression tests for P0 CLI safety and configuration failures."""

from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

import agent_reach.cli as cli


class _MemoryConfig:
    def __init__(self, *args, **kwargs):
        self.data = {}
        self.read_only = kwargs.get("read_only", False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


def test_browser_cookie_import_requires_explicit_platform(monkeypatch):
    """A bare --from-browser must fail before any browser credential access."""
    import agent_reach.config as config_module
    import agent_reach.cookie_extract as cookie_extract

    monkeypatch.setattr(config_module, "Config", _MemoryConfig)
    monkeypatch.setattr(cli, "_configure_logging", lambda _verbose=False: None)
    monkeypatch.setattr(
        cookie_extract,
        "configure_from_browser",
        lambda *_args, **_kwargs: pytest.fail("browser cookie reader must not run"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["agent-reach", "configure", "--from-browser", "chrome"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2


def test_browser_cookie_import_passes_explicit_platform_and_profile(
    monkeypatch, capsys
):
    """The CLI forwards an allowed minimal-cookie platform and exact profile."""
    import agent_reach.config as config_module
    import agent_reach.cookie_extract as cookie_extract

    captured = {}

    def fake_configure(browser, config, **kwargs):
        captured.update(browser=browser, config=config, **kwargs)
        return [("Twitter/X", True, "saved to config.yaml")]

    monkeypatch.setattr(config_module, "Config", _MemoryConfig)
    monkeypatch.setattr(cli, "_configure_logging", lambda _verbose=False: None)
    monkeypatch.setattr(cookie_extract, "configure_from_browser", fake_configure)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent-reach",
            "configure",
            "--from-browser",
            "chrome",
            "--platform",
            "xueqiu",
            "--profile",
            "Profile 2",
        ],
    )

    cli.main()

    assert captured["browser"] == "chrome"
    assert captured["platform"] == "xueqiu"
    assert captured["profile"] == "Profile 2"
    assert "Cookies configured" in capsys.readouterr().out


def test_browser_cookie_import_without_cookie_exits_one(monkeypatch, capsys):
    """An unsuccessful browser import is a CLI failure, not a silent success."""
    import agent_reach.config as config_module
    import agent_reach.cookie_extract as cookie_extract

    monkeypatch.setattr(config_module, "Config", _MemoryConfig)
    monkeypatch.setattr(cli, "_configure_logging", lambda _verbose=False: None)
    monkeypatch.setattr(
        cookie_extract,
        "configure_from_browser",
        lambda *_args, **_kwargs: [
            ("Xueqiu", False, "No Xueqiu cookies found")
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent-reach",
            "configure",
            "--from-browser",
            "chrome",
            "--platform",
            "xueqiu",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert "No cookies found" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("platform", "manual_key"),
    [("twitter", "twitter-cookies"), ("xiaohongshu", "xhs-cookies")],
)
def test_browser_cookie_import_rejects_cookie_editor_only_platforms(
    monkeypatch, capsys, platform, manual_key
):
    """Twitter/XHS browser stores are never opened by the automatic importer."""
    import agent_reach.cookie_extract as cookie_extract

    monkeypatch.setattr(cli, "_configure_logging", lambda _verbose=False: None)
    monkeypatch.setattr(
        cookie_extract,
        "configure_from_browser",
        lambda *_args, **_kwargs: pytest.fail("browser cookie reader must not run"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent-reach",
            "configure",
            "--from-browser",
            "chrome",
            "--platform",
            platform,
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert manual_key in capsys.readouterr().err


def test_install_does_not_implicitly_read_browser_cookies(monkeypatch, tmp_path, capsys):
    """Installing a cookie-backed channel prints an explicit command instead."""
    import agent_reach.config as config_module
    import agent_reach.cookie_extract as cookie_extract

    monkeypatch.setattr(config_module, "Config", _MemoryConfig)
    monkeypatch.setattr(
        cli.os.path,
        "expanduser",
        lambda value: value.replace("~", str(tmp_path)),
    )
    monkeypatch.setattr(cli, "_install_system_deps", lambda: None)
    monkeypatch.setattr(cli, "_install_mcporter", lambda: None)
    monkeypatch.setattr(cli, "_install_twitter_deps", lambda: None)
    monkeypatch.setattr(cli, "_install_skill", lambda: None)
    monkeypatch.setattr(
        "agent_reach.doctor.check_all",
        lambda _config: {},
    )
    monkeypatch.setattr(
        "agent_reach.doctor.format_report",
        lambda _results: "report",
    )
    monkeypatch.setattr(
        cookie_extract,
        "configure_from_browser",
        lambda *_args, **_kwargs: pytest.fail("install must not read browser cookies"),
    )

    cli._cmd_install(
        Namespace(
            env="local",
            proxy="",
            safe=False,
            dry_run=False,
            channels="twitter",
        )
    )

    output = capsys.readouterr().out
    assert "configure twitter-cookies" in output
    assert "Importing cookies from browser" not in output


def test_install_rejects_unknown_channel_before_side_effects(
    monkeypatch, capsys
):
    """A typo in --channels fails before config or system installation starts."""
    import agent_reach.config as config_module

    monkeypatch.setattr(cli, "_configure_logging", lambda _verbose=False: None)
    monkeypatch.setattr(
        config_module,
        "Config",
        lambda *_args, **_kwargs: pytest.fail(
            "Config must not be constructed for an invalid channel"
        ),
    )
    monkeypatch.setattr(
        cli,
        "_install_system_deps",
        lambda: pytest.fail("system dependencies must not be installed"),
    )
    monkeypatch.setattr(
        cli.os,
        "makedirs",
        lambda *_args, **_kwargs: pytest.fail(
            "install directories must not be created"
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent-reach",
            "install",
            "--env",
            "local",
            "--channels",
            "twiter",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "twiter" in capsys.readouterr().err


@pytest.mark.parametrize("sync_legacy", [False, True])
def test_manual_twitter_cookie_legacy_copies_are_opt_in(
    monkeypatch, capsys, sync_legacy
):
    """The source-of-truth config is always written; legacy copies are optional."""
    import shutil

    import agent_reach.config as config_module
    import agent_reach.cookie_extract as cookie_extract

    calls = []
    config = _MemoryConfig()
    monkeypatch.setattr(config_module, "Config", lambda: config)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        cookie_extract,
        "_sync_xfetch_session",
        lambda auth, ct0: calls.append(("xfetch", auth, ct0)) or True,
    )
    monkeypatch.setattr(
        cookie_extract,
        "_sync_bird_env",
        lambda auth, ct0: calls.append(("bird", auth, ct0)) or True,
    )

    cli._cmd_configure(
        Namespace(
            from_browser=None,
            key="twitter-cookies",
            value=["auth-value", "ct0-value"],
            sync_legacy_twitter=sync_legacy,
        )
    )

    assert config.get("twitter_auth_token") == "auth-value"
    assert config.get("twitter_ct0") == "ct0-value"
    assert bool(calls) is sync_legacy
    output = capsys.readouterr().out
    assert ("Legacy copies written" in output) is sync_legacy


@pytest.mark.parametrize(
    ("xfetch_ok", "bird_ok", "written_count", "failed_count"),
    [
        (True, True, 2, 0),
        (True, False, 1, 1),
        (False, True, 1, 1),
        (False, False, 0, 2),
    ],
)
def test_legacy_twitter_sync_reports_only_confirmed_results(
    monkeypatch,
    capsys,
    xfetch_ok,
    bird_ok,
    written_count,
    failed_count,
):
    import shutil

    import agent_reach.config as config_module
    import agent_reach.cookie_extract as cookie_extract

    monkeypatch.setattr(config_module, "Config", _MemoryConfig)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        cookie_extract,
        "_sync_xfetch_session",
        lambda *_args: xfetch_ok,
    )
    monkeypatch.setattr(
        cookie_extract,
        "_sync_bird_env",
        lambda *_args: bird_ok,
    )

    cli._cmd_configure(
        Namespace(
            from_browser=None,
            key="twitter-cookies",
            value=["auth-value", "ct0-value"],
            sync_legacy_twitter=True,
        )
    )

    output = capsys.readouterr().out
    assert output.count("  written:") == written_count
    assert output.count("  failed:") == failed_count


def test_twitter_configure_never_runs_upstream_browser_fallback(
    monkeypatch, capsys
):
    import shutil

    import agent_reach.config as config_module

    monkeypatch.setattr(config_module, "Config", _MemoryConfig)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/twitter")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail(
            "configure must not execute twitter status"
        ),
    )

    cli._cmd_configure(
        Namespace(
            from_browser=None,
            key="twitter-cookies",
            value=["auth-value", "ct0-value"],
            sync_legacy_twitter=False,
        )
    )

    output = capsys.readouterr().out
    assert "已保存" in output
    assert "未实时验证" in output
    assert "Twitter access works" not in output


def test_doctor_never_installs_or_updates_skill(monkeypatch, capsys):
    """A diagnostic command is read-only and must not mutate agent instructions."""
    import agent_reach.config as config_module

    monkeypatch.setattr(config_module, "Config", _MemoryConfig)
    monkeypatch.setattr("agent_reach.doctor.check_all", lambda _config: {})
    monkeypatch.setattr("agent_reach.doctor.format_report", lambda _results: "report")
    monkeypatch.setattr(
        cli,
        "_install_skill",
        lambda *_args, **_kwargs: pytest.fail("doctor must not install skill"),
    )

    cli._cmd_doctor(Namespace(json=False))

    assert "report" in capsys.readouterr().out


def test_watch_uses_read_only_config(monkeypatch, capsys):
    """Scheduled diagnostics must enforce the same no-write boundary as doctor."""
    import agent_reach.config as config_module

    created = []

    class RecordingConfig(_MemoryConfig):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    class _Release:
        status_code = 200

        @staticmethod
        def json():
            return {"tag_name": "v0.0.0", "body": ""}

    monkeypatch.setattr(config_module, "Config", RecordingConfig)
    monkeypatch.setattr(
        "agent_reach.doctor.check_all",
        lambda _config: {
            "web": {
                "status": "ok",
                "name": "网页",
                "message": "可用",
                "tier": 0,
                "backends": ["Jina Reader"],
                "active_backend": "Jina Reader",
            }
        },
    )
    monkeypatch.setattr(
        cli,
        "_github_get_with_retry",
        lambda *_args, **_kwargs: (_Release(), None, 1),
    )

    cli._cmd_watch()

    assert len(created) == 1
    assert created[0].read_only is True
    assert "全部正常" in capsys.readouterr().out


def _docker_result(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def test_xhs_docker_cookie_copy_succeeds_without_local_os_binding_error(
    monkeypatch, capsys
):
    """The Docker branch must be able to unlink its temporary file."""
    calls = []

    def fake_which(name):
        if name == "docker":
            return "/usr/bin/docker"
        return None

    def fake_run(args, **_kwargs):
        calls.append(args)
        if args[1] == "ps":
            return _docker_result(args, stdout="xiaohongshu-mcp\n")
        if args[1:3] == ["exec", "xiaohongshu-mcp"]:
            return _docker_result(args, stdout="/app/data/cookies.json\n")
        return _docker_result(args)

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    cli._configure_xhs_cookies("web_session=xhs_secret")

    output = capsys.readouterr().out
    assert "Cookies written to xiaohongshu-mcp:/app/data/cookies.json" in output
    assert "cannot access local variable 'os'" not in output
    assert any(call[1] == "cp" for call in calls)


def test_xhs_docker_cookie_copy_always_removes_temporary_file(monkeypatch, capsys):
    """Failed docker cp must not leave a plaintext cookie file behind."""
    copied_from = []

    def fake_which(name):
        if name == "docker":
            return "/usr/bin/docker"
        return None

    def fake_run(args, **_kwargs):
        if args[1] == "ps":
            return _docker_result(args, stdout="xiaohongshu-mcp\n")
        if args[1:3] == ["exec", "xiaohongshu-mcp"]:
            return _docker_result(args, stdout="/app/data/cookies.json\n")
        if args[1] == "cp":
            copied_from.append(args[2])
            return _docker_result(args, returncode=1, stderr="copy failed")
        return _docker_result(args)

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    cli._configure_xhs_cookies("web_session=xhs_secret")

    assert copied_from
    assert not Path(copied_from[0]).exists()
    assert "Failed to copy cookies: copy failed" in capsys.readouterr().out


def test_system_install_uses_ytdlp_first_user_config(
    monkeypatch, tmp_path
):
    """Installer writes the first config directory that real yt-dlp reads."""
    import shutil

    import agent_reach.utils.paths as paths

    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setattr(
        cli.os.path,
        "expanduser",
        lambda value: str(tmp_path / ".legacy-config")
        if value == "~/.config/yt-dlp"
        else value.replace("~", str(tmp_path)),
    )
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: f"/usr/bin/{name}"
        if name in {"gh", "node", "npm", "yt-dlp"}
        else None,
    )

    def fake_run(args, **_kwargs):
        if args[-1:] == ["--version"] and args[0].endswith("yt-dlp"):
            return _docker_result(args, stdout="2026.07.04\n")
        return _docker_result(
            args,
            stdout="/tmp/npm-root\n"
            if args[1:3] == ["root", "-g"]
            else "",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    cli._install_system_deps()

    config_path = tmp_path / ".config" / "yt-dlp" / "config"
    assert config_path.read_text(encoding="utf-8") == "--js-runtimes node\n"
    assert not (tmp_path / ".legacy-config" / "config").exists()


@pytest.mark.parametrize(
    "yt_dlp_version",
    [None, "2025.10.22", "not-a-stable-version"],
)
def test_system_install_never_writes_unsupported_ytdlp_flag(
    monkeypatch, tmp_path, yt_dlp_version
):
    """A missing, old, or unknown yt-dlp must not receive a fatal option."""
    import shutil

    import agent_reach.utils.paths as paths

    monkeypatch.setattr(paths.sys, "platform", "darwin")
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME")

    def fake_which(name):
        if name in {"gh", "node", "npm"}:
            return f"/usr/bin/{name}"
        if name == "yt-dlp" and yt_dlp_version is not None:
            return "/usr/bin/yt-dlp"
        return None

    def fake_run(args, **_kwargs):
        if args[-1:] == ["--version"] and args[0].endswith("yt-dlp"):
            return _docker_result(args, stdout=f"{yt_dlp_version}\n")
        return _docker_result(
            args,
            stdout="/tmp/npm-root\n"
            if args[1:3] == ["root", "-g"]
            else "",
        )

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    cli._install_system_deps()

    config_path = tmp_path / ".config" / "yt-dlp" / "config"
    assert not config_path.exists()


def test_update_guide_preserves_ytdlp_default_extra():
    """Every documented upgrade path keeps yt-dlp's default/EJS dependencies."""
    guide = (
        Path(__file__).resolve().parents[1] / "docs" / "update.md"
    ).read_text(encoding="utf-8")
    update_line = next(
        line for line in guide.splitlines() if line.startswith("which yt-dlp")
    )

    assert update_line.count("yt-dlp[default]") == 3
    assert "pipx install --force 'yt-dlp[default]'" in update_line


def test_mcporter_install_adds_exa_to_home_scope(monkeypatch):
    """Installer config remains available across working directories."""
    import shutil

    calls = []

    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/usr/bin/mcporter" if name == "mcporter" else None,
    )

    def fake_run(args, **_kwargs):
        calls.append(args)
        if args == ["mcporter", "config", "list", "--json"]:
            return _docker_result(args, stdout='{"servers": []}')
        return _docker_result(args)

    monkeypatch.setattr(subprocess, "run", fake_run)

    cli._install_mcporter()

    assert [
        "mcporter",
        "config",
        "add",
        "exa",
        "https://mcp.exa.ai/mcp",
        "--scope",
        "home",
    ] in calls
    assert ["mcporter", "config", "list", "--json"] in calls


def test_mcporter_install_does_not_treat_metadata_as_exa_server(
    monkeypatch,
):
    """Only a server object's exact name may suppress Exa setup."""
    import json
    import shutil

    calls = []
    payload = {
        "servers": [
            {
                "name": "unrelated",
                "source": {"path": "/tmp/exa-project/mcporter.json"},
                "url": "https://example.test/?note=exa",
            }
        ]
    }

    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/usr/bin/mcporter" if name == "mcporter" else None,
    )

    def fake_run(args, **_kwargs):
        calls.append(args)
        if args == ["mcporter", "config", "list", "--json"]:
            return _docker_result(args, stdout=json.dumps(payload))
        return _docker_result(args)

    monkeypatch.setattr(subprocess, "run", fake_run)

    cli._install_mcporter()

    assert [
        "mcporter",
        "config",
        "add",
        "exa",
        "https://mcp.exa.ai/mcp",
        "--scope",
        "home",
    ] in calls


def test_server_xhs_install_never_recommends_qr_or_browser_extraction(
    monkeypatch, capsys
):
    """Project policy requires an explicit Cookie-Editor export for XHS."""
    monkeypatch.setattr(cli, "_detect_environment", lambda: "server")

    cli._install_xhs_deps()

    output = capsys.readouterr().out
    assert "Cookie-Editor" in output
    assert "configure xhs-cookies" in output
    assert "扫码" not in output
    assert "二维码" not in output


def test_configure_usage_does_not_recommend_blocked_twitter_browser_import(
    capsys,
):
    cli._cmd_configure(
        Namespace(
            from_browser=None,
            key=None,
            value=[],
            sync_legacy_twitter=False,
        )
    )

    output = capsys.readouterr().out
    assert "--platform xueqiu" in output
    assert "--platform twitter" not in output


def test_configure_missing_value_exits_one(monkeypatch, capsys):
    """A selected config key without a value must fail at the CLI boundary."""
    import agent_reach.config as config_module

    monkeypatch.setattr(config_module, "Config", _MemoryConfig)
    monkeypatch.setattr(cli, "_configure_logging", lambda _verbose=False: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["agent-reach", "configure", "github-token"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert "Missing value for github-token" in capsys.readouterr().out


def test_twitter_cookie_parse_failure_exits_one(monkeypatch, capsys):
    """Malformed Twitter cookie input must not produce a successful CLI status."""
    import agent_reach.config as config_module

    config = _MemoryConfig()
    monkeypatch.setattr(config_module, "Config", lambda: config)
    monkeypatch.setattr(cli, "_configure_logging", lambda _verbose=False: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["agent-reach", "configure", "twitter-cookies", "not-a-cookie"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert "Could not find auth_token and ct0" in capsys.readouterr().out
    assert config.data == {}


def test_profile_rejects_unsupported_browser_before_cookie_backend(
    monkeypatch, capsys
):
    import agent_reach.cookie_extract as cookie_extract

    monkeypatch.setattr(cli, "_configure_logging", lambda _verbose=False: None)
    monkeypatch.setattr(
        cookie_extract,
        "configure_from_browser",
        lambda *_args, **_kwargs: pytest.fail(
            "unsupported profile must fail before browser access"
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent-reach",
            "configure",
            "--from-browser",
            "firefox",
            "--platform",
            "xueqiu",
            "--profile",
            "default-release",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "Chrome/Edge/Brave" in capsys.readouterr().err


def test_missing_profile_is_clean_cli_error_without_traceback(
    monkeypatch, capsys
):
    import agent_reach.config as config_module
    import agent_reach.cookie_extract as cookie_extract

    monkeypatch.setattr(config_module, "Config", _MemoryConfig)
    monkeypatch.setattr(
        cookie_extract,
        "configure_from_browser",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError(
                "Profile 'secret-profile' not found for chrome; "
                "https://user:pass@example.test/?token=hidden"
            )
        ),
    )

    with pytest.raises(SystemExit) as exc:
        cli._cmd_configure(
            Namespace(
                from_browser="chrome",
                platform="xueqiu",
                profile="Missing",
                key=None,
                value=[],
                sync_legacy_twitter=False,
            )
        )

    error = capsys.readouterr().err
    assert exc.value.code == 2
    assert "Traceback" not in error
    assert "user:pass" not in error
    assert "hidden" not in error
    assert "***" in error


def test_install_dry_run_does_not_create_agent_reach_directory(
    isolated_home, monkeypatch
):
    monkeypatch.setattr(cli, "_install_system_deps_dryrun", lambda: None)

    cli._cmd_install(
        Namespace(
            env="local",
            proxy="",
            safe=False,
            dry_run=True,
            channels="",
        )
    )

    assert not (isolated_home / ".agent-reach").exists()


def test_uninstall_warns_about_opt_in_legacy_credential_copies(
    isolated_home, capsys
):
    xfetch = isolated_home / ".config" / "xfetch" / "session.json"
    bird = isolated_home / ".config" / "bird" / "credentials.env"
    xfetch.parent.mkdir(parents=True)
    bird.parent.mkdir(parents=True)
    xfetch.write_text("{}", encoding="utf-8")
    bird.write_text("AUTH_TOKEN=secret\n", encoding="utf-8")

    cli._cmd_uninstall(Namespace(dry_run=True, keep_config=False))

    output = capsys.readouterr().out
    normalized_output = output.replace("\\", "/")
    assert xfetch.as_posix() in normalized_output
    assert bird.as_posix() in normalized_output
    assert "不会自动删除" in output
    assert xfetch.exists()
    assert bird.exists()


def test_uninstall_preserves_mcporter_entries_without_agent_reach_provenance(
    isolated_home, monkeypatch, capsys
):
    """Names and endpoints alone do not prove Agent Reach owns an MCP entry."""
    calls = []
    payload = {
        "servers": [
            {
                "name": "exa",
                "source": {
                    "kind": "local",
                    "path": str(isolated_home / ".mcporter" / "mcporter.json"),
                },
                "baseUrl": "https://mcp.exa.ai/mcp",
            },
            {
                "name": "xiaohongshu",
                "source": {
                    "kind": "local",
                    "path": str(isolated_home / ".mcporter" / "mcporter.json"),
                },
                "baseUrl": "http://localhost:18060/mcp",
            },
        ]
    }

    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/mcporter" if name == "mcporter" else None,
    )

    def fake_run(args, **_kwargs):
        calls.append(args)
        return _docker_result(args, stdout=json.dumps(payload))

    monkeypatch.setattr(subprocess, "run", fake_run)

    cli._cmd_uninstall(Namespace(dry_run=False, keep_config=True))

    output = capsys.readouterr().out
    assert not any("remove" in call for call in calls)
    assert "来源无法证明" in output
