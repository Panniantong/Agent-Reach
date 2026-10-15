"""Upstream tools and machine prerequisites Agent Reach installs, at their latest allowed version.

Versions are not pinned. Each tool may set `floor` (oldest version we accept)
and `exclude` (known-bad versions, added in a release when an upstream breaks);
the install asks the package manager for the newest version inside those limits.
state.json records the version actually installed.

Kinds:
- pip / npm: private, under ~/.agent-reach/tools/<name>/ (own venv or npm
  prefix). Never on the user's PATH; the user's own copy, if any, is untouched.
- singleton (npm): can only exist once per machine (OpenCLI owns a fixed daemon
  port and a Chrome extension). A user copy inside the limits is used as is; an
  out-of-limits user copy is upgraded only with explicit consent; when missing
  it is installed into ~/.agent-reach/tools/npm-global/ and recorded as ours.
- prerequisites (node, uv, ffmpeg, chrome): the system copy is used when there
  is one; otherwise a private copy is installed without an admin password.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from . import state
from .result import NEED_SETUP, UPSTREAM_BROKEN, ReachError

OURS = "agent-reach"


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str                       # "pip" | "npm" | "ffmpeg" | "node" | "uv" | "chrome"
    package: str                    # pip requirement / npm package name ("" for prerequisites)
    commands: Tuple[str, ...]       # executables it provides
    singleton: bool = False
    floor: str = ""                 # oldest acceptable version
    exclude: Tuple[str, ...] = ()   # known-bad versions
    needs: Tuple[str, ...] = ()     # tools that must be installed first


TOOLS: Dict[str, Tool] = {
    t.name: t
    for t in (
        Tool("bili-cli", "pip", "bilibili-cli", ("bili",)),
        Tool(
            "boss-agent-cli", "pip",
            "boss-agent-cli @ https://github.com/can4hou6joeng4/boss-agent-cli/archive/HEAD.zip",
            ("boss",),
        ),
        Tool("mcporter", "npm", "mcporter", ("mcporter",), needs=("node",)),
        Tool("opencli", "npm", "@jackwener/opencli", ("opencli",), singleton=True, floor="1.8.6", needs=("node",)),
        Tool("ffmpeg", "ffmpeg", "imageio-ffmpeg", ("ffmpeg",)),
        Tool("node", "node", "", ("node", "npm", "npx")),
        Tool("uv", "uv", "", ("uv", "uvx")),
        Tool("chrome", "chrome", "", ()),
    )
}

#: Command name → tool, for resolving executables.
_BY_COMMAND = {c: t for t in TOOLS.values() for c in t.commands}

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_WIN = sys.platform == "win32"


def tools_root() -> Path:
    return state.root() / "tools"


def tool_dir(name: str) -> Path:
    return tools_root() / name


def npm_global_dir() -> Path:
    """Prefix for singletons we install (`npm -g --prefix`): no admin rights needed."""
    return tools_root() / "npm-global"


def _exe(name: str) -> str:
    return name + (".exe" if _WIN else "")


def _node_bin_dir() -> Path:
    base = tool_dir("node") / "current"
    return base if _WIN else base / "bin"


def _npm_global_bin() -> Path:
    return npm_global_dir() if _WIN else npm_global_dir() / "bin"


def _private_bin(tool: Tool, command: str) -> Path:
    base = tool_dir(tool.name)
    if tool.kind == "pip":
        return base / "venv" / ("Scripts" if _WIN else "bin") / _exe(command)
    if tool.kind == "npm":
        return base / "node_modules" / ".bin" / (command + (".cmd" if _WIN else ""))
    if tool.kind == "node":
        return _node_bin_dir() / (command + (".cmd" if _WIN and command != "node" else ".exe" if _WIN else ""))
    if tool.kind in ("uv", "ffmpeg"):
        return base / "bin" / _exe(command)
    return base / command


def bin_dirs() -> List[Path]:
    """Private bin folders that exist (node, our npm -g prefix, uv, ffmpeg)."""
    dirs = [_node_bin_dir(), _npm_global_bin(), tool_dir("uv") / "bin", tool_dir("ffmpeg") / "bin"]
    return [d for d in dirs if d.is_dir()]


def extend_path() -> None:
    """Append our private bin folders to PATH (system copies still win), so that
    upstream scripts find node/uvx/ffmpeg and children we start inherit them."""
    parts = os.environ.get("PATH", "").split(os.pathsep)
    extra = [str(d) for d in bin_dirs() if str(d) not in parts]
    if extra:
        os.environ["PATH"] = os.pathsep.join([p for p in parts if p] + extra)


def resolve(command: str) -> Optional[str]:
    """Absolute path for `command`: our private copy first, then the user's PATH."""
    tool = _BY_COMMAND.get(command)
    if tool and not tool.singleton:
        private = _private_bin(tool, command)
        if private.exists():
            return str(private)
    found = shutil.which(command)
    if found or not tool or not tool.singleton:
        return found
    ours = _npm_global_bin() / (command + (".cmd" if _WIN else ""))
    return str(ours) if ours.exists() else None


