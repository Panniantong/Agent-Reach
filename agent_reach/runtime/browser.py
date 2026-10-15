"""The Agent Reach dedicated browser.

A separate Chrome whose profile lives in ~/.agent-reach/browser/profile/, so
every browser login Agent Reach relies on stays under ~/.agent-reach/. The
user's own Chrome profiles and ~/.opencli settings are never touched.

Chrome: the system Google Chrome if there is one, else Chrome for Testing
(stable) under ~/.agent-reach/tools/chrome/ (`ensure_chrome`).

OpenCLI extension: the `opencli-extension-*.zip` of the latest OpenCLI GitHub
release, unpacked at ~/.agent-reach/browser/extension/ (a stable path, so the
extension id stays the same). Branded Chrome ignores `--load-extension`, so on
macOS/Linux the idle watcher (runtime.browser_watcher) launches Chrome with
`--remote-debugging-pipe --enable-unsafe-extension-debugging` and loads the
extension over that pipe with CDP `Extensions.loadUnpacked` on every launch
(it does not persist). Chrome exits when the pipe closes, so the watcher owns
the browser for its whole life. `setup()` then records which OpenCLI profile
is the dedicated browser (~/.agent-reach/browser/state.json); no user click.
Windows has no fd passing: the user adds the extension from the Web Store once.

Browser channels open it on demand (`ensure_running`). Every Agent Reach use
touches ~/.agent-reach/browser/last_used; the watcher closes the browser after
IDLE_LIMIT seconds without use.

Debugging is bound to 127.0.0.1:9222 only. Any local process that can reach
that port can control this browser; that is why it closes when idle.
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
import subprocess
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
CFT_VERSIONS_URL = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
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
    make_private_dir(browser_root())
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


# ── cross-process locks ──


def _open_lock(path: Path) -> int:
    make_private_dir(path.parent)
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


def _fetch(url: str, timeout: float = 30.0) -> bytes:
    """GET `url` (honours the OS / env proxy settings)."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _download(url: str, dest: Path, timeout: float = 60.0) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out, 1 << 20)


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
    candidates = []
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


def _cft_dir() -> Path:
    from . import tools

    return tools.tool_dir("chrome")


def _cft_platform() -> Optional[str]:
    system, machine = platform.system(), platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if system == "Darwin":
        return "mac-arm64" if arm else "mac-x64"
    if system == "Windows":
        return "win64" if sys.maxsize > 2**32 else "win32"
    if system == "Linux":
        return "linux-arm64" if arm else "linux64"
    return None


def _cft_binary(plat: Optional[str] = None) -> Path:
    plat = plat or _cft_platform() or ""
    base = _cft_dir() / f"chrome-{plat}"
    if plat.startswith("mac"):
        return base / "Google Chrome for Testing.app" / "Contents" / "MacOS" / "Google Chrome for Testing"
    if plat.startswith("win"):
        return base / "chrome.exe"
    return base / "chrome"


def chrome_binary() -> Optional[str]:
    """System Google Chrome, else our Chrome for Testing if installed, else None (never downloads)."""
    system = _system_chrome()
    if system:
        return system
    cft = _cft_binary()
    return str(cft) if _cft_platform() and cft.exists() else None


def ensure_chrome() -> str:
    """Path to a Chrome binary, installing Chrome for Testing (stable) when the system has no Chrome."""
    from .result import NEED_SETUP, UPSTREAM_BROKEN, ReachError

    found = chrome_binary()
    if found:
        return found
    plat = _cft_platform()
    if not plat:
        raise ReachError(NEED_SETUP, f"no Chrome build for {platform.system()} {platform.machine()}",
                         hint="Ask the user to install Google Chrome.")
    try:
        stable = json.loads(_fetch(CFT_VERSIONS_URL))["channels"]["Stable"]
        version = stable["version"]
        url = next(d["url"] for d in stable["downloads"]["chrome"] if d["platform"] == plat)
    except Exception as exc:  # noqa: BLE001
        raise ReachError(UPSTREAM_BROKEN, f"could not look up Chrome for Testing: {exc}") from None
    dest = _cft_dir()
    dest.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".chrome-", dir=dest.parent))
    try:
        archive = work / "chrome.zip"
        _download(url, archive, timeout=120)
        unpacked = work / "unpacked"
        unpacked.mkdir()
        _unzip(archive, unpacked)
        archive.unlink()
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(unpacked, dest)
    except Exception as exc:  # noqa: BLE001
        raise ReachError(UPSTREAM_BROKEN, f"could not install Chrome for Testing: {exc}") from None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    exe = _cft_binary(plat)
    if not exe.exists():
        raise ReachError(UPSTREAM_BROKEN, "Chrome for Testing download did not contain a browser")
    from . import tools

    record = getattr(tools, "record", None)
    if record:
        record("chrome", version)
    return str(exe)


