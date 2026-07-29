# -*- coding: utf-8 -*-
"""Dedicated tests for Substack's multi-backend discovery health check."""

from unittest.mock import Mock, patch

from agent_reach.backends.opencli import OpenCLIStatus
from agent_reach.channels.substack import SubstackChannel


def test_can_handle_matches_substack_hosts():
    channel = SubstackChannel()
    for url in [
        "https://substack.com/home",
        "https://www.substack.com/browse",
        "https://lenny.substack.com/p/some-post",
        "HTTPS://LENNY.SUBSTACK.COM/archive",
    ]:
        assert channel.can_handle(url) is True, url


def test_can_handle_rejects_non_substack():
    channel = SubstackChannel()
    for url in [
        "https://example.com/substack",
        "https://substack.com.evil.test/p/x",
        "https://stratechery.com/2026/post",  # custom domains → web channel
        "",
    ]:
        assert channel.can_handle(url) is False, url


def _opencli(**kwargs) -> OpenCLIStatus:
    return OpenCLIStatus(**kwargs)


def test_check_opencli_ready_is_ok_with_active_backend():
    ready = _opencli(installed=True, extension_connected=True, daemon_running=True)
    with patch("agent_reach.backends.opencli_status", return_value=ready):
        channel = SubstackChannel()
        status, message = channel.check()

    assert status == "ok"
    assert channel.active_backend == "OpenCLI"
    assert "opencli substack search" in message


def test_check_falls_back_to_exa_when_bridge_down():
    down = _opencli(installed=True, extension_connected=False, hint="bridge down")
    inspection = Mock(server_names={"exa"}, imports_unchecked=False)
    with patch("agent_reach.backends.opencli_status", return_value=down), patch(
        "shutil.which", return_value="/usr/local/bin/mcporter"
    ), patch(
        "agent_reach.channels.mcporter.inspect_mcporter_config",
        return_value=inspection,
    ):
        channel = SubstackChannel()
        status, message = channel.check()

    assert status == "ok"
    assert channel.active_backend == "Exa via mcporter"
    assert "降级" in message


def test_check_opencli_missing_and_exa_configured_uses_exa():
    inspection = Mock(server_names={"exa"}, imports_unchecked=False)
    with patch(
        "agent_reach.backends.opencli_status",
        return_value=_opencli(installed=False),
    ), patch("shutil.which", return_value="/usr/local/bin/mcporter"), patch(
        "agent_reach.channels.mcporter.inspect_mcporter_config",
        return_value=inspection,
    ):
        channel = SubstackChannel()
        status, _ = channel.check()

    assert status == "ok"
    assert channel.active_backend == "Exa via mcporter"


def test_check_nothing_installed_is_off_with_both_paths():
    with patch(
        "agent_reach.backends.opencli_status",
        return_value=_opencli(installed=False),
    ), patch("shutil.which", return_value=None):
        channel = SubstackChannel()
        status, message = channel.check()

    assert status == "off"
    assert channel.active_backend is None
    assert "--channels substack" in message
    assert "mcporter" in message


def test_check_opencli_installed_but_disconnected_warns_when_no_exa():
    down = _opencli(installed=True, extension_connected=False, hint="连接提示")
    with patch("agent_reach.backends.opencli_status", return_value=down), patch(
        "shutil.which", return_value=None
    ):
        channel = SubstackChannel()
        status, message = channel.check()

    assert status == "warn"
    assert channel.active_backend is None
    assert message == "连接提示"


def test_backend_override_prefers_exa(monkeypatch):
    """<channel>_backend config moves Exa to the front of the probe order."""
    channel = SubstackChannel()
    config = Mock()
    config.get = Mock(
        side_effect=lambda key: "Exa" if key == "substack_backend" else None
    )
    assert channel.ordered_backends(config)[0] == "Exa via mcporter"
