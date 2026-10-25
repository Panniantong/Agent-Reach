"""Browser locale is configurable instead of hardcoded to zh-CN."""

from agent_reach.runtime import browser_watcher


def _captured_launch(monkeypatch, tmp_path):
    """Run _launch_cloak with a fake cloakbrowser and capture the kwargs."""
    captured = {}

    class FakeContext:
        pages = [object()]

    def fake_launch(persistent_context, **kwargs):
        captured.update(kwargs)
        return FakeContext()

    fake_module = type("FakeCloak", (), {"launch_persistent_context": staticmethod(fake_launch)})
    monkeypatch.setitem(__import__("sys").modules, "cloakbrowser", fake_module)
    monkeypatch.setattr(browser_watcher.browser, "profile_dir", lambda: tmp_path / "profile")
    monkeypatch.setattr(browser_watcher.browser, "extension_dir", lambda: tmp_path / "ext")
    return captured


def test_browser_locale_defaults_to_zh_cn(monkeypatch, tmp_path):
    """The existing Chinese default stays the default for every user."""
    monkeypatch.setenv("HOME", str(tmp_path))
    captured = _captured_launch(monkeypatch, tmp_path)

    browser_watcher._launch_cloak("about:blank")

    assert captured["locale"] == "zh-CN"


def test_browser_locale_is_configurable_via_config_key(monkeypatch, tmp_path):
    """A config key sets the browser locale."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BROWSER_LOCALE", "en-US")
    captured = _captured_launch(monkeypatch, tmp_path)

    browser_watcher._launch_cloak("about:blank")

    assert captured["locale"] == "en-US"


def test_browser_locale_env_var_overrides_config_key(monkeypatch, tmp_path):
    """An explicit env var wins over the stored config."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BROWSER_LOCALE", "de-DE")
    captured = _captured_launch(monkeypatch, tmp_path)

    browser_watcher._launch_cloak("about:blank")

    assert captured["locale"] == "de-DE"


def test_browser_locale_ignores_blank_value(monkeypatch, tmp_path):
    """An empty value must not produce an empty locale."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BROWSER_LOCALE", "   ")
    captured = _captured_launch(monkeypatch, tmp_path)

    browser_watcher._launch_cloak("about:blank")

    assert captured["locale"] == "zh-CN"