def can_load_extension() -> bool:
    """macOS/Linux: the watcher loads the extension over the launch pipe. Windows: Web Store only."""
    return sys.platform != "win32"


def chrome_argv(exe: str, url: str, *, pipe: bool) -> List[str]:
    argv = [
        exe,
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile_dir()}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
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


def refresh_extension() -> dict:
    """Install or update the OpenCLI extension from the latest OpenCLI release.

    Keeps the current copy when GitHub is unreachable; raises only if there is none.
    Returns {"version", "updated"}. A running browser is closed before files change.
    """
    from .result import UPSTREAM_BROKEN, ReachError

    current = extension_version()
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
    make_private_dir(browser_root())
    work = Path(tempfile.mkdtemp(prefix=".extension-", dir=browser_root()))
    try:
        archive = work / "extension.zip"
        _download(asset["browser_download_url"], archive)
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


def _launch(url: str) -> None:
    """Start the dedicated browser. Caller holds start_lock().

    macOS/Linux: the watcher launches Chrome (it must own the pipe). Windows:
    Chrome is started here and the watcher only watches.
    """
    from .result import UPSTREAM_BROKEN, ReachError

    exe = ensure_chrome()
    make_private_dir(profile_dir())
    update_state(started_at=time.time())
    if not can_load_extension():
        subprocess.Popen(chrome_argv(exe, url, pipe=False), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
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
            [sys.executable, "-m", "agent_reach.runtime.browser_watcher", "--launch", url, "--chrome", exe],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, **_detach_kwargs(),
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


def _remaining_start_wait() -> float:
    """How long a browser that is open but not ready yet still gets."""
    started = _load_state().get("started_at") or 0.0
    return max(_RUNNING_GRACE, started + START_WAIT - time.time())


def start(url: str = "about:blank") -> None:
    """Show `url` in the dedicated browser, launching it if needed (login)."""
    touch()
    if is_running():
        open_url(url)
        return
    with start_lock():
        if is_running():
            open_url(url)
            return
        _launch(url)


def ensure_running(context: Optional[str] = None) -> None:
    """Make the dedicated browser ready for an action, launching it if needed.

    With `context`, also wait until that OpenCLI profile is connected. A browser
    left open without its watcher (so without the extension) is relaunched.
    The wait does not count against the action's --timeout.
    Raises ReachError when it is not ready within START_WAIT.
    """
    from .clock import off_the_clock
    from .result import NEED_SETUP, UPSTREAM_BROKEN, ReachError

    touch()

    def ready() -> bool:
        return is_running() and (context is None or context in connected_contexts())

    if ready():
        return
    with off_the_clock(), start_lock():
        if context and can_load_extension() and is_running() and not watcher_running():
            stop()  # an orphan from an older Agent Reach: reopen it with the extension
        if not is_running():
            _launch("about:blank")
        if not wait_for(ready, _remaining_start_wait()):
            if not is_running():
                raise ReachError(UPSTREAM_BROKEN, "the Agent Reach browser closed while starting")
            if can_load_extension():
                raise ReachError(
                    UPSTREAM_BROKEN, "the Agent Reach browser is running but OpenCLI is not connected to it",
                    hint="Run `agent-reach browser setup` once; if it fails the same way, OpenCLI itself is broken.",
                )
            raise ReachError(
                NEED_SETUP, "the Agent Reach browser is running but OpenCLI is not connected to it",
                hint="Ask the user to check the OpenCLI extension is enabled in the Agent Reach browser window.",
            )
    touch()


def stop(timeout: float = 10.0) -> bool:
    """Close the dedicated browser: CDP Browser.close, then terminate. True if it is closed."""
    if not is_running():
        return True
    from . import cdp

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


def clear_site(domains: List[str]) -> int:
    """Delete the dedicated browser's cookies for `domains` (and subdomains); returns how many.

    Opens the browser if it is closed; does nothing when it was never used.
    """
    if not domains or not (is_running() or profile_dir().is_dir()):
        return 0
    from . import cdp

    ensure_running()
    doomed = [c for c in (cdp.call("Storage.getCookies") or {}).get("cookies", [])
              if any(cdp.domain_matches(c.get("domain", ""), d) for d in domains)]
    if not doomed:
        return 0
    keys = ("name", "domain", "path", "secure", "httpOnly", "sameSite", "partitionKey", "sourceScheme", "sourcePort")
    expired = [{**{k: c[k] for k in keys if k in c}, "value": "", "expires": 1} for c in doomed]
    cdp.call("Storage.setCookies", {"cookies": expired})
    left = {(c.get("name"), c.get("domain"), c.get("path")) for c in (cdp.call("Storage.getCookies") or {}).get("cookies", [])}
    return sum((c.get("name"), c.get("domain"), c.get("path")) not in left for c in doomed)


def delete_profile() -> bool:
    """Close the dedicated browser and remove ~/.agent-reach/browser/. True if something was removed."""
    root = browser_root()
    if not root.exists():
        return False
    with contextlib.suppress(Exception), start_lock(wait=15.0):
        stop()
        pids = _profile_pids()
        for pid in pids:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGTERM)
        if not wait_for(lambda: not _profile_pids(), 5.0, interval=0.2):
            for pid in _profile_pids():
                with contextlib.suppress(OSError):
                    if sys.platform != "win32":
                        os.kill(pid, signal.SIGKILL)
                    else:
                        os.kill(pid, signal.SIGTERM)
        wait_for(lambda: not watcher_running(), 20.0, interval=0.2)
    shutil.rmtree(root, ignore_errors=True)
    return not root.exists()


