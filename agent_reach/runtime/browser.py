"""The Agent Reach dedicated browser.

One Reach-owned profile under ~/.agent-reach/browser/profile is shared by all
browser channels. CloakBrowser is preferred; installation/download failure falls
back to installed Chrome. The existing watcher owns the browser, loads OpenCLI,
and closes it after 600 seconds without use. Website adapters stay upstream.
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess  # nosec B404 - invoked only with fixed argv lists, never shell=True

import requests
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Iterator, List, Optional

from agent_reach.utils.paths import (
    PrivatePathError,
    atomic_write_private_text,
    home_dir,
    make_private_dir,
    read_small_text_no_follow,
)

CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
_CONTEXT_RE = re.compile(r"^\s*(\S+)\s+[—-]\s+connected\b", re.M)

#: Close the browser after this many seconds without Agent Reach use.
IDLE_LIMIT = 600.0
#: Longest wait for a cold start (measured ~42 s to OpenCLI connect on a Mac).
START_WAIT = 90.0
#: Extra wait for a browser that has been up longer than START_WAIT.
_RUNNING_GRACE = 5.0
_LOCK_WAIT = START_WAIT + 30.0
#: How long Windows setup waits for the user to add the extension from the Web Store.
_STORE_WAIT = 180.0

OPENCLI_RELEASE_API = "https://api.github.com/repos/jackwener/OpenCLI/releases/latest"
_EXTENSION_ASSET_RE = re.compile(r"^opencli-extension-.*\.zip$")
_USER_AGENT = "agent-reach"


def browser_root() -> Path:
    return home_dir() / ".agent-reach" / "browser"


def profile_dir() -> Path:
    return browser_root() / "profile"


def extension_dir() -> Path:
    return browser_root() / "extension"


def watcher_log_path() -> Path:
    return browser_root() / "watcher.log"


def _state_path() -> Path:
    return browser_root() / "state.json"


def _last_used_path() -> Path:
    return browser_root() / "last_used"


def _start_lock_path() -> Path:
    return browser_root() / "start.lock"


def watcher_lock_path() -> Path:
    return browser_root() / "watcher.lock"


def _load_state() -> dict:
    try:
        text = read_small_text_no_follow(_state_path(), max_bytes=64 * 1024)
    except (OSError, PrivatePathError):
        return {}
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {}


def _save_state(state: dict) -> None:
    from . import state as ledger
    make_private_dir(browser_root())
    ledger.remember_path(_state_path(), "browser lifecycle state")
    atomic_write_private_text(_state_path(), json.dumps(state, indent=2))


def update_state(**changes) -> None:
    """Merge `changes` into the browser state (None deletes a key); re-reads first, other processes write too."""
    state = _load_state()
    for key, value in changes.items():
        if value is None:
            state.pop(key, None)
        else:
            state[key] = value
    _save_state(state)


# ── last use ──


def touch() -> None:
    """Record an Agent Reach use of the browser (resets the idle timer)."""
    make_private_dir(browser_root())
    path = _last_used_path()
    # Create-if-missing without a rename: concurrent callers on Windows cannot replace a file another one holds.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.close(fd)
    os.utime(path)


def last_used() -> Optional[float]:
    try:
        return _last_used_path().stat().st_mtime
    except OSError:
        return None


# Generic activity signal only: no site selectors, content or credentials.
_ACTIVITY = """(() => {
  if (!window.__reachActivityInstalled) {
    window.__reachActivityInstalled = true;
    window.__reachLastInput = 0;
    for (const name of ['pointerdown', 'keydown', 'wheel', 'touchstart'])
      addEventListener(name, event => {
        if (event.isTrusted) window.__reachLastInput = Date.now();
      }, {capture: true, passive: true});
  }
  return window.__reachLastInput;
})()"""


def observe_activity() -> None:
    """Poll trusted human input and remember origins for later site-only logout."""
    from . import cdp
    origins = set(_load_state().get("visited_origins", []))
    before = set(origins)
    for target in cdp._json("/json/list") or []:
        if target.get("type") != "page":
            continue
        parsed = urllib.parse.urlsplit(target.get("url", ""))
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            origins.add(f"{parsed.scheme}://{parsed.netloc}")
        result = cdp.call("Runtime.evaluate", {"expression": _ACTIVITY, "returnByValue": True},
                          target_id=target.get("id")) or {}
        value = result.get("result", {}).get("value")
        if isinstance(value, (int, float)) and (last_used() or 0) < value / 1000 <= time.time() + 1:
            touch()
    if origins != before:
        update_state(visited_origins=sorted(origins))


# ── cross-process locks ──


def _open_lock(path: Path) -> int:
    from . import state as ledger
    make_private_dir(path.parent)
    ledger.remember_path(path, "browser lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    return os.open(path, flags, 0o600)


def try_lock(fd: int) -> bool:
    """Take an exclusive lock on `fd` without blocking."""
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


@contextlib.contextmanager
def _locked(path: Path, wait: float) -> Iterator[None]:
    """Hold an exclusive lock on `path`; ReachError after `wait` seconds."""
    fd = _open_lock(path)
    try:
        deadline = time.monotonic() + wait
        while not try_lock(fd):
            if time.monotonic() >= deadline:
                from .result import UPSTREAM_BROKEN, ReachError

                raise ReachError(UPSTREAM_BROKEN, "another Agent Reach process is still starting the browser")
            time.sleep(0.2)
        yield
    finally:
        os.close(fd)  # closing releases the lock


def start_lock(wait: float = _LOCK_WAIT):
    """Serializes launching (and idle-closing) the browser across processes."""
    return _locked(_start_lock_path(), wait)


def watcher_running() -> bool:
    fd = _open_lock(watcher_lock_path())
    try:
        return not try_lock(fd)
    finally:
        os.close(fd)


def wait_for(check: Callable[[], bool], seconds: float, interval: float = 1.0) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        if check():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


# ── downloads ──


def _require_https(url: str) -> None:
    if not url.startswith("https://"):
        raise ValueError(f"refusing to fetch non-https url: {url}")


def _fetch(url: str, timeout: float = 30.0) -> bytes:
    """GET `url` (honours the OS / env proxy settings)."""
    _require_https(url)
    resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _download(url: str, dest: Path, timeout: float = 60.0) -> None:
    _require_https(url)
    resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as out:
        for chunk in resp.iter_content(1 << 20):
            out.write(chunk)


def _unzip(archive: Path, dest: Path) -> None:
    """Extract keeping symlinks and exec bits (a Chrome .app is full of both)."""
    if platform.system() == "Darwin" and shutil.which("ditto"):
        subprocess.run(["ditto", "-x", "-k", str(archive), str(dest)], check=True, capture_output=True, timeout=600)
        return
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            target = (dest / info.filename).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"unsafe path in archive: {info.filename}")
            mode = info.external_attr >> 16
            if (mode & 0o170000) == 0o120000:  # symlink
                target.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(zf.read(info).decode("utf-8"), target)
                continue
            zf.extract(info, dest)
            if mode & 0o111 and not info.is_dir():
                os.chmod(target, (mode & 0o777) | 0o600)


# ── Chrome ──


def _system_chrome() -> Optional[str]:
    system = platform.system()
    candidates: List[Optional[str]] = []
    if system == "Darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    elif system == "Windows":
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    else:
        candidates = [c for n in ("google-chrome", "google-chrome-stable", "chromium") if (c := shutil.which(n)) is not None]
    return next((c for c in candidates if c and os.path.exists(c)), None)








def chrome_binary() -> Optional[str]:
    """Offline lookup; never starts a browser or downloads anything."""
    selected = _load_state().get("executable")
    if selected and Path(selected).is_file():
        return selected
    return _system_chrome()


def ensure_chrome(*, retry_cloak: bool = False) -> str:
    """Prepare CloakBrowser, falling back only to an installed system Chrome."""
    from .result import NEED_SETUP, ReachError

    selected = chrome_binary()
    if selected and _load_state().get("backend") and not retry_cloak:
        return selected
    from agent_reach.backends import cloak
    try:
        installed = cloak.setup()
    except (ReachError, OSError):
        fallback = _system_chrome()
        if not fallback:
            raise ReachError(NEED_SETUP, "CloakBrowser could not be installed and no system Chrome was found",
                             hint="Check the download/proxy connection, or install Chrome, then run agent-reach browser setup.") from None
        update_state(backend="chrome", executable=fallback, launcher_python=None,
                     fallback_reason="CloakBrowser installation/download failed")
        return fallback
    update_state(backend="cloakbrowser", executable=installed["executable"],
                 launcher_python=installed["python"], fallback_reason=None)
    return installed["executable"]


def can_load_extension() -> bool:
    """Cloak loads extensions everywhere; system Chrome uses pipe loading on POSIX."""
    return _load_state().get("backend") == "cloakbrowser" or sys.platform != "win32"


def chrome_argv(exe: str, url: str, *, pipe: bool, headless: bool = True) -> List[str]:
    argv = [
        exe,
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile_dir()}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        argv += ["--headless=new"]
    if pipe:
        argv += ["--remote-debugging-pipe", "--enable-unsafe-extension-debugging"]
    if os.environ.get("AGENT_REACH_TEST_MOCK_KEYCHAIN") == "1":
        # Tests only (temp HOME has no login keychain). Never for real users: it changes the cookie key.
        argv += ["--use-mock-keychain", "--password-store=basic"]
    return argv + [url]


# ── OpenCLI extension ──


def extension_version() -> Optional[str]:
    try:
        return json.loads((extension_dir() / "manifest.json").read_text("utf-8")).get("version")
    except (OSError, ValueError):
        return None


def refresh_extension(*, upgrade: bool = False) -> dict:
    """Install or update the OpenCLI extension from the latest OpenCLI release.

    Keeps the current copy when GitHub is unreachable; raises only if there is none.
    Returns {"version", "updated"}. A running browser is closed before files change.
    """
    from .result import UPSTREAM_BROKEN, ReachError

    current = extension_version()
    if current and not upgrade:
        return {"version": current, "updated": False}
    try:
        release = json.loads(_fetch(OPENCLI_RELEASE_API))
        asset = next(a for a in release.get("assets", []) if _EXTENSION_ASSET_RE.match(a.get("name", "")))
    except Exception as exc:  # noqa: BLE001
        if current:
            return {"version": current, "updated": False}
        raise ReachError(UPSTREAM_BROKEN, f"could not find the OpenCLI extension release: {exc}") from None
    state = _load_state()
    if current and state.get("extension_asset") == asset["name"]:
        return {"version": current, "updated": False}
    from . import state as ledger
    make_private_dir(browser_root())
    ledger.remember_path(extension_dir(), "OpenCLI extension")
    work = Path(tempfile.mkdtemp(prefix=".extension-", dir=browser_root()))
    try:
        archive = work / "extension.zip"
        _download(asset["browser_download_url"], archive)
        expected_digest = asset.get("digest", "")
        if expected_digest.startswith("sha256:"):
            import hashlib

            actual_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            if actual_digest != expected_digest.split(":", 1)[1]:
                raise ReachError(UPSTREAM_BROKEN, "OpenCLI extension archive failed integrity check")
        unpacked = work / "unpacked"
        unpacked.mkdir()
        _unzip(archive, unpacked)
        manifest = next(unpacked.rglob("manifest.json"), None)
        if manifest is None:
            raise ValueError("no manifest.json in the extension zip")
        version = json.loads(manifest.read_text("utf-8")).get("version")
        if current and version == current:
            update_state(extension_asset=asset["name"], extension_version=version)
            return {"version": version, "updated": False}
        if is_running():
            stop()  # never swap files under a running extension; the next launch loads the new one
        shutil.rmtree(extension_dir(), ignore_errors=True)
        os.replace(manifest.parent, extension_dir())
    except ReachError:
        raise
    except Exception as exc:  # noqa: BLE001
        if current and extension_version():
            return {"version": current, "updated": False}
        raise ReachError(UPSTREAM_BROKEN, f"could not install the OpenCLI extension: {exc}") from None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    update_state(extension_asset=asset["name"], extension_version=version)
    return {"version": version, "updated": True}


# ── process ──


def is_running() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", CDP_PORT)) == 0


def _detach_kwargs() -> dict:
    # Run from our own folder: `python -m` puts the cwd first on sys.path, so a stray
    # agent_reach/ folder where the user ran the command would shadow the installed package.
    root = browser_root()
    make_private_dir(root)
    if sys.platform == "win32":
        return {"cwd": str(root), "creationflags": subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    return {"cwd": str(root), "start_new_session": True}


def _launch(url: str, *, headless: bool = True) -> None:
    """Start the dedicated browser. Caller holds start_lock().

    The watcher launches Cloak through its public SDK on every OS. System
    Chrome fallback uses pipe loading on POSIX and Web Store loading on Windows.
    """
    from agent_reach.config import Config

    from .result import UPSTREAM_BROKEN, ReachError

    if is_running():
        raise ReachError(UPSTREAM_BROKEN, "The dedicated debugging port is already in use; no browser was changed")
    exe = ensure_chrome()
    _prepare_shared_profile()
    make_private_dir(profile_dir())
    from . import state as ledger
    ledger.remember_path(profile_dir(), "dedicated browser profile")
    for name in ("watcher.log", "session.json", "last_used", "watcher.lock", "start.lock", "session.lock"):
        ledger.remember_path(browser_root() / name, "browser lifecycle")
    update_state(started_at=time.time(), headless=headless)
    if not can_load_extension():
        subprocess.Popen(chrome_argv(exe, url, pipe=False, headless=headless), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **_detach_kwargs())
        if not wait_for(is_running, START_WAIT):
            raise ReachError(UPSTREAM_BROKEN, f"the Agent Reach browser did not open within {START_WAIT:.0f}s")
        _spawn_watcher()
        return
    if not extension_version():
        with contextlib.suppress(ReachError):
            refresh_extension()  # offline: open without it; the OpenCLI wait reports the problem
    # A watcher still exiting from the last browser holds its lock for a moment; the new one waits for it.
    with open(watcher_log_path(), "wb") as log:
        proc = subprocess.Popen(
            [_load_state().get("launcher_python") or sys.executable, "-m", "agent_reach.runtime.browser_watcher",
             "--launch", url, "--chrome", exe, *(["--cloak"] if _load_state().get("backend") == "cloakbrowser" else []),
             *([] if headless else ["--headed"])],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[2]),
                 "CLOAKBROWSER_AUTO_UPDATE": "false",
                 "REACH_BROWSER_PROXY": str(Config(read_only=True).get("proxy") or ""),
                 "CLOAKBROWSER_CACHE_DIR": str(browser_root().parent / "cloak-binaries")}, **_detach_kwargs(),
        )
    if not wait_for(lambda: is_running() or proc.poll() is not None, START_WAIT, interval=0.2) or not is_running():
        tail = ""
        with contextlib.suppress(OSError):
            tail = watcher_log_path().read_text("utf-8", "replace").strip().splitlines()[-1][:300]
        raise ReachError(UPSTREAM_BROKEN, "the Agent Reach browser did not open" + (f": {tail}" if tail else ""))


def _spawn_watcher() -> None:
    """Windows: start the detached idle watcher for an already-open browser unless one runs."""
    if watcher_running():
        return
    subprocess.Popen(
        [sys.executable, "-m", "agent_reach.runtime.browser_watcher"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **_detach_kwargs(),
    )
    # Hold start_lock until the watcher owns its lock, so a racing launch sees it.
    wait_for(watcher_running, 5.0, interval=0.1)


def _prepare_shared_profile() -> None:
    """Keep the old Chrome profile recoverable when changing browser engines."""
    selected = _load_state()
    if (selected.get("backend") != "cloakbrowser" or selected.get("profile_backend") == "cloakbrowser"
            or not profile_dir().is_dir()):
        return
    if not (browser_root() / "session.json").is_file() and _system_chrome():
        # An older Reach may have saved only Chrome's encrypted Cookie database.
        # Briefly open that Reach-owned profile to export it, never a personal profile.
        try:
            update_state(backend="chrome", executable=_system_chrome(), launcher_python=None)
            _launch("about:blank")
            save_session()
            stop()
        finally:
            update_state(backend=selected.get("backend"), executable=selected.get("executable"),
                         launcher_python=selected.get("launcher_python"))
    backup = browser_root() / ("profile-before-cloak-" + str(time.time_ns()))
    profile_dir().rename(backup)
    from . import state as ledger
    ledger.remember_path(backup, "previous dedicated profile backup")
    update_state(profile_backend="cloakbrowser", profile_backup=str(backup))


def _remaining_start_wait() -> float:
    """How long a browser that is open but not ready yet still gets."""
    started = _load_state().get("started_at") or 0.0
    return max(_RUNNING_GRACE, started + START_WAIT - time.time())


def _close_for_restart() -> None:
    from .result import UPSTREAM_BROKEN, ReachError
    if not stop() or not wait_for(lambda: not watcher_running(), 20.0, interval=0.1):
        raise ReachError(UPSTREAM_BROKEN, "Could not close the owned browser safely; saved profile retained")


def start(url: str = "about:blank") -> None:
    """Explicit human login: show a window using the same saved profile."""
    touch()
    with start_lock():
        if is_running():
            _require_owned()
            if not _load_state().get("headless", False):
                open_url(url)
                return
            _close_for_restart()
        _launch(url, headless=False)


def ensure_running(context: Optional[str] = None) -> None:
    """Prepare/reopen the shared browser; repair one lost Bridge connection."""
    from .clock import off_the_clock
    from .result import NEED_SETUP, UPSTREAM_BROKEN, ReachError
    if is_running():
        _require_owned()  # a visible login window is used as-is, never closed for a query
        own = dedicated_context()
        if own and own != bound_context() and own in connected_contexts():
            update_state(opencli_context=own)  # repair a record that points at another Chrome
            context = own
    if context is None:
        context = bound_context()
        if not context:
            setup()
            return
    touch()
    def ready():
        return is_running() and context in connected_contexts()
    if ready():
        return
    with off_the_clock():
        with start_lock():
            if can_load_extension() and is_running() and not watcher_running():
                stop()  # only a verified Reach-owned orphan may be replaced
            if not is_running():
                _launch("about:blank")
            if wait_for(ready, _remaining_start_wait()):
                touch()
                return
            if not is_running():
                raise ReachError(UPSTREAM_BROKEN, "The dedicated browser closed during startup")
            automatic = can_load_extension()
        if automatic:
            # setup owns its own lock; never recurse while holding start_lock.
            setup()
        else:
            raise ReachError(NEED_SETUP, "Enable the OpenCLI extension in the dedicated Chrome fallback",
                             hint="Run agent-reach browser setup; no website login has been requested.")
    touch()


def stop(timeout: float = 10.0) -> bool:
    """Close the dedicated browser: CDP Browser.close, then terminate. True if it is closed."""
    if not is_running():
        return True
    _require_owned()
    from . import cdp

    save_session()
    info = cdp.call("SystemInfo.getProcessInfo") or {}
    pid = next((p.get("id") for p in info.get("processInfo", []) if p.get("type") == "browser"), None)
    cdp.call("Browser.close")
    if wait_for(lambda: not is_running(), timeout, interval=0.2):
        return True
    if pid:
        with contextlib.suppress(OSError):
            os.kill(int(pid), signal.SIGTERM)
    return wait_for(lambda: not is_running(), 5.0, interval=0.2)


def open_url(url: str) -> None:
    """Open a new tab in the running dedicated browser."""
    _require_owned()
    req = urllib.request.Request(f"{CDP_URL}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback: never proxy
    with opener.open(req, timeout=5):
        pass


def _profile_pids() -> List[int]:
    """Processes started with our --user-data-dir (Chrome and its helpers)."""
    if sys.platform == "win32":
        return []
    try:
        out = subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    flag = f"--user-data-dir={profile_dir()}"
    pids = []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if pid.isdigit() and int(pid) != os.getpid() and (flag + " " in cmd + " "):
            pids.append(int(pid))
    return pids


def _require_owned() -> None:
    """Do not navigate or close an unrelated browser occupying our fixed port."""
    if not watcher_running() and not _profile_pids():
        from .result import NEED_SETUP, ReachError
        raise ReachError(NEED_SETUP, "Port 9222 belongs to an unmanaged browser; close that debugging session yourself first")


def save_session() -> None:
    """Serialize snapshot reads/writes with logout so an old snapshot cannot revive it."""
    with _locked(browser_root() / "session.lock", wait=5.0):
        _save_session_unlocked()


def _save_session_unlocked() -> None:
    from . import cdp
    result = cdp.call("Storage.getCookies")
    if result is not None:
        atomic_write_private_text(browser_root() / "session.json", json.dumps(result))


def restore_session() -> None:
    from . import cdp
    try:
        text = read_small_text_no_follow(browser_root() / "session.json", max_bytes=2 * 1024 * 1024)
        rows = json.loads(text or "{}").get("cookies", [])
    except (OSError, ValueError, PrivatePathError):
        return
    existing = cdp.call("Storage.getCookies")
    if existing is None:
        return
    keys = {(c["name"], c["domain"], c.get("path", "/")) for c in existing.get("cookies", [])}
    allowed = {"name", "value", "domain", "path", "secure", "httpOnly", "sameSite", "expires"}
    missing = [{k: v for k, v in row.items() if k in allowed} for row in rows
               if isinstance(row, dict) and row.get("name") and row.get("domain")
               and (row["name"], row["domain"], row.get("path", "/")) not in keys
               and isinstance(row.get("expires", -1), (int, float))
               and (row.get("expires", -1) <= 0 or row["expires"] > time.time())]
    if missing and cdp.call("Storage.setCookies", {"cookies": missing}) is None:
        from .result import UPSTREAM_BROKEN, ReachError
        raise ReachError(UPSTREAM_BROKEN, "Saved login could not be restored; the saved session was retained")
    update_state(restored_cookies=len(missing))


def clear_site(domains: List[str]) -> int:
    from .browser_binding import exclusive_browser
    with exclusive_browser():
        return _clear_site(domains)


def _clear_site(domains: List[str]) -> int:
    """Delete the dedicated browser's cookies for `domains` (and subdomains); returns how many.

    Opens the browser if it is closed; does nothing when it was never used.
    """
    if not domains or not (is_running() or profile_dir().is_dir()):
        return 0

    ensure_running()
    with _locked(browser_root() / "session.lock", wait=5.0):
        return _clear_running_site(domains)


def _clear_running_site(domains: List[str]) -> int:
    from . import cdp
    from .result import UPSTREAM_BROKEN, ReachError
    # Stop the removed site's open pages from refreshing its login in memory.
    targets = cdp._json("/json/list")
    cookies = cdp.call("Storage.getCookies")
    if not isinstance(targets, list) or cookies is None:
        raise ReachError(UPSTREAM_BROKEN, "Could not inspect site data; login cleanup is incomplete")
    pages = [t for t in targets if t.get("type") == "page"]
    closing = [t for t in pages if any(cdp.domain_matches(urllib.parse.urlsplit(t.get("url", "")).hostname or "", d) for d in domains)]
    page_origins = {urllib.parse.urlsplit(t["url"]).scheme + "://" + urllib.parse.urlsplit(t["url"]).netloc
                    for t in closing if urllib.parse.urlsplit(t["url"]).scheme in {"http", "https"}}
    visited = set(_load_state().get("visited_origins", []))
    page_origins |= {o for o in visited if any(cdp.domain_matches(urllib.parse.urlsplit(o).hostname or "", d) for d in domains)}
    if closing and len(closing) == len(pages):
        if cdp.call("Target.createTarget", {"url": "about:blank"}) is None:
            raise ReachError(UPSTREAM_BROKEN, "Could not retain the shared browser while logging out")
    for target in closing:
        if cdp.call("Target.closeTarget", {"targetId": target["id"]}) is None:
            raise ReachError(UPSTREAM_BROKEN, "Could not close the removed site's page")
    doomed = [c for c in cookies.get("cookies", [])
              if any(cdp.domain_matches(c.get("domain", ""), d) for d in domains)]
    keys = ("name", "domain", "path", "secure", "httpOnly", "sameSite", "partitionKey", "sourceScheme", "sourcePort")
    expired = [{**{k: c[k] for k in keys if k in c}, "value": "", "expires": 1} for c in doomed]
    if expired and cdp.call("Storage.setCookies", {"cookies": expired}) is None:
        from .result import UPSTREAM_BROKEN, ReachError
        raise ReachError(UPSTREAM_BROKEN, "Could not clear this site's cookies in the dedicated browser")
    hosts = {d.lstrip(".") for d in domains} | {c["domain"].lstrip(".") for c in doomed}
    # Include the site's conventional www origin even when no www cookie exists.
    hosts |= {"www." + d.lstrip(".") for d in domains}
    origins = page_origins | {scheme + h for h in hosts for scheme in ("https://", "http://")}
    for origin in origins:
        if cdp.call("Storage.clearDataForOrigin", {"origin": origin,
                    "storageTypes": "all"}, page=True) is None:
            raise ReachError(UPSTREAM_BROKEN, "Could not clear this site's browser storage; channel retained")
    _save_session_unlocked()
    after = cdp.call("Storage.getCookies")
    if after is None or any(any(cdp.domain_matches(c.get("domain", ""), d) for d in domains) for c in after.get("cookies", [])):
        raise ReachError(UPSTREAM_BROKEN, "Site login cleanup could not be verified; channel retained")
    update_state(visited_origins=sorted(visited - origins))
    left = {(c.get("name"), c.get("domain"), c.get("path")) for c in after.get("cookies", [])}
    return sum((c.get("name"), c.get("domain"), c.get("path")) not in left for c in doomed)


def delete_profile() -> bool:
    """Remove recorded browser artifacts only, preserving unknown files."""
    from . import state as ledger
    root = browser_root()
    if not root.exists():
        return False
    paths = [root.parent / n for n in ledger.load().get("owned_paths", {})
             if n.startswith("browser/") and ".." not in Path(n).parts]
    if not paths:
        return False
    if not stop():
        from .result import UPSTREAM_BROKEN, ReachError
        raise ReachError(UPSTREAM_BROKEN, "The dedicated browser could not close; its files were retained")
    wait_for(lambda: not watcher_running(), 20.0, interval=0.2)
    paths = [root.parent / n for n in ledger.load().get("owned_paths", {})
             if n.startswith("browser/") and ".." not in Path(n).parts]
    for path in sorted(paths, key=lambda p: len(p.parts), reverse=True):
        from agent_reach.utils.paths import ensure_no_symlink_path
        ensure_no_symlink_path(path.parent, "browser artifact parent")
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)
    try:
        root.rmdir()
    except OSError:
        pass
    return not root.exists()


# ── OpenCLI binding ──


def connected_contexts() -> List[str]:
    """OpenCLI Browser Bridge profiles connected right now."""
    from . import bridge

    current = bridge.require_compatible()
    return [p["contextId"] for p in current.get("profiles", []) if p.get("extensionConnected")]


def bound_context() -> Optional[str]:
    """The OpenCLI profile recorded as the dedicated browser, or None."""
    return _load_state().get("opencli_context") or None


# Key the OpenCLI extension uses to persist its profile id inside each browser profile.
_CONTEXT_ID_KEY = "opencli_context_id_v1"


def dedicated_context() -> Optional[str]:
    """The OpenCLI profile id saved inside the running dedicated browser, read over its own CDP port.

    Read from the dedicated profile itself, so another Chrome connecting at
    the same moment can never be mistaken for it.
    """
    if not is_running():
        return None
    from . import cdp

    return cdp.extension_value(_CONTEXT_ID_KEY)


def bind() -> dict:
    """Record the dedicated browser's OpenCLI profile once its extension is connected."""
    own = dedicated_context()
    if own and own in connected_contexts():
        if own != bound_context():
            update_state(opencli_context=own)
        return {"status": "ready", "context": own}
    return {"status": "waiting_for_extension"}


