"""Shared Cloak browser, Chrome fallback, extension and cookie lifecycle."""

import json
import os
import shutil
import threading
import zipfile

import pytest

from agent_reach.runtime import browser, cdp


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(browser, "is_running", lambda: False)
    return tmp_path


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as zf:
        for name, (data, mode) in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o100000 | mode) << 16
            zf.writestr(info, data)
    return path


def _fake_downloads(monkeypatch, index: dict, archives: dict):
    monkeypatch.setattr(browser, "_fetch", lambda url, timeout=30.0: json.dumps(index[url]).encode())
    monkeypatch.setattr(browser, "_download", lambda url, dest, timeout=60.0: shutil.copy(archives[url], dest))


def test_domain_match_is_exact_or_subdomain():
    assert cdp.domain_matches(".reddit.com", "reddit.com")
    assert cdp.domain_matches("www.reddit.com", "reddit.com")
    assert not cdp.domain_matches("notreddit.com", "reddit.com")


def test_extension_installs_at_a_stable_path_and_refreshes_only_on_new_release(home, monkeypatch, tmp_path):
    manifest = lambda v: (json.dumps({"manifest_version": 3, "version": v}), 0o644)  # noqa: E731
    v1 = _zip(tmp_path / "v1.zip", {"manifest.json": manifest("1.0.1"), "dist/background.js": ("//", 0o644)})
    v2 = _zip(tmp_path / "v2.zip", {"manifest.json": manifest("1.0.2")})
    release = {"assets": [{"name": "opencli-extension-v1.0.1.zip", "browser_download_url": "u1"}]}
    _fake_downloads(monkeypatch, {browser.OPENCLI_RELEASE_API: release}, {"u1": v1, "u2": v2})

    assert browser.refresh_extension() == {"version": "1.0.1", "updated": True}
    assert (browser.extension_dir() / "dist" / "background.js").is_file()
    assert browser.refresh_extension() == {"version": "1.0.1", "updated": False}

    release["assets"] = [{"name": "opencli-extension-v1.0.2.zip", "browser_download_url": "u2"}]
    assert browser.refresh_extension() == {"version": "1.0.1", "updated": False}
    assert browser.refresh_extension(upgrade=True) == {"version": "1.0.2", "updated": True}
    assert browser.extension_version() == "1.0.2"
    assert browser._load_state()["extension_version"] == "1.0.2"


def test_extension_refresh_offline_keeps_the_current_copy(home, monkeypatch):
    browser.extension_dir().mkdir(parents=True)
    (browser.extension_dir() / "manifest.json").write_text(json.dumps({"version": "1.0.0"}))

    def offline(url, timeout=30.0):
        raise OSError("offline")

    monkeypatch.setattr(browser, "_fetch", offline)
    assert browser.refresh_extension() == {"version": "1.0.0", "updated": False}


def test_ensure_browser_prefers_cloak_and_reuses_its_install(home, monkeypatch, tmp_path):
    from unittest.mock import Mock

    from agent_reach.backends import cloak
    binary = tmp_path / "CloakChromium"
    binary.touch()
    install = Mock(return_value={"executable": str(binary), "python": "/private/python"})
    monkeypatch.setattr(cloak, "setup", install)
    monkeypatch.setattr(browser, "_system_chrome", lambda: "/system/chrome")
    assert browser.ensure_chrome() == str(binary)
    assert browser.ensure_chrome() == str(binary)
    assert install.call_count == 1 and browser._load_state()["backend"] == "cloakbrowser"


def test_download_failure_falls_back_to_system_chrome(home, monkeypatch):
    from agent_reach.backends import cloak
    from agent_reach.runtime.result import ReachError
    def fail():
        raise ReachError("TIMEOUT", "download timeout")
    monkeypatch.setattr(cloak, "setup", fail)
    monkeypatch.setattr(browser, "_system_chrome", lambda: "/system/chrome")
    assert browser.ensure_chrome() == "/system/chrome"
    assert browser._load_state()["backend"] == "chrome"
    assert browser._load_state()["fallback_reason"] == "TIMEOUT: download timeout"


