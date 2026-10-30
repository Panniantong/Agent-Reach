# -*- coding: utf-8 -*-
"""Tests for the remaining thin channels: OpenCLI sites, Exa Search, LinkedIn.

These channels gate routing/doctor output through small branchy check()
methods and can_handle() matchers that previously had no direct coverage:

- Facebook/Instagram ride the shared OpenCLISiteChannel (domain routing +
  opencli_status health states).
- ExaSearchChannel is a search-only channel (can_handle always False) whose
  check() classifies mcporter config states.
- LinkedInChannel routes linkedin.com URLs and classifies mcporter + uvx
  availability.
"""

import shutil

import pytest

from agent_reach.backends.opencli import OpenCLIStatus
from agent_reach.channels.exa_search import ExaSearchChannel
from agent_reach.channels.facebook import FacebookChannel
from agent_reach.channels.instagram import InstagramChannel
from agent_reach.channels.linkedin import LinkedInChannel
from agent_reach.channels.mcporter import (
    McporterConfigError,
    McporterConfigInspection,
)


def opencli_state(
    installed=False, broken=False, extension_connected=False, hint=""
) -> OpenCLIStatus:
    st = OpenCLIStatus(
        installed=installed, broken=broken, hint=hint
    )
    st.extension_connected = extension_connected
    return st


class TestOpenCLISiteChannels:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.facebook.com/zuck",
            "https://facebook.com",
            "https://m.facebook.com/profile.php?id=4",
            "https://fb.com/watch/123",
            "https://fb.watch/abc123",
        ],
    )
    def test_facebook_can_handle_own_domains(self, url):
        assert FacebookChannel().can_handle(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.instagram.com/p/abc/",
            "https://instagram.com",
            "https://instagr.am/p/xyz/",
        ],
    )
    def test_instagram_can_handle_own_domains(self, url):
        assert InstagramChannel().can_handle(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.linkedin.com/in/alice",
            "https://twitter.com/facebook",
            "https://github.com/facebook/react",
            "https://v2ex.com/t/123",
        ],
    )
    def test_facebook_rejects_foreign_domains(self, url):
        assert FacebookChannel().can_handle(url) is False

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.facebook.com/instagram",
            "https://fb.com/instagram",
            "https://twitter.com/instagram",
        ],
    )
    def test_instagram_rejects_foreign_domains(self, url):
        assert InstagramChannel().can_handle(url) is False

    def test_channel_metadata_is_complete(self):
        for channel in (FacebookChannel(), InstagramChannel()):
            assert channel.name
            assert channel.site
            assert channel.domains
            assert channel.usage
            assert channel.login_hint

    def test_check_off_when_opencli_not_installed(self, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.backends.opencli_status",
            lambda *a, **k: opencli_state(installed=False),
        )
        status, message = FacebookChannel().check()
        assert status == "off"
        assert "agent-reach install" in message

    def test_check_error_when_opencli_broken(self, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.backends.opencli_status",
            lambda *a, **k: opencli_state(
                installed=True, broken=True, hint="daemon crashed"
            ),
        )
        status, message = FacebookChannel().check()
        assert status == "error"
        assert "daemon crashed" in message

    def test_check_warn_when_opencli_ready(self, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.backends.opencli_status",
            lambda *a, **k: opencli_state(
                installed=True, extension_connected=True, hint="connected"
            ),
        )
        status, message = InstagramChannel().check()
        assert status == "warn"
        assert "Chrome" in message

    def test_check_warn_passes_opencli_hint(self, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.backends.opencli_status",
            lambda *a, **k: opencli_state(
                installed=True, extension_connected=False, hint="extension disconnected"
            ),
        )
        status, message = InstagramChannel().check()
        assert status == "warn"
        assert "extension disconnected" in message


