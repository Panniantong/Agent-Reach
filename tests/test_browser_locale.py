import sys
import types

from agent_reach.runtime import browser_watcher


def test_browser_locale_defaults_and_env_override(monkeypatch):
    monkeypatch.delenv("AGENT_REACH_BROWSER_LOCALE", raising=False)
    assert browser_watcher._browser_locale() == "en-US"

    monkeypatch.setenv("AGENT_REACH_BROWSER_LOCALE", "   ")
    assert browser_watcher._browser_locale() == "en-US"

    monkeypatch.setenv("AGENT_REACH_BROWSER_LOCALE", "zh-CN")
    assert browser_watcher._browser_locale() == "zh-CN"


def test_launch_cloak_passes_configured_locale(monkeypatch, tmp_path):
    captured = {}

    def fake_launch_persistent_context(profile_dir, **kwargs):
        captured["profile_dir"] = profile_dir
        captured.update(kwargs)
        return types.SimpleNamespace(pages=[object()], new_page=lambda: None)

    monkeypatch.setitem(
        sys.modules,
        "cloakbrowser",
        types.SimpleNamespace(launch_persistent_context=fake_launch_persistent_context),
    )
    monkeypatch.setattr(browser_watcher.browser, "profile_dir", lambda: tmp_path / "profile")
    monkeypatch.setattr(browser_watcher.browser, "extension_dir", lambda: tmp_path / "ext")
    monkeypatch.setenv("AGENT_REACH_BROWSER_LOCALE", "fr-FR")

    browser_watcher._launch_cloak("https://example.com", headless=True)
    assert captured["locale"] == "fr-FR"