def setup(*, retry_cloak: bool = False, headless: bool = True) -> dict:
    """Make the dedicated browser ready with the OpenCLI extension loaded and bound; returns status().

    macOS/Linux: fully automatic. Windows: opens the Web Store page and waits for the user's click.
    Needs `opencli` installed (binding reads `opencli profile list`).
    """
    from .clock import off_the_clock

    with off_the_clock():
        if retry_cloak:
            ensure_chrome(retry_cloak=True)
        else:
            ensure_chrome()
        if not can_load_extension() and not bound_context():
            return _setup_from_store()
        if can_load_extension():
            refresh_extension()
        touch()
        with start_lock():
            state = _load_state()
            visible = is_running() and state.get("headless") is False
            if (is_running() and watcher_running() and state.get("running_backend") == state.get("backend")
                    and (state.get("headless") == headless or visible)):
                if bind()["status"] == "ready":
                    return status()
                if visible:
                    from .result import ReachError
                    raise ReachError("BUSY", "A login window is open in the Agent Reach browser",
                                     hint="Wait until the user says they finished logging in; do not close the window.")
            _close_for_restart()  # release profile and watcher before switching modes
            _launch("about:blank", headless=headless)

            def connected() -> bool:
                if not is_running() and not watcher_running():
                    from .result import UPSTREAM_BROKEN, ReachError
                    raise ReachError(UPSTREAM_BROKEN, "The dedicated browser exited before its extension connected",
                                     hint=f"Browser launch failed; inspect {watcher_log_path()}. No login was requested.")
                return bind()["status"] == "ready"

            if not wait_for(connected, _remaining_start_wait(), interval=0.5):
                from .result import UPSTREAM_BROKEN, ReachError

                raise ReachError(
                    UPSTREAM_BROKEN, "the OpenCLI extension did not connect to OpenCLI in the Agent Reach browser",
                    hint=f"Details: {watcher_log_path()}. Check `opencli profile list` works.",
                )
        touch()
        return status()