class TestExaSearchChannel:
    def test_search_only_channel_never_handles_urls(self):
        assert ExaSearchChannel().can_handle("https://exa.ai/search") is False
        assert ExaSearchChannel().can_handle("https://github.com") is False

    def test_check_off_when_mcporter_missing(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        status, message = ExaSearchChannel().check()
        assert status == "off"
        assert "mcporter" in message

    def test_check_error_on_unreadable_config(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/mcporter")

        def explode(*a, **k):
            raise McporterConfigError("config unreadable")

        monkeypatch.setattr(
            "agent_reach.channels.exa_search.inspect_mcporter_config", explode
        )
        status, message = ExaSearchChannel().check()
        assert status == "error"
        assert "config unreadable" in message

    def test_check_warn_when_exa_configured(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/mcporter")
        monkeypatch.setattr(
            "agent_reach.channels.exa_search.inspect_mcporter_config",
            lambda *a, **k: McporterConfigInspection(
                frozenset({"exa"}), "home"
            ),
        )
        status, message = ExaSearchChannel().check()
        assert status == "warn"
        assert "Exa" in message

    def test_check_warn_when_editor_imports_unchecked(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/mcporter")
        monkeypatch.setattr(
            "agent_reach.channels.exa_search.inspect_mcporter_config",
            lambda *a, **k: McporterConfigInspection(
                frozenset({"other"}), "home", imports_unchecked=True
            ),
        )
        status, message = ExaSearchChannel().check()
        assert status == "warn"
        assert "imports" in message

    def test_check_off_when_exa_not_configured(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/mcporter")
        monkeypatch.setattr(
            "agent_reach.channels.exa_search.inspect_mcporter_config",
            lambda *a, **k: McporterConfigInspection(frozenset(), None),
        )
        status, message = ExaSearchChannel().check()
        assert status == "off"
        assert "mcporter config add exa" in message


class TestLinkedInChannel:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.linkedin.com/in/alice",
            "https://linkedin.com/company/acme",
            "https://www.linkedin.com/jobs/view/123",
        ],
    )
    def test_can_handle_linkedin_domains(self, url):
        assert LinkedInChannel().can_handle(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://facebook.com/linkedin",
            "https://twitter.com/linkedin",
            "https://github.com/linkedin",
        ],
    )
    def test_can_handle_rejects_foreign_domains(self, url):
        assert LinkedInChannel().can_handle(url) is False

    def test_check_off_without_mcporter(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        status, message = LinkedInChannel().check()
        assert status == "off"
        assert "Jina Reader" in message

    def test_check_error_on_unreadable_config(self, monkeypatch):
        monkeypatch.setattr(
            shutil, "which", lambda cmd: "/usr/bin/mcporter"
        )

        def explode(*a, **k):
            raise McporterConfigError("config unreadable")

        monkeypatch.setattr(
            "agent_reach.channels.linkedin.inspect_mcporter_config", explode
        )
        status, message = LinkedInChannel().check()
        assert status == "error"
        assert "config unreadable" in message

    def test_check_warn_when_server_configured_but_uvx_missing(self, monkeypatch):
        monkeypatch.setattr(
            shutil,
            "which",
            lambda cmd: "/usr/bin/mcporter" if cmd == "mcporter" else None,
        )
        monkeypatch.setattr(
            "agent_reach.channels.linkedin.inspect_mcporter_config",
            lambda *a, **k: McporterConfigInspection(
                frozenset({"mcp-server-linkedin"}), "home"
            ),
        )
        status, message = LinkedInChannel().check()
        assert status == "warn"
        assert "uvx" in message

    def test_check_warn_when_server_configured_with_uvx(self, monkeypatch):
        monkeypatch.setattr(
            shutil,
            "which",
            lambda cmd: "/usr/bin/mcporter" if cmd == "mcporter" else "/usr/bin/uvx",
        )
        monkeypatch.setattr(
            "agent_reach.channels.linkedin.inspect_mcporter_config",
            lambda *a, **k: McporterConfigInspection(
                frozenset({"linkedin-scraper"}), "home"
            ),
        )
        status, message = LinkedInChannel().check()
        assert status == "warn"
        assert "uvx" not in message

    def test_check_warn_when_editor_imports_unchecked(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/mcporter")
        monkeypatch.setattr(
            "agent_reach.channels.linkedin.inspect_mcporter_config",
            lambda *a, **k: McporterConfigInspection(
                frozenset(), None, imports_unchecked=True
            ),
        )
        status, message = LinkedInChannel().check()
        assert status == "warn"
        assert "imports" in message

    def test_check_off_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/mcporter")
        monkeypatch.setattr(
            "agent_reach.channels.linkedin.inspect_mcporter_config",
            lambda *a, **k: McporterConfigInspection(frozenset(), None),
        )
        status, message = LinkedInChannel().check()
        assert status == "off"
        assert "mcporter config add linkedin" in message
