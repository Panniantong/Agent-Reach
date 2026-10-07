# -*- coding: utf-8 -*-
"""Suite-wide containment for tests that exercise user-facing installers."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from agent_reach.config import Config


@pytest.fixture(scope="session")
def bash_executable() -> str:
    """Return a real GNU Bash, avoiding Windows' WSL launcher stub."""
    candidates: list[Path] = []
    override = os.environ.get("AGENT_REACH_TEST_BASH")
    if override:
        candidates.append(Path(override))

    if os.name == "nt":
        for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            program_files = os.environ.get(env_name)
            if program_files:
                git_root = Path(program_files) / "Git"
                candidates.extend(
                    (git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe")
                )

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            git_root = Path(local_app_data) / "Programs" / "Git"
            candidates.extend(
                (git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe")
            )

        git = shutil.which("git")
        if git:
            git_parent = Path(git).resolve().parent
            if git_parent.name.lower() in {"bin", "cmd"}:
                git_root = git_parent.parent
                candidates.extend(
                    (git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe")
                )

    discovered = shutil.which("bash")
    if discovered:
        candidates.append(Path(discovered))

    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.fspath(candidate))
        if key in seen or not candidate.is_file():
            continue
        seen.add(key)
        try:
            result = subprocess.run(
                [os.fspath(candidate), "--version"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and "GNU bash" in result.stdout:
            return os.fspath(candidate)

    pytest.fail("GNU Bash is required for shell-script tests")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect every common home/config root before each test runs."""
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    monkeypatch.delenv("OPENCLAW_HOME", raising=False)

    config_dir = home / ".agent-reach"
    monkeypatch.setattr(Config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(Config, "CONFIG_FILE", config_dir / "config.yaml")
    return home


@pytest.fixture(autouse=True)
def isolated_xueqiu_cookie_jar(monkeypatch):
    """Prevent the module-level Xueqiu session from leaking between tests."""
    from agent_reach.channels import xueqiu

    xueqiu._cookie_jar.clear()
    monkeypatch.setattr(xueqiu, "_cookies_initialized", False)
    yield
    xueqiu._cookie_jar.clear()


@pytest.fixture(autouse=True)
def clear_probe_cache():
    """Drop the process-wide probe cache before every test.

    probe.probe_command caches results with a TTL. Without this, one test's
    real probe (e.g. bili --version on the host) poisons a later test that
    monkeypatches subprocess.run to simulate a broken/missing tool.
    """
    from agent_reach import probe

    probe._PROBE_CACHE.clear()
    yield
    probe._PROBE_CACHE.clear()
