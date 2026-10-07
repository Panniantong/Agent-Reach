# -*- coding: utf-8 -*-
"""Install-flow tests: environment detection, safe/dry-run side-effect
isolation, channel expansion, and probe cache freshness.

These cover the installer paths that the rest of the suite exercises only
indirectly. The hard rules under test:

- ``--dry-run`` and safe mode must never create directories, write config,
  or run installers.
- ``--channels=all`` expands to exactly the supported set.
- Channel names are normalized (case, whitespace) before validation.
- ``probe_command`` results are reused within the TTL window and can be
  forced fresh via ``clear_probe_cache()``.
- Cookie-based configure paths print the account-ban risk warning.
"""

import os
import shutil
import subprocess
from argparse import Namespace
from unittest.mock import patch

import pytest

import agent_reach.cli as cli
import agent_reach.probe as probe
from agent_reach.config import Config


class TestDetectEnvironment:
    """_detect_environment() — local vs server classification."""

    def _stub_virt(self, monkeypatch, virt_output="none\n"):
        """Patch the real subprocess.run; _detect_environment's internal
        `import subprocess` resolves to the same module object."""
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(
                ["systemd-detect-virt"], 0, virt_output, ""
            ),
        )

    def test_local_when_no_indicators(self, monkeypatch):
        monkeypatch.delenv("SSH_CONNECTION", raising=False)
        monkeypatch.delenv("SSH_CLIENT", raising=False)
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setattr(cli.os.path, "exists", lambda _: False)
        self._stub_virt(monkeypatch)
        assert cli._detect_environment() == "local"

    def test_server_when_ssh_session(self, monkeypatch):
        monkeypatch.setenv("SSH_CONNECTION", "1.2.3.4 50000 5.6.7.8 22")
        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.setattr(cli.os.path, "exists", lambda _: False)
        self._stub_virt(monkeypatch)
        assert cli._detect_environment() == "server"

    def test_server_when_container_marker(self, monkeypatch):
        real_exists = os.path.exists

        def fake_exists(path):
            if path == "/.dockerenv":
                return True
            return real_exists(path)

        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.setattr(cli.os.path, "exists", fake_exists)
        self._stub_virt(monkeypatch)
        assert cli._detect_environment() == "server"

    def test_server_when_headless_plus_virt(self, monkeypatch):
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("SSH_CONNECTION", raising=False)
        monkeypatch.setattr(cli.os.path, "exists", lambda _: False)
        # headless (+1) + detected virt (+1) = 2 → server
        self._stub_virt(monkeypatch, virt_output="kvm\n")
        assert cli._detect_environment() == "server"

    def test_local_when_headless_but_no_other_indicators(self, monkeypatch):
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("SSH_CONNECTION", raising=False)
        monkeypatch.setattr(cli.os.path, "exists", lambda _: False)
        # headless alone (+1) < 2 → still local
        self._stub_virt(monkeypatch)
        assert cli._detect_environment() == "local"