def ffmpeg_path() -> Optional[str]:
    return resolve("ffmpeg")


def present(name: str) -> bool:
    """Is the tool usable right now (ours or the system's)? Offline."""
    tool = TOOLS[name]
    if tool.kind == "chrome":
        from .browser import chrome_binary

        return chrome_binary() is not None
    return all(resolve(c) for c in tool.commands)


# ── versions ──

def _version_tuple(text: str) -> tuple:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else ()


def allowed(tool: Tool, version: Optional[str]) -> bool:
    v = _version_tuple(version or "")
    if not v:
        return False
    if tool.floor and v < _version_tuple(tool.floor):
        return False
    return not any(v == _version_tuple(x) for x in tool.exclude)


def install_spec(tool: Tool) -> str:
    """What the package manager is asked for: the newest version inside floor/exclude."""
    if tool.kind in ("pip", "ffmpeg"):
        cons = ([f">={tool.floor}"] if tool.floor else []) + [f"!={x}" for x in tool.exclude]
        if " @ " in tool.package or not cons:
            return tool.package
        return tool.package + ",".join(cons)
    # npm: a range made of the gaps between excluded versions
    bad = sorted(set(tool.exclude), key=_version_tuple)
    lower, parts = f">={tool.floor}" if tool.floor else ">=0.0.0", []
    for x in bad:
        parts.append(f"{lower} <{x}")
        lower = f">{x}"
    parts.append(lower)
    rng = " || ".join(parts)
    return tool.package if rng == ">=0.0.0" else f"{tool.package}@{rng}"


def _dist_name(tool: Tool) -> str:
    return re.split(r"[\s@<>=!~\[;]", tool.package, 1)[0]


def _pip_version(tool: Tool) -> Optional[str]:
    want = re.sub(r"[-_.]+", "_", _dist_name(tool)).lower()
    venv = tool_dir(tool.name) / "venv"
    sites = [venv / "Lib" / "site-packages"] if _WIN else sorted((venv / "lib").glob("python*/site-packages"))
    for site in sites:
        for d in site.glob("*.dist-info"):
            name, _, ver = d.name[: -len(".dist-info")].partition("-")
            if re.sub(r"[-_.]+", "_", name).lower() == want:
                return ver
    return None


def _npm_version(prefix: Path, package: str) -> Optional[str]:
    """Version from package.json under a local prefix (node_modules) or an -g prefix (lib/node_modules)."""
    for base in (prefix / "node_modules", prefix / "lib" / "node_modules"):
        try:
            return json.loads((base / package / "package.json").read_text("utf-8")).get("version")
        except (OSError, ValueError):
            continue
    return None


def _command_version(exe: Optional[str]) -> Optional[str]:
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"\d+\.\d+\.\d+", out.stdout + out.stderr)
    return m.group(0) if m else None


def installed_version(tool: Tool) -> Optional[str]:
    """Version of the copy `resolve` would use (singletons: whichever is on PATH)."""
    return _command_version(resolve(tool.commands[0]))


def _private_version(tool: Tool) -> Optional[str]:
    if tool.kind in ("pip", "ffmpeg"):
        return _pip_version(tool)
    if tool.kind == "npm":
        return _npm_version(tool_dir(tool.name), tool.package)
    return _command_version(str(_private_bin(tool, tool.commands[0])))


# ── installing ──

def _install_env() -> dict:
    """pip and npm only read proxy env vars; hand them the OS proxy (e.g. the macOS system proxy) when none is set."""
    extend_path()
    env = dict(os.environ)
    if not (env.get("HTTPS_PROXY") or env.get("https_proxy")):
        found = urllib.request.getproxies()
        proxy = found.get("https") or found.get("http")
        if proxy:
            env["HTTPS_PROXY"] = env["HTTP_PROXY"] = proxy
    return env


