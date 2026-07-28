# -*- coding: utf-8 -*-
"""Regression guards for test-suite and Doctor filesystem isolation."""

import os
from argparse import Namespace
from pathlib import Path

import agent_reach.cli as cli
from agent_reach.config import Config


def test_runtime_home_and_config_are_inside_test_sandbox(isolated_home):
    assert Path.home() == isolated_home
    assert Path(os.path.expanduser("~")) == isolated_home
    assert Config.CONFIG_DIR.is_relative_to(isolated_home)
    assert Config.CONFIG_FILE.is_relative_to(isolated_home)


def test_doctor_leaves_sandbox_home_unchanged(
    isolated_home, monkeypatch, capsys
):
    """If Doctor is truly read-only, even the sandbox remains empty."""
    monkeypatch.setattr("agent_reach.doctor.check_all", lambda config: {})
    monkeypatch.setattr("agent_reach.doctor.format_report", lambda results: "report")
    monkeypatch.setattr(
        cli,
        "_install_skill",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("doctor must not install skills")
        ),
    )

    cli._cmd_doctor(Namespace(json=False))

    assert capsys.readouterr().out.strip() == "report"
    assert list(isolated_home.iterdir()) == []