# ── OpenCLI binding ──


def connected_contexts() -> List[str]:
    """OpenCLI Browser Bridge profiles connected right now."""
    from .run import run_cmd

    out = run_cmd(["opencli", "profile", "list"], timeout=20)
    return _CONTEXT_RE.findall(out)


def bound_context() -> Optional[str]:
    """The OpenCLI profile recorded as the dedicated browser, or None."""
    return _load_state().get("opencli_context") or None


def bind() -> dict:
    """Record which OpenCLI profile is the dedicated browser (Windows Web Store flow).

    The first call snapshots profiles already connected (the user's own
    Chrome). After the user installs the extension in the dedicated window,
    the next call finds exactly one new profile and records it.
    """
    state = _load_state()
    now = connected_contexts()
    if state.get("opencli_context") in now:
        return {"status": "ready", "context": state["opencli_context"]}
    if "baseline" not in state:
        state["baseline"] = now
        _save_state(state)
    new = [c for c in now if c not in state["baseline"]]
    if len(new) == 1:
        state["opencli_context"] = new[0]
        _save_state(state)
        return {"status": "ready", "context": new[0]}
    if len(new) > 1:
        return {"status": "ambiguous", "candidates": new}
    return {"status": "waiting_for_extension"}


def _ambiguous(candidates: List[str]):
    from .result import NEED_SETUP, ReachError

    return ReachError(
        NEED_SETUP, f"more than one new OpenCLI profile connected: {', '.join(candidates)}",
        hint="Ask the user to close other Chrome windows that have the OpenCLI extension, then run setup again.",
    )


def setup() -> dict:
    """Make the dedicated browser ready with the OpenCLI extension loaded and bound; returns status().

    macOS/Linux: fully automatic. Windows: opens the Web Store page and waits for the user's click.
    Needs `opencli` installed (binding reads `opencli profile list`).
    """
    from .clock import off_the_clock

    with off_the_clock():
        ensure_chrome()
        if not can_load_extension():
            return _setup_from_store()
        refresh_extension()
        touch()
        with start_lock():
            ctx = bound_context()
            if ctx and is_running() and watcher_running() and ctx in connected_contexts():
                return status()
            stop()  # (re)launch so this browser connects fresh and we can tell it apart
            if ctx:  # let OpenCLI notice the old connection is gone before taking the snapshot
                wait_for(lambda: ctx not in connected_contexts(), 10.0)
            baseline = connected_contexts()
            _launch("about:blank")
            found: List[str] = []

            def new_context() -> bool:
                found[:] = [c for c in connected_contexts() if c not in baseline]
                return len(found) == 1

            if not wait_for(new_context, _remaining_start_wait(), interval=0.5):
                from .result import UPSTREAM_BROKEN, ReachError

                if found:
                    raise _ambiguous(found)
                raise ReachError(
                    UPSTREAM_BROKEN, "the OpenCLI extension did not connect to OpenCLI in the Agent Reach browser",
                    hint=f"Details: {watcher_log_path()}. Check `opencli profile list` works.",
                )
            update_state(opencli_context=found[0], baseline=None)
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
    if result["status"] == "ambiguous":
        raise _ambiguous(result["candidates"])
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
        "extension_version": extension_version(),
        "running": running,
        "opencli_context": ctx,
        "opencli_connected": connected,
        "idle_close_after_s": int(IDLE_LIMIT),
    }


def setup_problems() -> List[str]:
    """What blocks browser-login channels right now (offline checks only).

    macOS/Linux set the browser up by themselves on first use, so nothing blocks there.
    """
    if not can_load_extension() and not bound_context():
        return ["Agent Reach browser not set up: run `agent-reach browser setup`"]
    return []
