# -*- coding: utf-8 -*-
"""Tests for agent_reach.utils.paths remediation-command rendering."""

import agent_reach.utils.paths as paths


class TestRenderYtdlpFixCommand:
    def test_posix_command_is_a_single_line(self, monkeypatch, tmp_path):
        """The POSIX remediation is a copy-pasteable one-liner.

        Regression: the printf format string embedded an *actual* newline
        character instead of the shell escape ``\\n``, which split the command
        across two lines (line 1 ended with an unclosed ``printf '%s`` quote).
        """
        monkeypatch.setattr(paths.sys, "platform", "linux")
        monkeypatch.setattr(
            paths.Path, "home", classmethod(lambda cls: tmp_path)
        )

        cmd = paths.render_ytdlp_fix_command()

        # No embedded newline: the whole command stays on one line.
        assert "\n" not in cmd
        # printf must receive the literal two-character shell escape \n,
        # not a real newline, so the appended config line is terminated.
        assert "printf '%s\\n'" in cmd
        # The idempotency guard and the payload are both present.
        assert "grep -qxF -- '--js-runtimes node'" in cmd
        assert "--js-runtimes node" in cmd

    def test_windows_command_uses_powershell(self, monkeypatch, tmp_path):
        """Windows guidance stays PowerShell-based and unaffected by the fix."""
        monkeypatch.setattr(paths.sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))

        cmd = paths.render_ytdlp_fix_command()

        assert "Add-Content" in cmd
        assert "--js-runtimes node" in cmd
