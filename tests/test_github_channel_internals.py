# -*- coding: utf-8 -*-
"""Unit tests for the GitHub channel's credential-detection internals.

Covers the pure helper functions in agent_reach.channels.github that
decide where gh's hosts.yml lives, whether saved gh credentials are
present, and whether explicit credentials were provided. These helpers
gate the doctor/check output but previously had no direct coverage.
"""

import os
from pathlib import Path

import pytest

import agent_reach.channels.github as github
from agent_reach.probe import ProbeResult


def norm(path) -> str:
    """Normalize a path for cross-platform comparison."""
    return str(path).replace("\\", "/")


class TestGhHostsPath:
    def test_gh_config_dir_override_wins(self, monkeypatch):
        monkeypatch.setenv("GH_CONFIG_DIR", "~/custom-gh")
        monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg")
        result = norm(github._gh_hosts_path())
        assert result.endswith("custom-gh/hosts.yml")
        assert "xdg" not in result

    def test_xdg_config_home_used_without_override(self, monkeypatch):
        monkeypatch.delenv("GH_CONFIG_DIR", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg")
        assert norm(github._gh_hosts_path()).endswith("xdg/gh/hosts.yml")

    def test_windows_appdata_used(self, monkeypatch):
        monkeypatch.delenv("GH_CONFIG_DIR", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("APPDATA", r"C:\Users\ghuser\AppData\Roaming")
        assert norm(github._gh_hosts_path()) == norm(
            r"C:\Users\ghuser\AppData\Roaming\GitHub CLI\hosts.yml"
        )

    def test_home_fallback_when_no_env_hints(self, monkeypatch):
        monkeypatch.delenv("GH_CONFIG_DIR", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setattr(
            Path, "home", staticmethod(lambda: Path("C:/home/ghuser"))
        )
        assert norm(github._gh_hosts_path()).endswith(".config/gh/hosts.yml")


class TestSavedGithubHostConfigured:
    @pytest.fixture
    def hosts(self, tmp_path, monkeypatch):
        path = tmp_path / "hosts.yml"
        monkeypatch.setattr(github, "_gh_hosts_path", lambda: path)

        def set_payload(payload):
            if payload is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_text(payload, encoding="utf-8")
            return path

        return set_payload

    def test_missing_hosts_file_reports_unconfigured(self, hosts):
        hosts(None)
        assert github._saved_github_host_configured() is False

    def test_invalid_yaml_raises_config_error(self, hosts):
        hosts("[this is not: valid yaml\n  - broken")
        with pytest.raises(github.GitHubConfigError):
            github._saved_github_host_configured()

    def test_non_dict_top_level_raises_config_error(self, hosts):
        hosts("- just\n- a\n- list")
        with pytest.raises(github.GitHubConfigError):
            github._saved_github_host_configured()

    def test_empty_payload_reports_unconfigured(self, hosts):
        hosts("")
        assert github._saved_github_host_configured() is False

    def test_missing_github_com_key_reports_unconfigured(self, hosts):
        hosts("gitlab.com:\n  user: alice\n")
        assert github._saved_github_host_configured() is False

    def test_github_com_entry_not_a_dict_raises(self, hosts):
        hosts("github.com: just-a-string\n")
        with pytest.raises(github.GitHubConfigError):
            github._saved_github_host_configured()

    def test_users_entry_not_a_dict_raises(self, hosts):
        hosts("github.com:\n  users: not-a-dict\n")
        with pytest.raises(github.GitHubConfigError):
            github._saved_github_host_configured()

    def test_oauth_token_counts_as_configured(self, hosts):
        hosts("github.com:\n  oauth_token: gho_abc\n")
        assert github._saved_github_host_configured() is True

    def test_user_only_counts_as_configured(self, hosts):
        hosts("github.com:\n  user: alice\n")
        assert github._saved_github_host_configured() is True

    def test_users_dict_counts_as_configured(self, hosts):
        hosts("github.com:\n  users:\n    alice:\n      oauth_token: gho_abc\n")
        assert github._saved_github_host_configured() is True

    def test_empty_github_com_entry_reports_unconfigured(self, hosts):
        hosts("github.com: {}\n")
        assert github._saved_github_host_configured() is False


class TestExplicitGithubCredentials:
    def test_gh_token_env_wins(self, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "gho_env")
        assert github._explicit_github_credentials(None) is True

    def test_github_token_env_wins(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "gho_env")
        assert github._explicit_github_credentials(None) is True

    def test_config_token_counts(self, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert github._explicit_github_credentials({"github_token": "gho_cfg"}) is True

    def test_no_credentials_anywhere(self, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert github._explicit_github_credentials(None) is False
        assert github._explicit_github_credentials({}) is False

    def test_unreadable_config_raises(self):
        class ExplodingConfig(dict):
            def get(self, key, default=None):
                raise OSError("boom")

        with pytest.raises(github.GitHubConfigError):
            github._explicit_github_credentials(ExplodingConfig())


class TestCheckClassifiesCredentialStates:
    """Check() maps credential detection to doctor-visible status lines."""

    @pytest.fixture(autouse=True)
    def gh_probe_ok(self, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.probe.probe_command",
            lambda *args, **kwargs: ProbeResult("ok", output="gh version 2.92.0"),
        )

    def test_explicit_credentials_are_verified_ok(self, monkeypatch):
        monkeypatch.setattr(
            github, "_explicit_github_credentials", lambda config: True
        )
        monkeypatch.setattr(github, "_saved_github_host_configured", lambda: False)
        channel = github.GitHubChannel()
        status, message = channel.check(config={"github_token": "gho_cfg"})
        assert status == "warn"
        assert "gh CLI" in message

    def test_saved_credentials_are_verified_ok(self, monkeypatch):
        monkeypatch.setattr(
            github, "_explicit_github_credentials", lambda config: False
        )
        monkeypatch.setattr(github, "_saved_github_host_configured", lambda: True)
        channel = github.GitHubChannel()
        status, message = channel.check(config=None)
        assert status == "warn"
        assert "gh CLI" in message

    def test_no_credentials_recommend_auth_login(self, monkeypatch):
        monkeypatch.setattr(
            github, "_explicit_github_credentials", lambda config: False
        )
        monkeypatch.setattr(github, "_saved_github_host_configured", lambda: False)
        channel = github.GitHubChannel()
        status, message = channel.check(config=None)
        assert status == "warn"
        assert "gh auth login" in message
