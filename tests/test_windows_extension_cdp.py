# -*- coding: utf-8 -*-
"""Windows system Chrome gets the OpenCLI extension over CDP, not the Web Store.

Chrome dropped `--load-extension` and Windows has no pipe path, so the fallback
browser asks the one it just opened to install the unpacked copy. These tests
pin the decisions around that call, not the Chrome side of it.
"""

import pytest


def _write_extension(version: str = "1.0.0"):
    from agent_reach.runtime import browser

    folder = browser.extension_dir()
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text('{"version": "%s"}' % version, encoding="utf-8")
    return folder


# ── the predicates ──


def test_loads_extension_over_cdp_is_windows_system_chrome_only(monkeypatch):
    from agent_reach.runtime import browser

    monkeypatch.setattr(browser, "can_load_extension", lambda: False)
    monkeypatch.setattr(browser.sys, "platform", "win32")
    assert browser.loads_extension_over_cdp()

    monkeypatch.setattr(browser.sys, "platform", "darwin")
    assert not browser.loads_extension_over_cdp()

    # CloakBrowser loads extensions itself, so CDP is not the answer there either.
    monkeypatch.setattr(browser.sys, "platform", "win32")
    monkeypatch.setattr(browser, "can_load_extension", lambda: True)
    assert not browser.loads_extension_over_cdp()


# ── the install call ──


def test_load_extension_over_cdp_needs_a_copy_on_disk(monkeypatch):
    from agent_reach.runtime import browser, cdp

    calls = []
    monkeypatch.setattr(browser, "is_running", lambda: True)
    monkeypatch.setattr(cdp, "call", lambda *a, **k: calls.append(a))

    assert browser.load_extension_over_cdp(timeout=0) is None
    assert calls == []


def test_load_extension_over_cdp_returns_the_extension_id(monkeypatch):
    from agent_reach.runtime import browser, cdp

    folder = _write_extension()
    monkeypatch.setattr(browser, "is_running", lambda: True)
    monkeypatch.setattr(cdp, "call", lambda method, params=None, **k: (
        {"id": "abcdef"} if method == "Extensions.loadUnpacked" and params == {"path": str(folder)} else None))

    assert browser.load_extension_over_cdp(timeout=0) == "abcdef"


def test_load_extension_over_cdp_waits_for_the_debugging_port(monkeypatch):
    from agent_reach.runtime import browser, cdp

    _write_extension()
    answers = [None, None, {"id": "late"}]
    monkeypatch.setattr(browser, "is_running", lambda: True)
    monkeypatch.setattr(cdp, "call", lambda *a, **k: answers.pop(0))
    monkeypatch.setattr(browser.time, "sleep", lambda seconds: None)  # the retry, without the wait

    assert browser.load_extension_over_cdp(timeout=5) == "late"


def test_load_extension_over_cdp_gives_up_when_chrome_refuses(monkeypatch):
    from agent_reach.runtime import browser, cdp

    _write_extension()
    monkeypatch.setattr(browser, "is_running", lambda: True)
    monkeypatch.setattr(cdp, "call", lambda *a, **k: None)

    assert browser.load_extension_over_cdp(timeout=0) is None


# ── the launch ──