class TestSafeAndDryRunSideEffects:
    """Safe/dry-run modes must be read-only."""

    def test_dry_run_never_creates_tools_dir(self, monkeypatch, capsys, tmp_path):
        """--dry-run must not create ~/.agent-reach/tools."""
        monkeypatch.setattr(cli, "_install_system_deps_dryrun", lambda: None)
        monkeypatch.setattr(cli, "_install_mcporter_safe", lambda: None)
        monkeypatch.setattr("agent_reach.doctor.check_all", lambda _config: {})
        monkeypatch.setattr("agent_reach.doctor.format_report", lambda _r: "report")

        cli._cmd_install(
            Namespace(
                env="local", proxy="", system=True, safe=False,
                dry_run=True, channels="",
            )
        )

        tools_dir = Config.CONFIG_DIR / "tools"
        assert not tools_dir.exists(), "dry-run must not create tools dir"

    def test_safe_mode_never_writes_config(self, monkeypatch, capsys, tmp_path):
        config_file = Config.CONFIG_DIR / "config.yaml"

        def fail_write(*args, **kwargs):
            pytest.fail("safe mode must not write config")

        monkeypatch.setattr(cli, "_install_system_deps_safe", lambda: None)
        monkeypatch.setattr(cli, "_install_mcporter_safe", lambda: None)
        monkeypatch.setattr(Config, "set", fail_write)
        monkeypatch.setattr("agent_reach.doctor.check_all", lambda _config: {})
        monkeypatch.setattr("agent_reach.doctor.format_report", lambda _r: "report")

        cli._cmd_install(
            Namespace(
                env="local", proxy="", system=False, safe=True,
                dry_run=False, channels="",
            )
        )

        assert not config_file.exists()
        assert "SAFE MODE" in capsys.readouterr().out

    def test_safe_mode_proxy_does_not_persist(self, monkeypatch, capsys):
        written = []

        def record_write(key, value):
            written.append((key, value))

        monkeypatch.setattr(cli, "_install_system_deps_safe", lambda: None)
        monkeypatch.setattr(cli, "_install_mcporter_safe", lambda: None)
        monkeypatch.setattr(Config, "set", record_write)
        monkeypatch.setattr("agent_reach.doctor.check_all", lambda _config: {})
        monkeypatch.setattr("agent_reach.doctor.format_report", lambda _r: "report")

        cli._cmd_install(
            Namespace(
                env="local", proxy="http://user:pass@127.0.0.1:8080",
                system=False, safe=True, dry_run=False, channels="",
            )
        )

        assert written == [], "safe mode must not persist a proxy"
        assert "Would save network proxy" in capsys.readouterr().out

    def test_safe_dep_check_never_runs_installers(self, monkeypatch, capsys):
        """_install_system_deps_safe only inspects, never executes installs."""
        calls = []
        monkeypatch.setattr(
            shutil, "which",
            lambda name: calls.append(name) or "/usr/bin/" + name,
        )

        cli._install_system_deps_safe()

        out = capsys.readouterr().out
        assert "no auto-install" in out
        assert "apt-get" not in out

    def test_dryrun_dep_check_never_runs_installers(self, monkeypatch, capsys):
        calls = []
        monkeypatch.setattr(
            shutil, "which",
            lambda name: calls.append(name) or None,
        )

        cli._install_system_deps_dryrun()

        out = capsys.readouterr().out
        assert "would install via" in out
        # The hint text may mention apt-get/brew as instructions; the
        # guarantee is that no install command is ever EXECUTED.
        assert "apt-get update" not in out

    def test_mcporter_safe_never_installs(self, monkeypatch, capsys):
        monkeypatch.setattr(shutil, "which", lambda _: None)
        cli._install_mcporter_safe()
        out = capsys.readouterr().out
        assert "To install: npm install -g mcporter" in out
        assert "npm install" not in out.replace("To install: npm install -g mcporter", "")