def _setup_from_store() -> dict:
    from agent_reach.backends.opencli import OPENCLI_EXTENSION_URL

    from .result import NEED_SETUP, ReachError

    touch()
    result = bind()
    if result["status"] == "waiting_for_extension":
        start(OPENCLI_EXTENSION_URL)
        found = wait_for(lambda: result.update(bind()) or result["status"] != "waiting_for_extension", _STORE_WAIT)
        if not found:
            raise ReachError(
                NEED_SETUP, "waiting for the OpenCLI extension in the Agent Reach browser",
                hint="Ask the user to click 'Add to Chrome' in the window that just opened, then run `agent-reach browser setup` again.",
            )
    if result["status"] != "ready":
        raise ReachError(NEED_SETUP, "waiting for the OpenCLI extension in the Agent Reach browser",
                         hint="Run `agent-reach browser setup` again after the extension is added.")
    return status()


def status() -> dict:
    ctx = bound_context()
    running = is_running()
    connected = None
    if ctx and running:
        try:
            connected = ctx in connected_contexts()
        except Exception:  # noqa: BLE001 - status must never raise
            connected = False
    return {
        "profile_dir": str(profile_dir()),
        "chrome": chrome_binary(),
        "backend": _load_state().get("backend"),
        "fallback_reason": _load_state().get("fallback_reason"),
        "extension_version": extension_version(),
        "running": running,
        "headless": _load_state().get("headless") if running else None,
        "opencli_context": ctx,
        "opencli_connected": connected,
        "idle_close_after_s": int(IDLE_LIMIT),
        "bridge_note": _load_state().get("bridge_note"),
    }


def setup_problems() -> List[str]:
    """What blocks browser-login channels right now (offline checks only).

    macOS/Linux set the browser up by themselves on first use, so nothing blocks there.
    """
    if not can_load_extension() and not bound_context():
        return ["Agent Reach browser not set up: run `agent-reach browser setup`"]
    return []