@pytest.fixture
def windows_launch(monkeypatch):
    """A Windows system-Chrome launch with the process side stubbed out."""
    from agent_reach.runtime import browser

    fake = {"argv": [], "launches": 0, "running": False}
    monkeypatch.setattr(browser, "can_load_extension", lambda: False)
    monkeypatch.setattr(browser, "loads_extension_over_cdp", lambda: True)
    monkeypatch.setattr(browser, "ensure_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(browser, "_prepare_shared_profile", lambda: None)
    monkeypatch.setattr(browser, "is_running", lambda: fake["running"])
    monkeypatch.setattr(browser, "wait_for", lambda check, seconds, interval=1.0: True)
    monkeypatch.setattr(browser, "_spawn_watcher", lambda: None)

    def fake_popen(argv, *args, **kwargs):
        fake["argv"].append(argv)
        fake["launches"] += 1
        fake["running"] = True  # the port answers once Chrome is started

    monkeypatch.setattr(browser.subprocess, "Popen", fake_popen)
    return fake


def test_launch_installs_the_extension_over_cdp(windows_launch, monkeypatch):
    from agent_reach.runtime import browser

    _write_extension()
    monkeypatch.setattr(browser, "load_extension_over_cdp", lambda timeout=20.0: "abcdef")

    browser._launch("about:blank", headless=True)

    assert windows_launch["launches"] == 1
    assert "--remote-debugging-pipe" not in windows_launch["argv"][0]  # no pipe on Windows
    assert browser._load_state().get("extension_id") == "abcdef"


def test_launch_clears_a_stale_extension_id_when_chrome_refuses(windows_launch, monkeypatch):
    from agent_reach.runtime import browser

    _write_extension()
    browser.update_state(extension_id="stale")
    monkeypatch.setattr(browser, "load_extension_over_cdp", lambda timeout=20.0: None)

    browser._launch("about:blank", headless=True)

    assert browser._load_state().get("extension_id") is None  # nothing claims a loaded extension


# ── setup decides between the disk copy and the store ──


@pytest.fixture
def fake_setup(monkeypatch):
    """`setup` with the launch and the binding stubbed, so only its decisions run."""
    from agent_reach.runtime import browser

    fake = {"contexts": [], "running": False, "watched": False, "launches": 0, "store": [], "installed": "abcdef"}
    monkeypatch.setattr(browser, "can_load_extension", lambda: False)
    monkeypatch.setattr(browser, "loads_extension_over_cdp", lambda: True)
    monkeypatch.setattr(browser, "ensure_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(browser, "is_running", lambda: fake["running"])
    monkeypatch.setattr(browser, "watcher_running", lambda: fake["watched"])
    monkeypatch.setattr(browser, "dedicated_context", lambda: "dedicated" if fake["running"] else None)
    monkeypatch.setattr(browser, "connected_contexts", lambda: list(fake["contexts"]))
    monkeypatch.setattr(browser, "_remaining_start_wait", lambda: 0.0)

    def fake_launch(url, *, headless=True):
        fake["launches"] += 1
        fake["running"] = True
        fake["watched"] = True
        browser.update_state(extension_id=fake["installed"])
        if fake["installed"]:
            fake["contexts"].append("dedicated")

    def fake_stop(timeout=10.0):
        fake["running"] = False
        fake["watched"] = False
        fake["contexts"].clear()
        return True

    def fake_store():
        # It opens a window and waits for the user, so it must not run under start_lock.
        with browser.start_lock(wait=0.5):
            fake["store"].append("unlocked")
        return {"status": "store"}

    monkeypatch.setattr(browser, "_launch", fake_launch)
    monkeypatch.setattr(browser, "stop", fake_stop)
    monkeypatch.setattr(browser, "_setup_from_store", fake_store)
    return fake


def test_setup_uses_the_disk_copy_instead_of_the_store(fake_setup):
    from agent_reach.runtime import browser

    _write_extension()

    result = browser.setup()

    assert fake_setup["store"] == []  # no Web Store page, no click
    assert fake_setup["launches"] == 1
    assert result["opencli_connected"] is True
    assert result["opencli_context"] == "dedicated"


def test_setup_opens_the_store_page_when_chrome_refuses_the_install(fake_setup):
    from agent_reach.runtime import browser

    _write_extension()
    fake_setup["installed"] = None  # Chrome answered, but with no extension id

    assert browser.setup() == {"status": "store"}
    assert fake_setup["store"] == ["unlocked"]  # reached only after start_lock was released


def test_setup_asks_for_the_store_when_no_copy_can_be_downloaded(monkeypatch):
    from agent_reach.runtime import browser
    from agent_reach.runtime.result import UPSTREAM_BROKEN, ReachError

    def offline():
        raise ReachError(UPSTREAM_BROKEN, "could not find the OpenCLI extension release")

    monkeypatch.setattr(browser, "can_load_extension", lambda: False)
    monkeypatch.setattr(browser, "loads_extension_over_cdp", lambda: True)
    monkeypatch.setattr(browser, "ensure_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(browser, "bound_context", lambda: None)
    monkeypatch.setattr(browser, "refresh_extension", offline)
    monkeypatch.setattr(browser, "_setup_from_store", lambda: {"status": "store"})

    assert browser.setup() == {"status": "store"}  # the offline click is still an option


# ── the NEED_SETUP gate ──


def test_ensure_running_does_not_report_need_setup_on_windows(monkeypatch):
    from agent_reach.runtime import browser

    setups, launched = [], {"running": False}
    monkeypatch.setattr(browser, "can_load_extension", lambda: False)
    monkeypatch.setattr(browser, "loads_extension_over_cdp", lambda: True)
    monkeypatch.setattr(browser, "bound_context", lambda: "dedicated")
    monkeypatch.setattr(browser, "is_running", lambda: launched["running"])
    monkeypatch.setattr(browser, "connected_contexts", lambda: [])
    monkeypatch.setattr(browser, "wait_for", lambda check, seconds, interval=1.0: False)
    monkeypatch.setattr(browser, "stop", lambda timeout=10.0: True)
    monkeypatch.setattr(browser, "watcher_running", lambda: False)
    monkeypatch.setattr(browser, "_launch", lambda url="about:blank", headless=True: launched.update(running=True))
    monkeypatch.setattr(browser, "_remaining_start_wait", lambda: 0.0)
    monkeypatch.setattr(browser, "setup", lambda **kw: setups.append(kw))

    browser.ensure_running()  # no ReachError: the CDP install counts as automatic

    assert setups == [{}]


def test_setup_problems_drop_the_click_once_the_copy_is_on_disk(monkeypatch):
    from agent_reach.runtime import browser

    monkeypatch.setattr(browser, "can_load_extension", lambda: False)
    monkeypatch.setattr(browser, "loads_extension_over_cdp", lambda: True)
    monkeypatch.setattr(browser, "bound_context", lambda: None)

    assert browser.setup_problems()  # nothing on disk yet: the user still has to set it up

    _write_extension()

    assert browser.setup_problems() == []
