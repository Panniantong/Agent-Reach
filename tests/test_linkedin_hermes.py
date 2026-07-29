# -*- coding: utf-8 -*-
"""LinkedIn doctor integration with Hermes-native MCP configuration."""

from agent_reach.channels.linkedin import LinkedInChannel


def _write_hermes_config(root, body):
    root.mkdir(parents=True, mode=0o700)
    path = root / "config.yaml"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)


def test_linkedin_check_detects_enabled_hermes_native_mcp(
    monkeypatch, tmp_path
):
    hermes_home = tmp_path / "hermes"
    _write_hermes_config(
        hermes_home,
        "mcp_servers:\n  linkedin:\n    command: uvx\n    enabled: true\n",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr("agent_reach.channels.linkedin.shutil.which", lambda _name: None)

    channel = LinkedInChannel()
    status, message = channel.check()

    assert status == "warn"
    assert "Hermes" in message
    assert "LinkedIn MCP" in message
    assert channel.active_backend is None


def test_linkedin_check_ignores_disabled_hermes_native_mcp(
    monkeypatch, tmp_path
):
    hermes_home = tmp_path / "hermes"
    _write_hermes_config(
        hermes_home,
        "mcp_servers:\n  linkedin:\n    command: uvx\n    enabled: false\n",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr("agent_reach.channels.linkedin.shutil.which", lambda _name: None)

    status, message = LinkedInChannel().check()

    assert status == "off"
    assert "需要" in message
