# -*- coding: utf-8 -*-
"""Dedicated tests for the ``linkedin`` channel.

LinkedIn routes through mcporter + linkedin-scraper-mcp and its ``check()``
walks five distinct outcomes: mcporter missing (off, Jina Reader fallback
hint), unreadable mcporter config (error), a LinkedIn MCP server present in
config (warn — Doctor refuses to claim usability without a live probe),
editor imports left unexpanded (warn — credential-read boundary), and
mcporter installed but LinkedIn unconfigured (off with the exact add
command). ``inspect_mcporter_config`` and ``shutil.which`` are stubbed so
every branch runs offline. Follow-up to #331 — extends dedicated channel
coverage after rss (#360), github (#361), web (#363), reddit (#364),
xueqiu (#365), v2ex (#366) and youtube (#367).
"""

from unittest.mock import patch

from agent_reach.channels import linkedin as li
from agent_reach.channels.linkedin import LinkedInChannel
from agent_reach.channels.mcporter import (
    McporterConfigError,
    McporterConfigInspection,
)


def _inspection(names=(), imports_unchecked=False):
    return McporterConfigInspection(
        server_names=frozenset(names),
        source="~/.mcporter/mcporter.json",
        imports_unchecked=imports_unchecked,
    )


# --- can_handle ---

def test_can_handle_matches_linkedin_only():
    ch = LinkedInChannel()
    for url in [
        "https://www.linkedin.com/in/someone",
        "https://LINKEDIN.COM/jobs/view/123",
    ]:
        assert ch.can_handle(url) is True, url
    for url in ["https://example.com", "https://notlinkedin.com.evil.com", ""]:
        assert ch.can_handle(url) is False, url


# --- check(): mcporter missing ---

def test_check_off_without_mcporter_mentions_jina_fallback():
    ch = LinkedInChannel()
    with patch.object(li.shutil, "which", return_value=None):
        status, message = ch.check()
    assert status == "off"
    assert "Jina Reader" in message
    assert "linkedin-scraper-mcp" in message


# --- check(): config error ---

def test_check_error_when_config_inspection_fails():
    ch = LinkedInChannel()
    ch.active_backend = "stale"
    with patch.object(li.shutil, "which", return_value="/usr/bin/mcporter"), \
            patch.object(
                li, "inspect_mcporter_config",
                side_effect=McporterConfigError("mcpServers 缺失"),
            ):
        status, message = ch.check()
    assert status == "error"
    assert "mcpServers 缺失" in message
    assert ch.active_backend is None


# --- check(): server configured (any accepted alias) ---

def test_check_configured_server_warns_not_ok():
    """Config presence alone must not be sold as usable."""
    for alias in ("linkedin", "linkedin-scraper", "linkedin-scraper-mcp"):
        ch = LinkedInChannel()
        with patch.object(li.shutil, "which", return_value="/usr/bin/mcporter"), \
                patch.object(
                    li, "inspect_mcporter_config",
                    return_value=_inspection(names=[alias, "exa"]),
                ):
            status, message = ch.check()
        assert status == "warn", alias
        assert "未启动本地" in message
        assert ch.active_backend is None


# --- check(): editor imports unexpanded ---

def test_check_unchecked_imports_warns_instead_of_off():
    ch = LinkedInChannel()
    with patch.object(li.shutil, "which", return_value="/usr/bin/mcporter"), \
            patch.object(
                li, "inspect_mcporter_config",
                return_value=_inspection(imports_unchecked=True),
            ):
        status, message = ch.check()
    assert status == "warn"
    assert "editor" in message
    assert "未验证" in message


# --- check(): installed but unconfigured ---

def test_check_off_with_add_command_when_unconfigured():
    ch = LinkedInChannel()
    with patch.object(li.shutil, "which", return_value="/usr/bin/mcporter"), \
            patch.object(
                li, "inspect_mcporter_config", return_value=_inspection(),
            ):
        status, message = ch.check()
    assert status == "off"
    assert "mcporter config add linkedin" in message
