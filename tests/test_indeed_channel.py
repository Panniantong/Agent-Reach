# -*- coding: utf-8 -*-
"""Dedicated tests for the Indeed channel."""

from argparse import Namespace

from agent_reach import cli
from agent_reach.channels import get_channel
from agent_reach.channels.indeed import IndeedChannel


def _write_hermes_config(root, body):
    root.mkdir(parents=True, mode=0o700)
    path = root / "config.yaml"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)


def test_can_handle_matches_supported_indeed_hosts_and_rejects_lookalikes():
    channel = IndeedChannel()

    for url in (
        "https://www.indeed.com/viewjob?jk=abc",
        "https://dk.indeed.com/jobs?q=security",
        "https://uk.indeed.com/jobs?q=operations",
        "https://www.indeed.co.uk/viewjob?jk=abc",
    ):
        assert channel.can_handle(url), url

    for url in (
        "https://indeed.com.evil.test/jobs",
        "https://user:pass@indeed.com/jobs",
        "https://notindeed.com/jobs",
        "",
    ):
        assert not channel.can_handle(url), url


def test_check_detects_jobspy_in_hermes_native_mcp(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes"
    _write_hermes_config(
        hermes_home,
        "mcp_servers:\n  jobspy:\n    command: uvx\n    enabled: true\n",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr("agent_reach.channels.indeed.shutil.which", lambda _name: None)

    channel = IndeedChannel()
    status, message = channel.check()

    assert status == "warn"
    assert "Hermes" in message
    assert "JobSpy" in message
    assert channel.active_backend is None


def test_check_reports_setup_when_no_jobspy_mcp_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "missing"))
    monkeypatch.setattr("agent_reach.channels.indeed.shutil.which", lambda _name: None)

    channel = IndeedChannel()
    status, message = channel.check()

    assert status == "off"
    assert "JobSpy" in message
    assert "Jina Reader" in message
    assert channel.active_backend is None


def test_registry_contains_indeed_channel():
    channel = get_channel("indeed")

    assert isinstance(channel, IndeedChannel)


def test_install_accepts_indeed_as_a_manual_channel(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_install_system_deps_dryrun", lambda: None)

    cli._cmd_install(
        Namespace(
            env="local",
            proxy="",
            safe=False,
            dry_run=True,
            channels="indeed",
        )
    )

    output = capsys.readouterr().out
    assert "Would install optional channels: indeed" in output