def _run(argv, timeout: float = 600, env: Optional[dict] = None) -> str:
    run_env = _install_env()
    run_env.update(env or {})
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=run_env)
    except FileNotFoundError:
        raise ReachError(NEED_SETUP, f"{Path(argv[0]).name} is not installed") from None
    except subprocess.TimeoutExpired:
        raise ReachError(UPSTREAM_BROKEN, f"installing timed out: {' '.join(map(str, argv[:3]))}") from None
    if proc.returncode != 0:
        last = next((ln for ln in reversed(proc.stderr.splitlines()) if ln.strip()), "")
        raise ReachError(UPSTREAM_BROKEN, f"install failed: {last[:300]}")
    return proc.stdout


def _download(url: str, dest: Path, timeout: float = 600) -> None:
    proxy = _install_env().get("HTTPS_PROXY")
    handlers = [urllib.request.ProxyHandler({"https": proxy, "http": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": "agent-reach"})
    try:
        with opener.open(req, timeout=60) as resp, open(dest, "wb") as fh:
            shutil.copyfileobj(resp, fh, 1024 * 1024)
    except OSError as exc:
        raise ReachError(UPSTREAM_BROKEN, f"download failed: {url}: {exc}") from None


def _install_pip(tool: Tool) -> None:
    venv = tool_dir(tool.name) / "venv"
    shutil.rmtree(venv, ignore_errors=True)
    venv.parent.mkdir(parents=True, exist_ok=True)
    _run([sys.executable, "-m", "venv", str(venv)])
    py = venv / ("Scripts/python.exe" if _WIN else "bin/python")
    _run([str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", install_spec(tool)])
    if tool.kind == "ffmpeg":
        exe = _run([str(py), "-c", "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"]).strip()
        link = _private_bin(tool, "ffmpeg")
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.exists() or link.is_symlink():
            link.unlink()
        try:
            link.symlink_to(exe)
        except (OSError, NotImplementedError):
            shutil.copy2(exe, link)


def _npm_cmd() -> str:
    npm = resolve("npm")
    if not npm:
        raise ReachError(NEED_SETUP, "npm is not installed", hint="Run `agent-reach add <channel>` again.")
    return npm


def _install_npm(tool: Tool, *, global_prefix: Optional[Path] = None, system_global: bool = False) -> None:
    npm = _npm_cmd()
    spec = install_spec(tool)
    if system_global:
        _run([npm, "install", "-g", spec])
    elif global_prefix is not None:
        global_prefix.mkdir(parents=True, exist_ok=True)
        _run([npm, "install", "-g", "--prefix", str(global_prefix), "--no-fund", "--no-audit", spec])
    else:
        prefix = tool_dir(tool.name)
        prefix.mkdir(parents=True, exist_ok=True)
        _run([npm, "install", "--prefix", str(prefix), "--no-fund", "--no-audit", spec])


def _node_platform() -> Tuple[str, str, str]:
    """(os, arch, archive extension) in nodejs.org naming."""
    system = platform.system()
    os_name = {"Darwin": "darwin", "Linux": "linux", "Windows": "win"}.get(system)
    machine = platform.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if not os_name or not arch:
        raise ReachError(NEED_SETUP, f"no official Node.js build for {system} {machine}",
                         hint="Ask the user to install Node.js from https://nodejs.org.")
    return os_name, arch, "zip" if os_name == "win" else "tar.gz"


def _install_node(tool: Tool) -> None:
    import hashlib
    import tarfile
    import zipfile

    os_name, arch, ext = _node_platform()
    with tempfile.TemporaryDirectory(prefix="agent-reach-node-") as tmp:
        index = Path(tmp) / "index.json"
        _download("https://nodejs.org/dist/index.json", index)
        key = {"darwin": f"osx-{arch}-tar", "linux": f"linux-{arch}", "win": f"win-{arch}-zip"}[os_name]
        try:
            release = next(r for r in json.loads(index.read_text("utf-8")) if r.get("lts") and key in r.get("files", []))
        except (StopIteration, ValueError):
            raise ReachError(UPSTREAM_BROKEN, "could not find a Node.js LTS release for this machine") from None
        version = release["version"]
        if _command_version(str(_private_bin(tool, "node"))) == version.lstrip("v"):
            return  # already the latest LTS
        stem = f"node-{version}-{os_name}-{arch}"
        archive = Path(tmp) / f"{stem}.{ext}"
        base = f"https://nodejs.org/dist/{version}"
        _download(f"{base}/{archive.name}", archive)
        sums = Path(tmp) / "SHASUMS256.txt"
        _download(f"{base}/SHASUMS256.txt", sums)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if f"{digest}  {archive.name}" not in sums.read_text("utf-8"):
            raise ReachError(UPSTREAM_BROKEN, f"checksum mismatch for {archive.name}")
        out = Path(tmp) / "x"
        if ext == "zip":
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(out)
        else:
            with tarfile.open(archive) as tf:
                if hasattr(tarfile, "data_filter"):
                    tf.extractall(out, filter="data")
                else:  # pragma: no cover - Python < 3.12 without the filter backport
                    tf.extractall(out)
        dest = tool_dir("node")
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        shutil.move(str(out / stem), str(dest / "current"))


def _install_uv(tool: Tool) -> None:
    dest = tool_dir("uv") / "bin"
    env = {"UV_INSTALL_DIR": str(dest), "UV_NO_MODIFY_PATH": "1", "INSTALLER_NO_MODIFY_PATH": "1"}
    if _WIN:
        _run(["powershell", "-ExecutionPolicy", "ByPass", "-c", "irm https://astral.sh/uv/install.ps1 | iex"], env=env)
    else:
        with tempfile.TemporaryDirectory(prefix="agent-reach-uv-") as tmp:
            script = Path(tmp) / "install.sh"
            _download("https://astral.sh/uv/install.sh", script)
            _run(["sh", str(script)], env=env)
    nested = dest / "bin"  # older installers add a bin/ below UV_INSTALL_DIR
    if nested.is_dir():
        for f in nested.iterdir():
            shutil.move(str(f), str(dest / f.name))
        nested.rmdir()
    if not _private_bin(tool, "uvx").exists():
        raise ReachError(UPSTREAM_BROKEN, "the uv installer finished but uvx is missing")


def _install(tool: Tool, *, global_: bool = False) -> None:
    """Install (or upgrade) one tool. Singletons: global_=True (our npm -g prefix)."""
    if tool.kind in ("pip", "ffmpeg"):
        _install_pip(tool)
    elif tool.kind == "npm":
        _install_npm(tool, global_prefix=npm_global_dir() if global_ else None)
    elif tool.kind == "node":
        _install_node(tool)
    elif tool.kind == "uv":
        _install_uv(tool)
    else:
        raise ReachError(UPSTREAM_BROKEN, f"no installer for {tool.name}")
    extend_path()


def _upgrade_user_singleton(tool: Tool) -> None:
    """Upgrade the user's own global copy in place (only with consent)."""
    _install_npm(tool, system_global=True)


def record(name: str, version: Optional[str], *, owner: str = OURS, scope: str = "private", **extra) -> dict:
    """Record a tool in state.json (also used by browser.ensure_chrome for Chrome for Testing)."""
    data = state.load()
    entry = {"owner": owner, "scope": scope, "version": version, **extra}
    data["tools"][name] = entry
    state.save(data)
    return {"tool": name, **entry}


def ensure(name: str, *, allow_upgrade: bool = False, upgrade: bool = False) -> dict:
    """Make sure the tool is installed inside its limits; record it in state.

    `upgrade`: reinstall our private copy at the latest allowed version (update/sync).
    Returns {"tool", "owner", "scope", "version"}; owner "system" = not ours, not recorded.
    """
    tool = TOOLS[name]
    for dep in tool.needs:
        ensure(dep)  # callers that upgrade list the dependency themselves (manage.sync)
    entry = state.load()["tools"].get(name) or {}
    ours = entry.get("owner") == OURS

    if tool.kind == "chrome":
        from . import browser

        browser.ensure_chrome()
        entry = state.load()["tools"].get(name)
        if entry:
            return {"tool": name, **entry}
        return {"tool": name, "owner": "system", "scope": "system", "version": None}

    if tool.singleton:
        current = installed_version(tool)
        if current is None:
            _install(tool, global_=True)
            return record(name, installed_version(tool), scope="global", prefix=str(npm_global_dir()))
        if allowed(tool, current) and not (upgrade and ours):
            if not entry:
                return record(name, current, owner="user", scope="global")
            if entry.get("version") != current:
                return record(name, current, **{k: v for k, v in entry.items() if k != "version"})
            return {"tool": name, **entry}
        if ours:
            if entry.get("prefix"):
                _install(tool, global_=True)
            else:
                _upgrade_user_singleton(tool)
            return record(name, installed_version(tool), **{k: v for k, v in entry.items() if k != "version"})
        if not allow_upgrade:
            raise ReachError(
                NEED_SETUP,
                f"{name} {current} is outside the supported versions (needs >= {tool.floor or 'any'}"
                + (f", not {', '.join(tool.exclude)}" if tool.exclude else "") + ")",
                hint=f"Ask the user whether to upgrade their {name}; if yes, rerun with --allow-upgrade.",
            )
        _upgrade_user_singleton(tool)
        return record(name, installed_version(tool), owner=entry.get("owner", "user"), scope="global")

    private_ok = all(_private_bin(tool, c).exists() for c in tool.commands)
    if tool.kind in ("node", "uv", "ffmpeg") and not private_ok and all(shutil.which(c) for c in tool.commands):
        return {"tool": name, "owner": "system", "scope": "system", "version": None}
    if not private_ok or not ours or upgrade:
        _install(tool)
    elif entry.get("version"):
        return {"tool": name, **entry}
    # fresh install, or a record from an older Agent Reach without a version
    return record(name, _private_version(tool))


# ── removing ──

def _uninstall_global(name: str, entry: dict, dry_run: bool) -> Optional[str]:
    """Uninstall a singleton we installed. Returns a description, or None if not ours."""
    tool = TOOLS.get(name)
    if not tool or not tool.singleton or entry.get("owner") != OURS:
        return None
    prefix = entry.get("prefix")
    desc = f"npm -g {tool.package}" + (f" (in {prefix})" if prefix else "")
    npm = resolve("npm")
    if not dry_run and npm:
        argv = [npm, "uninstall", "-g"] + (["--prefix", prefix] if prefix else []) + [tool.package]
        try:
            subprocess.run(argv, capture_output=True, timeout=300, env=_install_env())
        except (OSError, subprocess.TimeoutExpired):
            pass
    return desc


def remove_private(name: str) -> bool:
    """Delete one of our installs and its record. User/system copies are never touched."""
    data = state.load()
    entry = data["tools"].get(name)
    tool = TOOLS.get(name)
    if tool and tool.singleton:
        if entry is None:
            return False
        if entry.get("owner") == OURS:
            _uninstall_global(name, entry, dry_run=False)
        data["tools"].pop(name, None)
        state.save(data)
        return entry.get("owner") == OURS
    if entry is not None and entry.get("owner") not in (None, OURS):
        return False
    removed = data["tools"].pop(name, None) is not None
    if _SAFE_NAME.match(name) and tool_dir(name).exists():
        shutil.rmtree(tool_dir(name))
        removed = True
    state.save(data)
    return removed


def closure(names: Iterable[str]) -> Set[str]:
    """The tools plus everything they need."""
    out: Set[str] = set()
    todo = [n for n in names if n in TOOLS]
    while todo:
        n = todo.pop()
        if n not in out:
            out.add(n)
            todo.extend(TOOLS[n].needs)
    return out


def prune(keep: Set[str]) -> List[str]:
    """Remove our tools not in `keep` (and drop records of user copies no channel uses)."""
    removed = []
    for name, entry in list(state.load()["tools"].items()):
        if name in keep:
            continue
        if entry.get("owner") != OURS:
            data = state.load()
            data["tools"].pop(name, None)
            state.save(data)
            continue
        if name not in TOOLS and not _SAFE_NAME.match(name):
            continue
        if name == "chrome":
            from . import browser

            browser.stop()
        if remove_private(name):
            removed.append(name)
    return removed


def uninstall_global_owned(dry_run: bool) -> list:
    """Global singletons we installed (owner agent-reach); uninstall them."""
    out = []
    for name, entry in state.load()["tools"].items():
        desc = _uninstall_global(name, entry, dry_run)
        if desc:
            out.append(desc)
    return out


def recorded() -> List[dict]:
    """Every tool in state.json with its installed version (for doctor)."""
    return [{"tool": n, **e} for n, e in sorted(state.load()["tools"].items())]