def test_download_timeout_without_system_chrome_keeps_timeout_code(home, monkeypatch):
    from agent_reach.backends import cloak
    from agent_reach.runtime.result import ReachError
    def fail():
        raise ReachError("TIMEOUT", "download timeout")
    monkeypatch.setattr(cloak, "setup", fail)
    monkeypatch.setattr(browser, "_system_chrome", lambda: None)
    with pytest.raises(ReachError) as err:
        browser.ensure_chrome()
    assert err.value.code == "TIMEOUT"
    assert "download timeout" in err.value.message


def test_cloak_setup_preserves_underlying_timeout(home, monkeypatch):
    from agent_reach.backends import cloak
    from agent_reach.runtime import tools
    from agent_reach.runtime.result import TIMEOUT, ReachError
    monkeypatch.setattr(tools, "ensure", lambda name: None)
    monkeypatch.setattr(tools, "resolve", lambda name: "/tmp/cloakbrowser")
    monkeypatch.setattr(tools, "install_env", lambda: {})
    calls = {"n": 0}

    def run_cmd(argv, **kwargs):
        calls["n"] += 1
        raise ReachError(TIMEOUT, "cloakbrowser did not finish within 180s")

    monkeypatch.setattr("agent_reach.runtime.run.run_cmd", run_cmd)
    with pytest.raises(ReachError) as err:
        cloak.setup()
    assert err.value.code == TIMEOUT
    assert "cloakbrowser did not finish within 180s" in err.value.message
    assert calls["n"] == 1


def test_clear_site_expires_only_that_sites_cookies(home, monkeypatch):
    jar = [
        {"name": "a", "value": "1", "domain": ".reddit.com", "path": "/"},
        {"name": "b", "value": "2", "domain": "www.reddit.com", "path": "/"},
        {"name": "c", "value": "3", "domain": "notreddit.com", "path": "/"},
    ]

    def fake_call(method, params=None, **kwargs):
        if method == "Storage.getCookies":
            return {"cookies": list(jar)}
        if method == "Storage.clearDataForOrigin":
            assert "reddit.com" in params["origin"]
            return {}
        if method == "Storage.setCookies":
            for c in params["cookies"]:
                assert c["expires"] == 1
                jar[:] = [j for j in jar if (j["name"], j["domain"]) != (c["name"], c["domain"])]
            return {}
        raise AssertionError(method)

    browser.profile_dir().mkdir(parents=True)
    monkeypatch.setattr(browser, "ensure_running", lambda context=None: None)
    monkeypatch.setattr(cdp, "call", fake_call)
    monkeypatch.setattr(cdp, "_json", lambda *a: [])
    assert browser.clear_site(["reddit.com"]) == 2
    assert [c["name"] for c in jar] == ["c"]


def test_clear_site_never_opens_a_browser_that_was_never_used(home, monkeypatch):
    monkeypatch.setattr(browser, "ensure_running", lambda context=None: pytest.fail("opened the browser"))
    assert browser.clear_site(["reddit.com"]) == 0


def test_delete_profile_removes_the_browser_folder(home, monkeypatch):
    monkeypatch.setattr(browser, "stop", lambda timeout=10.0: True)
    browser.profile_dir().mkdir(parents=True)
    browser.touch()
    from agent_reach.runtime import state
    for path in (browser.profile_dir(), browser._last_used_path()):
        state.remember_path(path, "test browser")
    assert browser.delete_profile() is True
    assert not browser.browser_root().exists()
    assert browser.delete_profile() is False


def test_pipe_connection_matches_replies_and_notices_close():
    to_chrome_r, to_chrome_w = os.pipe()
    from_chrome_r, from_chrome_w = os.pipe()

    def fake_chrome():  # echoes each NUL-delimited command back as a reply, with an event first
        buf = b""
        while True:
            chunk = os.read(to_chrome_r, 4096)
            if not chunk:
                break
            buf += chunk
            while b"\0" in buf:
                raw, buf = buf.split(b"\0", 1)
                msg = json.loads(raw)
                os.write(from_chrome_w, json.dumps({"method": "Some.event"}).encode() + b"\0")
                os.write(from_chrome_w, json.dumps({"id": msg["id"], "result": {"id": msg["params"]["path"]}}).encode() + b"\0")
        os.close(from_chrome_w)  # Chrome exits when its input pipe closes
        os.close(to_chrome_r)

    t = threading.Thread(target=fake_chrome)
    t.start()
    conn = cdp.PipeConnection(to_chrome_w, from_chrome_r)
    assert conn.call("Extensions.loadUnpacked", {"path": "/ext"}) == {"id": 1, "result": {"id": "/ext"}}
    assert conn.call("Extensions.loadUnpacked", {"path": "/two"})["result"] == {"id": "/two"}
    conn.close()
    t.join(5)
    assert conn.closed.is_set()
    assert "error" in conn.call("Browser.close", timeout=1)