class TestChannelExpansion:
    """--channels parsing, normalization, and validation (behavioral)."""

    def _install_all_harness(self, monkeypatch, capsys):
        """Run _cmd_install with --channels=all; record which installers ran.

        Mirrors the real CHANNEL_INSTALLERS mapping inside _cmd_install:
        xiaohongshu → _install_xhs_deps; facebook/instagram/opencli all
        route to _install_opencli_deps (the dedup under test).
        """
        ran = []

        def record(channel):
            def installer():
                ran.append(channel)
                return True
            return installer

        mapping = {
            "twitter": "_install_twitter_deps",
            "xiaoyuzhou": "_install_xiaoyuzhou_deps",
            "xiaohongshu": "_install_xhs_deps",
            "reddit": "_install_reddit_deps",
            "facebook": "_install_opencli_deps",
            "instagram": "_install_opencli_deps",
            "bilibili": "_install_bili_deps",
            "opencli": "_install_opencli_deps",
        }
        for channel, func_name in mapping.items():
            monkeypatch.setattr(cli, func_name, record(channel))
        monkeypatch.setattr(cli, "_install_system_deps", lambda: True)
        monkeypatch.setattr(cli, "_install_mcporter", lambda: True)
        monkeypatch.setattr(cli, "_install_skill", lambda: True)
        monkeypatch.setattr("agent_reach.doctor.check_all", lambda _config: {})
        monkeypatch.setattr("agent_reach.doctor.format_report", lambda _r: "report")
        return ran

    def test_all_expands_to_supported_set(self, monkeypatch, capsys):
        ran = self._install_all_harness(monkeypatch, capsys)
        cli._cmd_install(
            Namespace(
                env="local", proxy="", system=True, safe=False,
                dry_run=False, channels="all",
            )
        )
        expected = {
            "twitter", "xiaoyuzhou", "xiaohongshu", "reddit",
            "opencli", "bilibili",
            # xueqiu/linkedin are cookie/manual-only — no installer stubs,
            # so "all" must NOT try to run a fake installer for them.
        }
        assert set(ran) == expected

    def test_channel_names_normalized_case_and_whitespace(self, monkeypatch, capsys):
        ran = self._install_all_harness(monkeypatch, capsys)
        cli._cmd_install(
            Namespace(
                env="local", proxy="", system=True, safe=False,
                dry_run=False, channels="Twitter,  BILIBILI ,REDDIT",
            )
        )
        assert sorted(ran) == ["bilibili", "reddit", "twitter"]

    def test_unknown_channel_rejected(self, monkeypatch, capsys):
        import agent_reach.config as config_module

        monkeypatch.setattr(cli, "_configure_logging", lambda _v=False: None)
        monkeypatch.setattr(
            config_module,
            "Config",
            lambda *_a, **_k: pytest.fail("Config must not be built for invalid channel"),
        )
        with patch("sys.argv", ["agent-reach", "install", "--env", "local", "--channels", "twiiter"]):
            with pytest.raises(SystemExit) as exc:
                cli.main()
        assert exc.value.code == 2
        assert "twiiter" in capsys.readouterr().err

    def test_installer_dedup_runs_each_once(self, monkeypatch, capsys):
        """facebook/instagram/opencli share one installer; must run once."""
        ran = []
        monkeypatch.setattr(cli, "_install_opencli_deps", lambda: ran.append("opencli") or True)
        monkeypatch.setattr(cli, "_install_system_deps", lambda: True)
        monkeypatch.setattr(cli, "_install_mcporter", lambda: True)
        monkeypatch.setattr(cli, "_install_skill", lambda: True)
        monkeypatch.setattr("agent_reach.doctor.check_all", lambda _config: {})
        monkeypatch.setattr("agent_reach.doctor.format_report", lambda _r: "report")

        cli._cmd_install(
            Namespace(
                env="local", proxy="", system=True, safe=False,
                dry_run=False, channels="facebook,instagram,opencli",
            )
        )
        assert ran == ["opencli"]


