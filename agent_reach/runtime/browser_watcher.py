"""Owner and idle watcher of the Agent Reach browser (`python -m agent_reach.runtime.browser_watcher`).

Started detached by runtime.browser. Holds ~/.agent-reach/browser/watcher.lock
so only one runs.

With --launch --cloak it owns a Cloak persistent context on every OS; otherwise
it uses the legacy Chrome pipe on POSIX or watches a Windows Chrome fallback.
The same 600-second idle timer handles all engines. Website extraction is done
by upstream tools. Snapshot writes are serialized with logout/removal.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
import time
from typing import Optional
from urllib.parse import quote, unquote, urlsplit

from agent_reach.utils.process import windows_hidden_kwargs

from . import bridge, browser


def _launch_with_pipe(chrome: str, url: str, *, headless: bool = True):
    """Start Chrome with the CDP pipe on its fds 3 (commands in) and 4 (replies out)."""
    if sys.platform == "win32":  # pragma: no cover
        raise NotImplementedError("pipe launch is not supported on Windows")
    import fcntl

    from .cdp import PipeConnection

    to_chrome_r, to_chrome_w = os.pipe()
    from_chrome_r, from_chrome_w = os.pipe()
    # Child ends above 4 so placing them on 3/4 never overwrites one with the other.
    child_in = fcntl.fcntl(to_chrome_r, fcntl.F_DUPFD_CLOEXEC, 10)
    child_out = fcntl.fcntl(from_chrome_w, fcntl.F_DUPFD_CLOEXEC, 10)
    for fd in (to_chrome_r, from_chrome_w):
        os.close(fd)

    def place_pipe() -> None:  # in the child, after fork: dup2 leaves 3/4 inheritable
        os.dup2(child_in, 3)
        os.dup2(child_out, 4)

    try:
        proc = subprocess.Popen(
            browser.chrome_argv(chrome, url, pipe=True, headless=headless),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=False,  # Python fds are non-inheritable by default; only 3/4 get through
            preexec_fn=place_pipe,  # noqa: PLW1509 - single-threaded here
            start_new_session=True,
        )
    finally:
        os.close(child_in)
        os.close(child_out)
    return proc, PipeConnection(to_chrome_w, from_chrome_r)


def _load_extension(conn) -> None:
    ext = browser.extension_dir()
    if not (ext / "manifest.json").is_file():
        print("OpenCLI extension missing; browser opened without it", file=sys.stderr, flush=True)
        return
    reply = conn.call("Extensions.loadUnpacked", {"path": str(ext)}, timeout=60)
    if "result" in reply:
        browser.update_state(extension_id=reply["result"].get("id"))
        print(f"extension loaded: {reply['result'].get('id')}", file=sys.stderr, flush=True)
    else:
        print(f"Extensions.loadUnpacked failed: {reply.get('error')}", file=sys.stderr, flush=True)


def _proxy_options() -> Optional[dict]:
    proxy = os.environ.get("REACH_BROWSER_PROXY")
    if not proxy:
        return None
    parsed = urlsplit(proxy if "://" in proxy else "http://" + proxy)
    host = f"[{parsed.hostname}]" if parsed.hostname and ":" in parsed.hostname else parsed.hostname
    options = {"server": f"{parsed.scheme}://{host}:{parsed.port}",
               "bypass": "localhost,127.0.0.1,[::1]"}
    if parsed.username:
        options.update(username=unquote(parsed.username), password=unquote(parsed.password or ""))
    return options


def _proxy_chrome_args(proxy: Optional[dict]) -> list[str]:
    """Chrome flags for the same proxy Playwright would have applied."""
    if not proxy or not proxy.get("server"):
        return []
    server = str(proxy["server"])
    username = proxy.get("username")
    if username:
        parsed = urlsplit(server)
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        auth = f"{quote(str(username), safe='')}:{quote(str(proxy.get('password') or ''), safe='')}"
        port = f":{parsed.port}" if parsed.port else ""
        server = f"{parsed.scheme}://{auth}@{host}{port}"
    args = [f"--proxy-server={server}"]
    if proxy.get("bypass"):
        args.append(f"--proxy-bypass-list={proxy['bypass']}")
    return args


def cloak_direct_argv(*, headless: bool, proxy: Optional[dict]) -> list[str]:
    """Cloak Chromium argv with stealth flags and no DevTools pipe.

    Playwright's persistent context attaches its own debugger to every tab.
    On Windows, Chrome then rejects the OpenCLI extension with
    "Cannot attach to this target", so Xiaohongshu search/read/comments never
    get past attach. A normal process keeps the fingerprint and the extension,
    and leaves tabs free for chrome.debugger.
    """
    from cloakbrowser import build_args, ensure_binary

    profile = str(browser.profile_dir())
    extension = str(browser.extension_dir())
    extra = [
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={browser.CDP_PORT}",
        "--no-first-run",
        "--no-default-browser-check",
        *_proxy_chrome_args(proxy),
    ]
    try:
        from cloakbrowser.config import persistent_seed_args
    except Exception:  # noqa: BLE001 - older Cloak builds have no stable seed helper
        seeded = extra
    else:
        seeded = persistent_seed_args(profile, True, extra) or extra
    try:
        from cloakbrowser.widevine import seed_widevine_hint
    except Exception:  # noqa: BLE001
        seed_widevine_hint = None
    binary = ensure_binary()
    if seed_widevine_hint is not None:
        with contextlib.suppress(Exception):
            seed_widevine_hint(profile, binary)
    chrome_args = build_args(
        True, list(seeded), locale="zh-CN", headless=headless,
        extension_paths=[extension], start_maximized=False,
    )
    argv = [binary, f"--user-data-dir={profile}", *chrome_args]
    if headless and not any(arg == "--headless" or arg.startswith("--headless=") for arg in argv):
        argv.append("--headless=new")
    if any(arg == "--remote-debugging-pipe" or arg.startswith("--remote-debugging-pipe=") for arg in argv):
        raise RuntimeError("CloakBrowser direct launch must not attach a DevTools pipe")
    return argv


class _DirectCloak:
    """Owns a Cloak process the way the watcher owns a Playwright context."""

    def __init__(self, proc: subprocess.Popen) -> None:
        self._proc = proc
        self.pages = [self]

    def exited(self) -> bool:
        return self._proc.poll() is not None

    def goto(self, url: str, **_kwargs: object) -> None:
        browser.open_url(url)

    def new_page(self) -> "_DirectCloak":
        return self

    def wait_for_event(self, _event: str, timeout: float = 0) -> None:
        deadline = time.monotonic() + max(0.0, timeout) / 1000.0
        while time.monotonic() < deadline:
            if self.exited():
                return
            time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
        if not self.exited():
            raise TimeoutError

    def close(self) -> None:
        if self._proc.poll() is not None:
            return
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self._proc.pid)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10, check=False, **windows_hidden_kwargs(),
            )
        else:
            self._proc.terminate()
        try:
            self._proc.wait(5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(5)


def _launch_cloak_direct(*, headless: bool, proxy: Optional[dict]) -> _DirectCloak:
    argv = cloak_direct_argv(headless=headless, proxy=proxy)
    env = os.environ.copy()
    try:
        from cloakbrowser.license import build_launch_env
    except Exception:  # noqa: BLE001
        build_launch_env = None
    if build_launch_env is not None:
        with contextlib.suppress(Exception):
            built = build_launch_env(None)
            if built:
                env = built
    proc = subprocess.Popen(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=env, **windows_hidden_kwargs(),
    )
    direct = _DirectCloak(proc)
    if not browser.wait_for(browser.is_running, browser.START_WAIT, interval=0.2):
        direct.close()
        raise RuntimeError(
            "CloakBrowser did not open its debugging port. Windows starts it without Playwright "
            "so Xiaohongshu can attach a tab; retry `agent-reach browser stop` then the command."
        )
    return direct


def _launch_cloak(url: str, *, headless: bool = True):
    """Use the SDK's public launcher; one persistent profile, no site rules.

    Windows skips Playwright. Its pipe session already holds the debugger, and
    Xiaohongshu then fails with "Cannot attach to this target."
    """
    proxy_options = _proxy_options()
    if sys.platform == "win32":
        return _launch_cloak_direct(headless=headless, proxy=proxy_options)

    from cloakbrowser import launch_persistent_context

    ctx = launch_persistent_context(
        str(browser.profile_dir()), headless=headless, locale="zh-CN",
        args=["--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={browser.CDP_PORT}"],
        extension_paths=[str(browser.extension_dir())],
        proxy=proxy_options,
    )
    if not ctx.pages:
        ctx.new_page()
    return ctx


def watch(idle: Optional[float] = None, poll: float = 2.0, *, launch: Optional[str] = None,
          chrome: Optional[str] = None, cloak: bool = False, headless: bool = True) -> str:
    """Run until the browser is gone. Returns why it stopped."""
    idle = browser.IDLE_LIMIT if idle is None else idle
    fd = browser._open_lock(browser.watcher_lock_path())
    proc = conn = ctx = bridge_proc = None
    try:
        # A probe (watcher_running) holds the lock for an instant; a live watcher holds it for good.
        # A watcher of a browser that just closed may still be on its way out: give it a moment.
        if not browser.wait_for(lambda: browser.try_lock(fd), 10.0 if launch else 2.0, interval=0.1):
            return "another watcher is running"
        bridge_proc = bridge.start()
        if launch is not None:
            if browser.is_running():
                return "a browser is already using the debugging port"
            if cloak:
                ctx = _launch_cloak(launch, headless=headless)
            else:
                proc, conn = _launch_with_pipe(chrome or browser.ensure_chrome(), "about:blank", headless=headless)
                _load_extension(conn)
            browser.update_state(running_backend="cloakbrowser" if cloak else "chrome",
                                 profile_backend="cloakbrowser" if cloak else "chrome", headless=headless)
            browser.restore_session()
            if launch != "about:blank":
                if ctx is not None:
                    ctx.pages[0].goto(launch, wait_until="domcontentloaded", timeout=30000)
                else:
                    browser.open_url(launch)
        browser.update_state(bridge_pid=bridge_proc.pid if bridge_proc else None, bridge_note=None)
        began = time.time()

        def gone() -> bool:
            if conn is not None:
                return conn.closed.is_set() or (proc is not None and proc.poll() is not None)
            if ctx is not None and getattr(ctx, "exited", None) and ctx.exited():
                return True
            return not browser.is_running()

        while True:
            if gone():
                return "browser closed"
            if bridge_proc is not None and bridge_proc.poll() is not None:
                return "owned Bridge exited; browser closed with it"
            browser.observe_activity()
            browser.save_session()
            used = max(began, browser.last_used() or 0.0)
            left = used + idle - time.time()
            if left <= 0:
                with contextlib.suppress(Exception), browser.start_lock(wait=5.0):
                    used = max(began, browser.last_used() or 0.0)
                    if used + idle <= time.time() and browser.stop():
                        return "closed after idle"
                left = poll  # used again meanwhile, or close failed: check later
            pause = min(poll, left + 0.5)
            if ctx is not None:
                try:
                    ctx.wait_for_event("close", timeout=max(1, int(pause * 1000)))
                except Exception as exc:
                    if type(exc).__name__ != "TimeoutError":
                        if not browser.is_running():
                            return "browser closed"
                        raise
            elif conn is not None:
                conn.closed.wait(pause)  # wake the moment Chrome exits
            else:
                time.sleep(pause)
    finally:
        if ctx is not None:
            with contextlib.suppress(Exception):
                ctx.close()
        if conn is not None:
            conn.close()  # Chrome exits when its pipe closes
        if proc is not None:
            try:
                proc.wait(15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(5)
        bridge.close(bridge_proc)
        browser.update_state(bridge_note=None, bridge_pid=None)
        os.close(fd)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent_reach.runtime.browser_watcher")
    parser.add_argument("--idle", type=float, default=None, help="seconds without use before closing")
    parser.add_argument("--launch", default=None, help="start Chrome with this URL and own it (macOS/Linux)")
    parser.add_argument("--chrome", default=None, help="Chrome binary for --launch")
    parser.add_argument("--cloak", action="store_true", help="use CloakBrowser's public launcher")
    parser.add_argument("--headed", action="store_true", help="show a window for human login")
    ns = parser.parse_args()
    reason = watch(ns.idle, launch=ns.launch, chrome=ns.chrome, cloak=ns.cloak, headless=not ns.headed)
    print(reason, file=sys.stderr, flush=True)
    sys.exit(0 if reason in ("browser closed", "closed after idle") else 1)


if __name__ == "__main__":
    main()