def test_cloak_launcher_shares_profile_and_keeps_bridge_off_proxy(home, monkeypatch):
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock

    from agent_reach.runtime import browser_watcher
    context = SimpleNamespace(pages=[Mock()])
    launch = Mock(return_value=context)
    monkeypatch.setitem(sys.modules, "cloakbrowser", SimpleNamespace(launch_persistent_context=launch))
    monkeypatch.setenv("REACH_BROWSER_PROXY", "http://user:pass@127.0.0.1:7890")
    assert browser_watcher._launch_cloak("about:blank") is context
    kwargs = launch.call_args.kwargs
    assert launch.call_args.args == (str(browser.profile_dir()),)
    assert kwargs["headless"] is True
    assert kwargs["extension_paths"] == [str(browser.extension_dir())]
    assert kwargs["proxy"] == {"server": "http://127.0.0.1:7890", "username": "user", "password": "pass",
                                "bypass": "localhost,127.0.0.1,[::1]"}


def test_migration_keeps_old_profile_and_restores_one_shared_destination(home, monkeypatch):
    binary = home / "cloak"
    binary.touch()
    browser.profile_dir().mkdir(parents=True)
    (browser.profile_dir()/"keep.txt").write_text("legacy")
    browser._save_state({"backend":"cloakbrowser", "executable":str(binary)})
    (browser.browser_root()/"session.json").write_text('{"cookies":[]}')
    browser._prepare_shared_profile()
    backup = browser._load_state()["profile_backup"]
    from pathlib import Path
    assert (Path(backup)/"keep.txt").read_text() == "legacy"
    assert not browser.profile_dir().exists()
    browser.profile_dir().mkdir()
    browser._prepare_shared_profile()
    assert browser.profile_dir().is_dir()  # migration never repeats on each start


def test_chrome_queries_are_headless_and_human_login_is_visible():
    assert '--headless=new' in browser.chrome_argv('/chrome','about:blank',pipe=False)
    assert '--headless=new' not in browser.chrome_argv('/chrome','about:blank',pipe=False,headless=False)


def test_cloak_manual_login_uses_the_same_profile_with_a_window(home, monkeypatch):
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock

    from agent_reach.runtime import browser_watcher
    context=SimpleNamespace(pages=[Mock()])
    launch=Mock(return_value=context)
    monkeypatch.setitem(sys.modules,'cloakbrowser',SimpleNamespace(launch_persistent_context=launch))
    browser_watcher._launch_cloak('https://example.test',headless=False)
    assert launch.call_args.kwargs['headless'] is False
    assert launch.call_args.args==(str(browser.profile_dir()),)
    context.pages[0].goto.assert_not_called() # restoration precedes navigation in the watcher


def test_attachable_page_skips_windows_toolbar_devtools_and_extensions():
    toolbar = {"type": "page", "id": "bar", "url": "chrome://webui-toolbar.top-chrome/",
               "webSocketDebuggerUrl": "ws://127.0.0.1/bar"}
    side = {"type": "other", "id": "side", "url": "chrome-untrusted://side-panel.top-chrome/"}
    worker = {"type": "service_worker", "id": "sw", "url": "chrome-extension://abc/bg.js"}
    devtools = {"type": "page", "id": "dt", "url": "devtools://devtools/bundled/inspector.html"}
    blank = {"type": "page", "id": "blank", "url": "about:blank"}
    note = {"type": "page", "id": "note", "url": "https://www.xiaohongshu.com/explore"}
    assert not cdp.is_attachable_page(toolbar)
    assert not cdp.is_attachable_page(side)
    assert not cdp.is_attachable_page(worker)
    assert not cdp.is_attachable_page(devtools)
    assert cdp.pick_attachable_page([toolbar, side, worker, devtools, blank, note]) is note
    assert cdp.pick_attachable_page([toolbar, blank]) is blank
    assert cdp.pick_attachable_page([toolbar, worker]) is None


