# -*- coding: utf-8 -*-
"""Dedicated tests for the ``exa_search`` channel.

Exa is a search-only channel (``can_handle`` is always False) that rides
mcporter + the remote Exa MCP. Its ``check()`` has five outcomes: mcporter
missing (off with install prescription), unreadable mcporter config
(error), ``exa`` present in config (warn — remote connectivity is never
probed by Doctor), editor imports left unexpanded (warn — credential-read
boundary), and mcporter installed but Exa unconfigured (off with the exact
add command). ``inspect_mcporter_config`` and ``shutil.which`` are stubbed
so every branch runs offline. Follow-up to #331 — extends dedicated
channel coverage after rss (#360), github (#361), web (#363),
reddit (#364), xueqiu (#365), v2ex (#366) and youtube (#367).
"""

from unittest.mock import patch

from agent_reach.channels import exa_search as exa
from agent_reach.channels.exa_search import ExaSearchChannel
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


# --- can_handle: search-only ---

def test_can_handle_rejects_every_url():
    ch = ExaSearchChannel()
    for url in ["https://exa.ai", "https://example.com/a", ""]:
        assert ch.can_handle(url) is False, url


# --- check(): mcporter missing ---

def test_check_off_without_mcporter_gives_install_steps():
    ch = ExaSearchChannel()
    with patch.object(exa.shutil, "which", return_value=None):
        status, message = ch.check()
    assert status == "off"
    assert "npm install -g mcporter" in message
    assert "mcporter config add exa" in message


# --- check(): config error ---

def test_check_error_when_config_inspection_fails():
    ch = ExaSearchChannel()
    ch.active_backend = "stale"
    with patch.object(exa.shutil, "which", return_value="/usr/bin/mcporter"), \
            patch.object(
                exa, "inspect_mcporter_config",
                side_effect=McporterConfigError("server 定义必须是对象"),
            ):
        status, message = ch.check()
    assert status == "error"
    assert "server 定义必须是对象" in message
    assert ch.active_backend is None


# --- check(): exa configured ---

def test_check_configured_exa_warns_not_ok():
    """Doctor must not claim a remote MCP works from config presence alone."""
    ch = ExaSearchChannel()
    with patch.object(exa.shutil, "which", return_value="/usr/bin/mcporter"), \
            patch.object(
                exa, "inspect_mcporter_config",
                return_value=_inspection(names=["exa", "linkedin"]),
            ):
        status, message = ch.check()
    assert status == "warn"
    assert "连通验证" in message
    assert ch.active_backend is None


# --- check(): editor imports unexpanded ---

def test_check_unchecked_imports_warns_instead_of_off():
    ch = ExaSearchChannel()
    with patch.object(exa.shutil, "which", return_value="/usr/bin/mcporter"), \
            patch.object(
                exa, "inspect_mcporter_config",
                return_value=_inspection(imports_unchecked=True),
            ):
        status, message = ch.check()
    assert status == "warn"
    assert "editor imports" in message


# --- check(): installed but unconfigured ---

def test_check_off_with_add_command_when_unconfigured():
    ch = ExaSearchChannel()
    with patch.object(exa.shutil, "which", return_value="/usr/bin/mcporter"), \
            patch.object(
                exa, "inspect_mcporter_config", return_value=_inspection(),
            ):
        status, message = ch.check()
    assert status == "off"
    assert "mcporter config add exa" in message
