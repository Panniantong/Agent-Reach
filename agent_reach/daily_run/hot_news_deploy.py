# -*- coding: utf-8
"""Self-hosted 60s API deployment for daily-run hot news (native Node or Docker)."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Literal, Optional

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run")

DeployMode = Literal["native", "docker", "auto", "skip"]

REPO_URL = "https://github.com/vikiboss/60s.git"
CONTAINER_NAME = "agent-reach-60s"
IMAGE = "vikiboss/60s:latest"
HOST_PORT = 8787
CONTAINER_PORT = 4399
LOCAL_BASE_URL = f"http://127.0.0.1:{HOST_PORT}"
MIN_NODE_MAJOR = 22
MIN_NODE_MINOR = 6


def vendor_dir() -> Path:
    return Path.home() / ".agent-reach" / "vendor" / "60s-api"


def pid_file() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "60s.pid"


def log_file() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "logs" / "60s.log"


def docker_path() -> Optional[str]:
    return shutil.which("docker")


def _user_local_bin(name: str) -> Optional[str]:
    candidate = Path.home() / ".local" / "node" / "bin" / name
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


def node_path() -> Optional[str]:
    return _user_local_bin("node") or shutil.which("node")


def npm_path() -> Optional[str]:
    return _user_local_bin("npm") or shutil.which("npm")


def git_path() -> Optional[str]:
    return shutil.which("git")


def _parse_node_version(raw: str) -> tuple[int, int, int]:
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", raw.strip())
    if not match:
        return 0, 0, 0
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def node_version_ok() -> tuple[bool, str]:
    node = node_path()
    if not node:
        return False, "node not found on PATH (60s native deploy needs Node.js 22.6+)"
    try:
        out = subprocess.run(
            [node, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        major, minor, patch = _parse_node_version(out.stdout or out.stderr or "")
        if (major, minor, patch) < (MIN_NODE_MAJOR, MIN_NODE_MINOR, 0):
            return False, f"node {major}.{minor}.{patch} is too old; need >= {MIN_NODE_MAJOR}.{MIN_NODE_MINOR}"
        return True, f"node {major}.{minor}.{patch}"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid() -> Optional[int]:
    path = pid_file()
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def native_process_running() -> bool:
    pid = read_pid()
    if pid and process_alive(pid):
        return True
    if pid:
        try:
            pid_file().unlink(missing_ok=True)
        except OSError:
            pass
    return False


def container_running(name: str = CONTAINER_NAME) -> bool:
    docker = docker_path()
    if not docker:
        return False
    try:
        out = subprocess.run(
            [docker, "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return name in (out.stdout or "").strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        return False


def container_exists(name: str = CONTAINER_NAME) -> bool:
    docker = docker_path()
    if not docker:
        return False
    try:
        out = subprocess.run(
            [docker, "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return name in (out.stdout or "").strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        return False


def resolve_local_base_url(base_urls: Optional[list[str]] = None, *, timeout: int = 5) -> Optional[str]:
    from agent_reach.daily_run.hot_news_collector import _resolve_base_url

    urls = base_urls or [LOCAL_BASE_URL]
    return _resolve_base_url(urls, timeout=timeout)


def merge_user_hot_news_settings(
    *,
    base_urls: Optional[list[str]] = None,
    mode: DeployMode = "native",
    path: Optional[Path] = None,
) -> Path:
    """Ensure ~/.agent-reach/daily_run_settings.json prefers local 60s."""
    from agent_reach.daily_run.settings import _DEFAULT_PATH, _read_json, clear_settings_cache

    out = path or (Path.home() / ".agent-reach" / "daily_run_settings.json")
    if out.exists():
        cfg = _read_json(out)
    elif _DEFAULT_PATH.exists():
        cfg = _read_json(_DEFAULT_PATH)
    else:
        cfg = {}

    hot = dict(cfg.get("hot_news") or {})
    hot.setdefault("enabled", True)
    preferred = base_urls or [LOCAL_BASE_URL, "https://60s.viki.moe"]
    hot["base_urls"] = preferred
    hot["deploy"] = {
        "mode": mode,
        "local_base_url": LOCAL_BASE_URL,
        "host_port": HOST_PORT,
        "repo_url": REPO_URL,
        "install_dir": str(vendor_dir()),
        "pid_file": str(pid_file()),
        "log_file": str(log_file()),
        "container_name": CONTAINER_NAME,
        "image": IMAGE,
        "container_port": CONTAINER_PORT,
    }
    cfg["hot_news"] = hot

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    clear_settings_cache()
    return out


def ensure_source(*, force: bool = False) -> tuple[bool, str]:
    git = git_path()
    if not git:
        return False, "git not found on PATH"

    install_dir = vendor_dir()
    if force and install_dir.exists():
        shutil.rmtree(install_dir, ignore_errors=True)

    if not install_dir.exists():
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                [git, "clone", "--depth", "1", REPO_URL, str(install_dir)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip()
                return False, err or "git clone failed"
            return True, f"cloned 60s into {install_dir}"
        except subprocess.TimeoutExpired:
            return False, "git clone timed out"
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)

    try:
        proc = subprocess.run(
            [git, "-C", str(install_dir), "pull", "--ff-only"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            return False, err or "git pull failed"
        return True, f"updated {install_dir}"
    except subprocess.TimeoutExpired:
        return False, "git pull timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def install_native_deps(install_dir: Path) -> tuple[bool, str]:
    npm = npm_path()
    if not npm:
        return False, "npm not found on PATH"
    env = {**os.environ, "NODE_ENV": "production"}
    try:
        proc = subprocess.run(
            [npm, "install", "--omit=dev"],
            cwd=install_dir,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
            env=env,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            return False, err or "npm install failed"
        return True, "npm install --omit=dev"
    except subprocess.TimeoutExpired:
        return False, "npm install timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def start_native(*, force: bool = False, install_deps: bool = True) -> tuple[bool, str]:
    ok_node, node_msg = node_version_ok()
    if not ok_node:
        return False, node_msg

    if native_process_running() and not force:
        return True, f"native 60s already running (pid {read_pid()})"

    if force and native_process_running():
        stop_native()

    ok, msg = ensure_source(force=force)
    if not ok:
        return False, msg

    install_dir = vendor_dir()
    entry = install_dir / "node.ts"
    if not entry.exists():
        return False, f"missing {entry} after clone"

    if install_deps or not (install_dir / "node_modules").exists():
        ok, dep_msg = install_native_deps(install_dir)
        if not ok:
            return False, dep_msg

    node = node_path()
    if not node:
        return False, "node not found on PATH"

    log_file().parent.mkdir(parents=True, exist_ok=True)
    pid_file().parent.mkdir(parents=True, exist_ok=True)

    env = {
        **os.environ,
        "PORT": str(HOST_PORT),
        "NODE_ENV": "production",
        "TZ": "Asia/Shanghai",
    }
    cmd = [
        node,
        "--experimental-strip-types",
        "--disable-warning=ExperimentalWarning",
        "node.ts",
    ]
    try:
        with open(log_file(), "ab") as logfh:
            proc = subprocess.Popen(
                cmd,
                cwd=install_dir,
                stdout=logfh,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        pid_file().write_text(str(proc.pid) + "\n", encoding="utf-8")
        return True, f"started native 60s pid={proc.pid} on {LOCAL_BASE_URL}"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def stop_native(*, remove_vendor: bool = False) -> tuple[bool, str]:
    pid = read_pid()
    if pid and process_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            if process_alive(pid):
                os.kill(pid, signal.SIGKILL)
        except OSError as exc:
            return False, str(exc)
    try:
        pid_file().unlink(missing_ok=True)
    except OSError:
        pass

    if remove_vendor:
        shutil.rmtree(vendor_dir(), ignore_errors=True)
        return True, "stopped native 60s and removed vendor dir"

    return True, "stopped native 60s"


def pull_image(*, image: str = IMAGE) -> tuple[bool, str]:
    docker = docker_path()
    if not docker:
        return False, "docker not found on PATH"
    try:
        proc = subprocess.run(
            [docker, "pull", image],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            return False, err or f"docker pull failed ({proc.returncode})"
        return True, f"pulled {image}"
    except subprocess.TimeoutExpired:
        return False, "docker pull timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def start_container(*, force: bool = False, pull: bool = True) -> tuple[bool, str]:
    docker = docker_path()
    if not docker:
        return False, "docker not found on PATH"

    if container_running():
        return True, f"container {CONTAINER_NAME} already running"

    if pull:
        ok, msg = pull_image()
        if not ok:
            logger.debug("60s image pull skipped/failed: {}", msg)

    if container_exists() and not force:
        try:
            proc = subprocess.run(
                [docker, "start", CONTAINER_NAME],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode == 0:
                return True, f"started existing container {CONTAINER_NAME}"
            err = (proc.stderr or proc.stdout or "").strip()
            return False, err or "docker start failed"
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)

    if container_exists() and force:
        subprocess.run([docker, "rm", "-f", CONTAINER_NAME], capture_output=True, timeout=30, check=False)

    cmd = [
        docker,
        "run",
        "-d",
        "--restart",
        "unless-stopped",
        "--name",
        CONTAINER_NAME,
        "-p",
        f"{HOST_PORT}:{CONTAINER_PORT}",
        IMAGE,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            return False, err or "docker run failed"
        return True, f"created container {CONTAINER_NAME} on {LOCAL_BASE_URL}"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def stop_container(*, remove: bool = False) -> tuple[bool, str]:
    docker = docker_path()
    if not docker:
        return False, "docker not found on PATH"
    if not container_exists():
        return True, "container not present"
    try:
        subprocess.run([docker, "stop", CONTAINER_NAME], capture_output=True, text=True, timeout=60, check=False)
        if remove:
            subprocess.run([docker, "rm", CONTAINER_NAME], capture_output=True, text=True, timeout=30, check=False)
            return True, f"removed container {CONTAINER_NAME}"
        return True, f"stopped container {CONTAINER_NAME}"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def stop_60s(*, remove: bool = False, mode: Optional[DeployMode] = None) -> tuple[bool, str]:
    """Stop native and/or docker 60s."""
    messages: list[str] = []
    ok = True

    stop_native_too = mode in (None, "native", "auto")
    stop_docker_too = mode in (None, "docker", "auto")

    if stop_native_too and (native_process_running() or remove):
        n_ok, n_msg = stop_native(remove_vendor=remove)
        ok = ok and n_ok
        messages.append(n_msg)

    from agent_reach.daily_run.hot_news_portal import stop_portal

    p_ok, p_msg = stop_portal()
    if p_msg != "portal not running":
        ok = ok and p_ok
        messages.append(p_msg)

    if stop_docker_too and (container_exists() or container_running()):
        d_ok, d_msg = stop_container(remove=remove)
        ok = ok and d_ok
        messages.append(d_msg)

    if not messages:
        return True, "60s not running"
    return ok, "; ".join(messages)


def wait_healthy(*, timeout: int = 60, poll_interval: float = 2.0) -> tuple[bool, str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        base = resolve_local_base_url([LOCAL_BASE_URL], timeout=3)
        if base:
            return True, base
        time.sleep(poll_interval)
    return False, f"60s API not reachable at {LOCAL_BASE_URL} within {timeout}s"


REBOOT_MARKER_BEGIN = "# agent-reach 60s reboot BEGIN"
REBOOT_MARKER_END = "# agent-reach 60s reboot END"
REBOOT_SLEEP_SECONDS = 30


def reboot_start_script() -> Path:
    """Resolve scripts/60s-reboot-start.sh from repo or installed package."""
    candidates = [
        Path(__file__).resolve().parents[2] / "scripts" / "60s-reboot-start.sh",
    ]
    try:
        import importlib.util

        spec = importlib.util.find_spec("agent_reach")
        if spec and spec.origin:
            candidates.append(Path(spec.origin).resolve().parent.parent / "scripts" / "60s-reboot-start.sh")
    except Exception:
        pass
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def render_reboot_crontab_block(*, sleep_seconds: int = REBOOT_SLEEP_SECONDS) -> str:
    script = reboot_start_script()
    lines = [
        REBOOT_MARKER_BEGIN,
        "SHELL=/bin/bash",
        "# log: ~/.agent-reach/daily_run/logs/60s-reboot-YYYY-MM-DD.log",
    ]
    if script.is_file():
        lines.append(f"# wrapper: {script}")
        lines.append(
            f"@reboot sleep {sleep_seconds} && {script}  # agent-reach 60s auto-start on boot"
        )
    else:
        lines.append(f"# missing wrapper script: {script}")
    lines.append(REBOOT_MARKER_END)
    return "\n".join(lines) + "\n"


def _merge_crontab_block(existing: str, block: str, marker_begin: str, marker_end: str) -> str:
    if marker_begin in existing:
        before = existing.split(marker_begin)[0].rstrip()
        after_parts = existing.split(marker_end)
        after = after_parts[1].lstrip("\n") if len(after_parts) > 1 else ""
        new_crontab = before
        if new_crontab:
            new_crontab += "\n"
        new_crontab += block
        if after.strip():
            new_crontab += after
        return new_crontab
    return existing.rstrip() + "\n\n" + block if existing.strip() else block


def reboot_cron_installed() -> bool:
    crontab_bin = shutil.which("crontab")
    if not crontab_bin:
        return False
    try:
        existing = subprocess.check_output([crontab_bin, "-l"], stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        return False
    return REBOOT_MARKER_BEGIN in existing


def install_reboot_crontab(*, dry_run: bool = False) -> str:
    """Install @reboot crontab entry to auto-start 60s after login/reboot."""
    block = render_reboot_crontab_block()
    if dry_run:
        return block

    script = reboot_start_script()
    if script.is_file():
        script.chmod(script.stat().st_mode | 0o111)

    crontab_bin = shutil.which("crontab")
    if not crontab_bin:
        fallback = Path.home() / ".agent-reach" / "daily_run" / "60s-reboot-crontab.txt"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(block, encoding="utf-8")
        raise RuntimeError(
            f"系统未安装 crontab。已将 @reboot 配置写入 {fallback}，请手动安装"
        )

    existing = ""
    try:
        existing = subprocess.check_output([crontab_bin, "-l"], stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        existing = ""

    new_crontab = _merge_crontab_block(existing, block, REBOOT_MARKER_BEGIN, REBOOT_MARKER_END)
    proc = subprocess.run(
        [crontab_bin, "-"],
        input=new_crontab.encode(),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode() or "crontab install failed")
    return new_crontab


def _attach_portal(result: dict[str, Any]) -> None:
    from agent_reach.daily_run.hot_news_portal import PORTAL_PORT, portal_running, start_portal

    ok, msg = start_portal(api_base=LOCAL_BASE_URL, force=True)
    result["portal_running"] = portal_running()
    result["web_url"] = f"http://127.0.0.1:{PORTAL_PORT}"
    if ok:
        result["portal_message"] = msg
    else:
        result["portal_message"] = f"portal start failed: {msg}"


def _install_native(result: dict[str, Any], *, force: bool, wait_timeout: int) -> dict[str, Any]:
    ok, msg = start_native(force=force)
    result["native_running"] = native_process_running()
    result["native_pid"] = read_pid()
    result["deploy_mode"] = "native"
    if not ok:
        base = resolve_local_base_url([LOCAL_BASE_URL, "https://60s.viki.moe"])
        result["active_base_url"] = base
        result["ok"] = bool(base)
        result["message"] = f"native deploy failed: {msg}"
        return result

    healthy, health_msg = wait_healthy(timeout=wait_timeout)
    result["reachable"] = healthy
    result["active_base_url"] = health_msg if healthy else resolve_local_base_url(
        [LOCAL_BASE_URL, "https://60s.viki.moe"]
    )
    result["ok"] = healthy or bool(result["active_base_url"])
    result["message"] = health_msg if healthy else f"started but health check failed: {health_msg}"
    if result.get("reachable"):
        _attach_portal(result)
    return result


def _install_docker(result: dict[str, Any], *, force: bool, pull: bool, wait_timeout: int) -> dict[str, Any]:
    if not docker_path():
        base = resolve_local_base_url([LOCAL_BASE_URL, "https://60s.viki.moe"])
        result["active_base_url"] = base
        result["ok"] = bool(base)
        result["deploy_mode"] = "docker"
        result["message"] = "docker not available"
        return result
    ok, msg = start_container(force=force, pull=pull)
    result["running"] = container_running()
    result["deploy_mode"] = "docker"
    if not ok:
        base = resolve_local_base_url([LOCAL_BASE_URL, "https://60s.viki.moe"])
        result["active_base_url"] = base
        result["ok"] = bool(base)
        result["message"] = f"docker deploy failed: {msg}"
        return result
    healthy, health_msg = wait_healthy(timeout=wait_timeout)
    result["reachable"] = healthy
    result["active_base_url"] = health_msg if healthy else resolve_local_base_url(
        [LOCAL_BASE_URL, "https://60s.viki.moe"]
    )
    result["ok"] = healthy or bool(result["active_base_url"])
    result["message"] = health_msg if healthy else f"deployed but health check failed: {health_msg}"
    if result.get("reachable"):
        _attach_portal(result)
    return result


def install_60s_local(
    *,
    mode: DeployMode = "native",
    pull: bool = True,
    force: bool = False,
    skip_deploy: bool = False,
    install_reboot_cron: bool = True,
    wait_timeout: int = 90,
) -> dict[str, Any]:
    """Deploy local 60s (native Node by default) and merge user hot_news settings."""
    if skip_deploy:
        mode = "skip"

    result: dict[str, Any] = {
        "ok": False,
        "local_base_url": LOCAL_BASE_URL,
        "deploy_mode": mode,
        "docker": bool(docker_path()),
        "node": node_path(),
        "native_running": native_process_running(),
        "native_pid": read_pid(),
        "container_name": CONTAINER_NAME,
        "container_running": container_running(),
        "install_dir": str(vendor_dir()),
        "reachable": False,
        "settings_path": None,
        "message": "",
    }

    settings_path = merge_user_hot_news_settings(mode=mode if mode != "skip" else "native")
    result["settings_path"] = str(settings_path)

    if mode == "skip":
        base = resolve_local_base_url([LOCAL_BASE_URL, "https://60s.viki.moe"])
        result["reachable"] = base == LOCAL_BASE_URL
        result["active_base_url"] = base
        result["ok"] = bool(base)
        result["message"] = "deploy skipped; using existing endpoint or public fallback"
        return _finalize_install_result(result, install_reboot_cron=install_reboot_cron)

    if resolve_local_base_url([LOCAL_BASE_URL], timeout=3) == LOCAL_BASE_URL and not force:
        result["reachable"] = True
        result["active_base_url"] = LOCAL_BASE_URL
        result["ok"] = True
        result["native_running"] = native_process_running()
        result["container_running"] = container_running()
        result["message"] = f"local 60s already healthy at {LOCAL_BASE_URL}"
        _attach_portal(result)
        return result

        _attach_portal(result)
        return _finalize_install_result(result, install_reboot_cron=install_reboot_cron)

    if mode == "native":
        return _finalize_install_result(
            _install_native(result, force=force, wait_timeout=wait_timeout),
            install_reboot_cron=install_reboot_cron,
        )

    if mode == "docker":
        return _finalize_install_result(
            _install_docker(result, force=force, pull=pull, wait_timeout=wait_timeout),
            install_reboot_cron=install_reboot_cron,
        )

    # auto: native → docker → public fallback
    native_result = _install_native(result, force=force, wait_timeout=wait_timeout)
    if native_result.get("ok") and native_result.get("reachable"):
        native_result["deploy_mode"] = "auto"
        return _finalize_install_result(native_result, install_reboot_cron=install_reboot_cron)

    docker_result = _install_docker(result, force=force, pull=pull, wait_timeout=wait_timeout)
    docker_result["deploy_mode"] = "auto"
    if docker_result.get("ok"):
        return _finalize_install_result(docker_result, install_reboot_cron=install_reboot_cron)

    base = resolve_local_base_url([LOCAL_BASE_URL, "https://60s.viki.moe"])
    docker_result["active_base_url"] = base
    docker_result["ok"] = bool(base)
    docker_result["message"] = (
        f"native/docker deploy failed; using public fallback {base}"
        if base
        else "native/docker deploy failed and public fallback unreachable"
    )
    return _finalize_install_result(docker_result, install_reboot_cron=install_reboot_cron)


def _finalize_install_result(result: dict[str, Any], *, install_reboot_cron: bool) -> dict[str, Any]:
    if install_reboot_cron and result.get("ok"):
        try:
            install_reboot_crontab()
            result["reboot_cron"] = True
            result["reboot_cron_installed"] = True
        except Exception as exc:
            result["reboot_cron"] = False
            result["reboot_cron_installed"] = reboot_cron_installed()
            result["reboot_cron_message"] = str(exc)
    else:
        result["reboot_cron_installed"] = reboot_cron_installed()
    return result


def status_60s() -> dict[str, Any]:
    """Report local 60s process/container and API reachability."""
    from agent_reach.daily_run.settings import load_settings

    cfg = load_settings()
    hot = cfg.get("hot_news") or {}
    deploy = hot.get("deploy") or {}
    base_urls = list(hot.get("base_urls") or [LOCAL_BASE_URL, "https://60s.viki.moe"])
    active = resolve_local_base_url(base_urls)
    local_ok = resolve_local_base_url([LOCAL_BASE_URL]) == LOCAL_BASE_URL

    ok_node, node_msg = node_version_ok()
    from agent_reach.daily_run.hot_news_portal import PORTAL_PORT, portal_running

    return {
        "deploy_mode": deploy.get("mode", "native"),
        "docker": bool(docker_path()),
        "node": node_path(),
        "node_ok": ok_node,
        "node_message": node_msg,
        "native_pid": read_pid(),
        "native_running": native_process_running(),
        "install_dir": str(vendor_dir()),
        "log_file": str(log_file()),
        "container_name": CONTAINER_NAME,
        "container_running": container_running(),
        "local_base_url": LOCAL_BASE_URL,
        "web_url": f"http://127.0.0.1:{PORTAL_PORT}",
        "portal_running": portal_running(),
        "local_reachable": local_ok,
        "active_base_url": active,
        "using_public_fallback": active == "https://60s.viki.moe" and not local_ok,
        "base_urls": base_urls,
        "platforms": hot.get("platforms"),
        "note": "Open web_url for readable dashboard; local_base_url root returns API JSON by design.",
        "reboot_cron_installed": reboot_cron_installed(),
        "reboot_crontab_block": render_reboot_crontab_block().strip(),
    }