def test_page_cdp_call_does_not_attach_to_a_toolbar(monkeypatch):
    toolbar = [{"type": "page", "id": "bar", "url": "chrome://webui-toolbar.top-chrome/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9/devtools/page/bar"}]
    monkeypatch.setattr(cdp, "_json", lambda path: toolbar if path == "/json/list" else {})
    monkeypatch.setattr(cdp.socket, "create_connection", lambda *a, **k: pytest.fail("attached to toolbar"))
    assert cdp.call("Runtime.evaluate", page=True) is None


def test_explicit_target_still_reaches_the_extension_worker(monkeypatch):
    worker = {"type": "service_worker", "id": "sw", "url": "chrome-extension://abc/bg.js",
              "webSocketDebuggerUrl": "ws://127.0.0.1:9/devtools/page/sw"}
    seen = {}

    def connect(*_args, **_kwargs):
        seen["yes"] = True
        raise OSError("down")

    monkeypatch.setattr(cdp, "_json", lambda path: [worker])
    monkeypatch.setattr(cdp.socket, "create_connection", connect)
    assert cdp.call("Runtime.evaluate", target_id="sw") is None
    assert seen["yes"]


def test_ensure_attachable_page_reuses_an_http_tab(monkeypatch):
    note = {"type": "page", "id": "note", "url": "https://www.xiaohongshu.com/explore"}
    monkeypatch.setattr(cdp, "_json", lambda path: [note])
    monkeypatch.setattr(cdp, "_open_page", lambda url: pytest.fail(url))
    assert cdp.ensure_attachable_page() is note


def test_ensure_attachable_page_opens_a_tab_when_only_the_toolbar_is_listed(monkeypatch):
    lists = [
        [{"type": "page", "id": "bar", "url": "chrome://webui-toolbar.top-chrome/"}],
        [{"type": "page", "id": "blank", "url": "about:blank"}],
    ]
    monkeypatch.setattr(cdp, "_json", lambda path: lists.pop(0) if path == "/json/list" else {"Browser": "1"})
    opened = {}
    monkeypatch.setattr(cdp, "_open_page", lambda url: opened.setdefault("url", url) or {"type": "page", "url": url, "id": "new"})
    page = cdp.ensure_attachable_page()
    assert opened["url"] == "about:blank"
    assert page["id"] == "blank"


def test_ensure_attachable_page_explains_a_dead_debugger_and_a_restricted_browser(monkeypatch):
    from agent_reach.runtime.result import ReachError

    monkeypatch.setattr(cdp, "_open_page", lambda url: None)
    monkeypatch.setattr(cdp, "_json", lambda path: None)
    with pytest.raises(ReachError, match="debugger endpoint") as missing:
        cdp.ensure_attachable_page()
    assert "browser stop" in missing.value.hint
    monkeypatch.setattr(cdp, "_json", lambda path: [] if path == "/json/list" else {"Browser": "1"})
    with pytest.raises(ReachError, match="could not find a browser tab") as restricted:
        cdp.ensure_attachable_page()
    assert "login xiaohongshu" in restricted.value.hint


def _cloak_modules(binary: str):
    import types

    seen = {}

    def build_args(stealth, extra, **kwargs):
        assert stealth is True
        assert kwargs["locale"] == "zh-CN"
        seen["headless"] = kwargs["headless"]
        seen["extension_paths"] = kwargs["extension_paths"]
        return ["--from-cloak", *list(extra)]

    def persistent_seed_args(profile, stealth, args):
        assert stealth is True and profile
        return ["--fingerprint=42", *args]

    cloak = types.ModuleType("cloakbrowser")
    cloak.__path__ = []
    cloak.build_args = build_args
    cloak.ensure_binary = lambda: binary
    cloak.seen = seen
    config = types.ModuleType("cloakbrowser.config")
    config.persistent_seed_args = persistent_seed_args
    return cloak, config