class TestProbeCacheFreshness:
    """probe_command caching: TTL reuse, forced refresh, key isolation."""

    def _stub_probe_run(self, monkeypatch, calls):
        """Stub subprocess.run used inside probe._run_once; records calls."""
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "v1", "")
        monkeypatch.setattr(subprocess, "run", fake_run)

    def test_second_probe_within_ttl_is_cached(self, monkeypatch):
        calls = []
        probe._PROBE_CACHE.clear()
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/fake-tool")
        self._stub_probe_run(monkeypatch, calls)

        r1 = probe.probe_command("fake-tool", ttl=60)
        r2 = probe.probe_command("fake-tool", ttl=60)
        assert r1.ok and r2.ok
        assert len(calls) == 1, "second probe should hit the cache"

    def test_expired_ttl_reprobes(self, monkeypatch):
        calls = []
        probe._PROBE_CACHE.clear()
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/fake-tool")
        self._stub_probe_run(monkeypatch, calls)

        probe.probe_command("fake-tool", ttl=0.01)  # caches with tiny TTL
        probe._PROBE_CACHE.clear()  # explicit invalidation
        probe.probe_command("fake-tool", ttl=60)

        assert len(calls) == 2

    def test_use_cache_false_forces_reprobe(self, monkeypatch):
        calls = []
        probe._PROBE_CACHE.clear()
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/fake-tool")
        self._stub_probe_run(monkeypatch, calls)

        probe.probe_command("fake-tool", ttl=60)
        probe.probe_command("fake-tool", ttl=60, use_cache=False)
        assert len(calls) == 2

    def test_cache_key_includes_args_and_env(self, monkeypatch):
        calls = []
        probe._PROBE_CACHE.clear()
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/fake-tool")
        self._stub_probe_run(monkeypatch, calls)

        probe.probe_command("fake-tool", args=("--version",), ttl=60)
        probe.probe_command("fake-tool", args=("--help",), ttl=60)
        probe.probe_command("fake-tool", args=("--version",), env={"A": "1"}, ttl=60)
        assert len(calls) == 3

    def test_clear_probe_cache_resets(self, monkeypatch):
        calls = []
        probe._PROBE_CACHE.clear()
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/fake-tool")
        self._stub_probe_run(monkeypatch, calls)

        probe.probe_command("fake-tool", ttl=60)
        probe.clear_probe_cache()
        probe.probe_command("fake-tool", ttl=60)
        assert len(calls) == 2

    def test_missing_binary_not_cached_but_fast(self, monkeypatch):
        """A missing binary short-circuits; which() is called each time."""
        probe._PROBE_CACHE.clear()
        monkeypatch.setattr(shutil, "which", lambda _: None)
        result = probe.probe_command("definitely-not-installed", ttl=60)
        assert result.status == "missing"
        assert not result.ok


class TestDoctorRefresh:
    def test_doctor_refresh_clears_probe_cache(self, monkeypatch, capsys):
        cleared = []
        monkeypatch.setattr(
            probe, "clear_probe_cache", lambda: cleared.append(True),
        )
        monkeypatch.setattr(Config, "CONFIG_DIR", Config.CONFIG_DIR)
        monkeypatch.setattr(
            "agent_reach.doctor.check_all",
            lambda _config: {},
        )
        monkeypatch.setattr("agent_reach.doctor.format_report", lambda _r: "report")

        cli._cmd_doctor(Namespace(json=False, refresh=True))
        assert cleared == [True]

    def test_doctor_without_refresh_keeps_cache(self, monkeypatch, capsys):
        cleared = []
        monkeypatch.setattr(
            probe, "clear_probe_cache", lambda: cleared.append(True),
        )
        monkeypatch.setattr(
            "agent_reach.doctor.check_all",
            lambda _config: {},
        )
        monkeypatch.setattr("agent_reach.doctor.format_report", lambda _r: "report")

        cli._cmd_doctor(Namespace(json=False, refresh=False))
        assert cleared == []


class TestCookieBanRiskWarning:
    """Weakness #2: cookie configure and doctor must surface the ban risk."""

    def test_warn_cookie_ban_risk_prints_targeted_warning(self, capsys):
        cli._warn_cookie_ban_risk("Twitter/X")
        out = capsys.readouterr().out
        assert "封号风险" in out
        assert "throwaway" in out
        assert "Twitter/X" in out

    def test_configure_twitter_cookies_warns(self, monkeypatch, capsys, tmp_path):
        state = {"set": []}

        class FakeConfig:
            CONFIG_DIR = Config.CONFIG_DIR
            CONFIG_FILE = Config.CONFIG_FILE

            def __init__(self, *a, **k):
                pass

            def set(self, key, value):
                state["set"].append((key, value))

        import agent_reach.config as config_module
        monkeypatch.setattr(config_module, "Config", FakeConfig)

        from agent_reach.cli import _cmd_configure
        args = Namespace(
            from_browser=None, platform=None, profile=None,
            key="twitter-cookies", value=["auth_token=abc123", "ct0=xyz789"],
            read_stdin=False, sync_legacy_twitter=False,
        )
        _cmd_configure(args)

        out = capsys.readouterr().out
        assert "封号风险" in out
        assert ("twitter_auth_token", "abc123") in state["set"]
        assert ("twitter_ct0", "xyz789") in state["set"]
