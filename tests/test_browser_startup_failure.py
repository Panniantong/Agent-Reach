"""When Chrome cannot start, the error should carry Chrome's own reason, not just "browser closed"."""

import sys

import pytest

SANDBOX_FATAL = (
    "[12:12:1121/101500.000000:FATAL:content/browser/zygote_host/zygote_host_impl_linux.cc:130] "
    "No usable sandbox! If you want to live dangerously and need an immediate workaround, "
    "you can try using --no-sandbox."
)


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    from agent_reach.runtime import browser

    browser.browser_root().mkdir(parents=True)
    return browser


def test_chrome_stderr_is_not_discarded(home, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("the pipe launch is POSIX only")
    from agent_reach.runtime import browser_watcher

    seen = {}

    class FakeChrome:
        def __init__(self, argv, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(browser_watcher.subprocess, "Popen", FakeChrome)
    _, conn = browser_watcher._launch_with_pipe("/fake/chrome", "about:blank")
    conn.close()
    assert seen.get("stderr") is None  # inherited from the watcher, whose stderr is watcher.log


def test_startup_error_names_chromes_fatal_line(home):
    home.watcher_log_path().write_text(
        f"extension loaded: abc\n{SANDBOX_FATAL}\nbrowser closed\n", "utf-8"
    )
    assert "No usable sandbox!" in home._startup_failure_detail()


def test_startup_error_falls_back_to_the_last_log_line(home):
    home.watcher_log_path().write_text("starting\nbrowser closed\n", "utf-8")
    assert home._startup_failure_detail() == "browser closed"


@pytest.mark.parametrize("content", [None, "", "\n\n"])
def test_startup_error_without_a_log_has_no_detail(home, content):
    if content is not None:
        home.watcher_log_path().write_text(content, "utf-8")
    assert home._startup_failure_detail() == ""