def test_windows_cloak_launch_does_not_hold_a_playwright_debugger(home, monkeypatch):
    import sys

    from agent_reach.runtime import browser_watcher

    binary = str(home / "chrome.exe")
    cloak, config = _cloak_modules(binary)
    monkeypatch.setattr(browser_watcher.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "cloakbrowser", cloak)
    monkeypatch.setitem(sys.modules, "cloakbrowser.config", config)
    monkeypatch.setattr(browser, "is_running", lambda: True)
    monkeypatch.setattr(browser_watcher, "windows_hidden_kwargs", lambda: {"creationflags": 123})
    captured = {}

    class Proc:
        pid = 7

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

        def terminate(self):
            return None

        def kill(self):
            return None

    def popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return Proc()

    monkeypatch.setattr(browser_watcher.subprocess, "Popen", popen)
    monkeypatch.setenv("REACH_BROWSER_PROXY", "http://user:p%40ss@127.0.0.1:7890")
    owned = browser_watcher._launch_cloak("about:blank", headless=False)
    argv = captured["argv"]
    assert argv[0] == binary
    assert f"--user-data-dir={browser.profile_dir()}" in argv
    assert "--remote-debugging-pipe" not in " ".join(argv)
    assert "--headless=new" not in argv
    assert "--fingerprint=42" in argv
    assert f"--remote-debugging-port={browser.CDP_PORT}" in argv
    assert "--proxy-server=http://user:p%40ss@127.0.0.1:7890" in argv
    assert "--proxy-bypass-list=localhost,127.0.0.1,[::1]" in argv
    assert cloak.seen["extension_paths"] == [str(browser.extension_dir())]
    assert cloak.seen["headless"] is False
    assert captured["kwargs"]["creationflags"] == 123
    assert owned.pages[0] is owned

    monkeypatch.delenv("REACH_BROWSER_PROXY", raising=False)
    headless_argv = browser_watcher.cloak_direct_argv(headless=True, proxy=None)
    assert "--headless=new" in headless_argv
    assert "--remote-debugging-pipe" not in headless_argv


def test_windows_cloak_launch_reports_a_missing_debugger_port(home, monkeypatch):
    import sys

    from agent_reach.runtime import browser_watcher

    cloak, config = _cloak_modules(str(home / "chrome.exe"))
    monkeypatch.setattr(browser_watcher.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "cloakbrowser", cloak)
    monkeypatch.setitem(sys.modules, "cloakbrowser.config", config)
    monkeypatch.setattr(browser, "wait_for", lambda *a, **k: False)
    monkeypatch.setattr(browser_watcher, "windows_hidden_kwargs", lambda: {})

    class Proc:
        pid = 9

        def __init__(self, argv):
            self.args = argv
            self.returncode = None
            self.stopped = False

        def poll(self):
            if self.args and self.args[0] == "taskkill":
                return 0
            return 0 if self.stopped else None

        def terminate(self):
            self.stopped = True

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

        def kill(self):
            self.stopped = True

        def communicate(self, input=None, timeout=None):
            self.returncode = 0
            self.stopped = True
            return (b"", b"")

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            self.returncode = 0
            self.stopped = True
            return False

    monkeypatch.setattr(browser_watcher.subprocess, "Popen", lambda argv, **kwargs: Proc(argv))
    with pytest.raises(RuntimeError, match="debugging port"):
        browser_watcher._launch_cloak("about:blank")


def test_restore_failure_preserves_the_original_snapshot(home, monkeypatch):
    from agent_reach.runtime.result import ReachError
    browser.browser_root().mkdir(parents=True)
    path=browser.browser_root()/'session.json'
    original=json.dumps({'cookies':[{'name':'sid','value':'saved','domain':'example.test'}]})
    path.write_text(original)
    monkeypatch.setattr(cdp,'call',lambda method,*a,**k:{'cookies':[]}if method=='Storage.getCookies'else None)
    with pytest.raises(ReachError,match='retained'):
        browser.restore_session()
    assert path.read_text()==original
