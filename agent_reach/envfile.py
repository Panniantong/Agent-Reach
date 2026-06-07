"""Project-local environment file support for Agent Reach.

The file lives at ~/.agent-reach/.env by default. It is intentionally separate
from the OS/user environment so cookies, tokens, and proxy settings can be used
by Agent Reach tools without leaking into unrelated applications.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Iterable, Mapping

from agent_reach.config import Config

DEFAULT_ENV_FILE = Config.CONFIG_DIR / ".env"
DEFAULT_WRAPPER_TOOLS = (
    "twitter",
    "xhs",
    "rdt",
    "yt-dlp",
    "bili",
    "douyin-mcp-server",
)
PIPX_PACKAGE_BY_TOOL = {
    "twitter": "twitter-cli",
    "xhs": "xiaohongshu-cli",
    "bili": "bilibili-cli",
    "rdt": "rdt-cli",
    "douyin-mcp-server": "douyin-mcp-server",
}


def parse_env_lines(lines: Iterable[str]) -> dict[str, str]:
    """Parse a small shell-compatible dotenv file."""
    values: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.lstrip("\ufeff").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or not name.replace("_", "A").isalnum() or name[0].isdigit():
            continue

        if (
            len(value) >= 2
            and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'"))
        ):
            value = value[1:-1]
        value = value.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
        values[name] = value
    return values


def read_env_file(path: Path | None = None) -> dict[str, str]:
    """Read a dotenv file using utf-8-sig so accidental BOMs do not break it."""
    env_path = Path(path or DEFAULT_ENV_FILE)
    if not env_path.exists():
        return {}
    return parse_env_lines(env_path.read_text(encoding="utf-8-sig").splitlines())


def quote_env_value(value: object) -> str:
    """Quote a value so the generated file can be sourced by POSIX shells."""
    text = "" if value is None else str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def write_env_file(values: Mapping[str, str], path: Path | None = None) -> Path:
    """Write a dotenv file without UTF-8 BOM and with owner-only permissions."""
    env_path = Path(path or DEFAULT_ENV_FILE)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Agent Reach local environment",
        "# Loaded only by Agent Reach wrappers; do not put these in global OS env.",
        "",
    ]
    for key in sorted(values):
        lines.append(f"{key}={quote_env_value(values[key])}")
    lines.append("")

    env_path.write_text("\n".join(lines), encoding="utf-8")
    try:
        env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return env_path


def update_env_file(updates: Mapping[str, str], path: Path | None = None) -> Path:
    """Merge updates into the local environment file."""
    values = read_env_file(path)
    for key, value in updates.items():
        if value is not None and str(value) != "":
            values[key] = str(value)
    return write_env_file(values, path)


def load_agent_env(path: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Load ~/.agent-reach/.env into os.environ for the current process."""
    values = read_env_file(path)
    for key, value in values.items():
        if override or key not in os.environ:
            os.environ[key] = value
    return values


def config_env_updates(config: Config) -> dict[str, str]:
    """Return dotenv keys mirrored from Agent Reach config.yaml."""
    updates: dict[str, str] = {}

    def copy(config_key: str, *env_keys: str) -> None:
        value = config.get(config_key)
        if value:
            for env_key in env_keys:
                updates[env_key] = str(value)

    copy("twitter_auth_token", "AUTH_TOKEN", "TWITTER_AUTH_TOKEN")
    copy("twitter_ct0", "CT0", "TWITTER_CT0")
    copy("xhs_cookie", "XHS_COOKIES")
    copy("xueqiu_cookie", "XUEQIU_COOKIE")
    copy("bilibili_proxy", "BILIBILI_PROXY")
    copy("bilibili_sessdata", "BILIBILI_SESSDATA")
    copy("bilibili_csrf", "BILIBILI_CSRF")
    copy("youtube_cookies_from", "YOUTUBE_COOKIES_FROM")
    copy("groq_api_key", "GROQ_API_KEY")
    copy("github_token", "GITHUB_TOKEN")
    copy("dashscope_api_key", "DASHSCOPE_API_KEY")
    return updates


def sync_config_to_env(config: Config | None = None, path: Path | None = None) -> Path:
    """Mirror known config.yaml credentials into ~/.agent-reach/.env."""
    return update_env_file(config_env_updates(config or Config()), path)


def default_user_bin_dir() -> Path:
    if os.name == "nt":
        return Path.home() / ".local" / "bin"
    return Path.home() / ".local" / "bin"


def _path_entries(exclude_dir: Path) -> list[Path]:
    entries = []
    for part in os.environ.get("PATH", "").split(os.pathsep):
        if not part:
            continue
        path = Path(part)
        try:
            if path.resolve() == exclude_dir.resolve():
                continue
        except OSError:
            pass
        entries.append(path)
    return entries


def find_executable_excluding(command: str, exclude_dir: Path) -> str | None:
    """Find a command on PATH while ignoring the wrapper output directory."""
    path = os.pathsep.join(str(p) for p in _path_entries(exclude_dir))
    found = shutil.which(command, path=path)
    if found:
        return found

    suffixes = [".exe", ".cmd", ""] if os.name == "nt" else [""]
    package = PIPX_PACKAGE_BY_TOOL.get(command, command)
    candidate_dirs = [
        Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin"),
        Path.home() / "pipx" / "venvs" / package / ("Scripts" if os.name == "nt" else "bin"),
        Path.home() / ".local" / "pipx" / "venvs" / package / ("Scripts" if os.name == "nt" else "bin"),
        Path.home() / ".agent-reach-venv" / ("Scripts" if os.name == "nt" else "bin"),
    ]
    for directory in candidate_dirs:
        for suffix in suffixes:
            candidate = directory / f"{command}{suffix}"
            if candidate.exists() and candidate.is_file():
                return str(candidate)
    return None


def install_tool_wrappers(
    tools: Iterable[str] = DEFAULT_WRAPPER_TOOLS,
    *,
    bin_dir: Path | None = None,
    env_path: Path | None = None,
) -> dict[str, str]:
    """Install command wrappers that load Agent Reach .env before running tools."""
    output_dir = Path(bin_dir or default_user_bin_dir())
    output_dir.mkdir(parents=True, exist_ok=True)
    env_file = Path(env_path or DEFAULT_ENV_FILE)
    python = sys.executable

    installed: dict[str, str] = {}
    for tool in tools:
        target = find_executable_excluding(tool, output_dir)
        if not target:
            installed[tool] = "missing"
            continue

        if os.name == "nt":
            cmd_path = output_dir / f"{tool}.cmd"
            cmd_path.write_text(
                "@echo off\n"
                f'"{python}" -m agent_reach.envexec --env-file "{env_file}" "{target}" %*\n'
                "exit /b %ERRORLEVEL%\n",
                encoding="utf-8",
            )
            installed[tool] = str(cmd_path)

        sh_path = output_dir / tool
        sh_path.write_text(
            "#!/bin/sh\n"
            f'exec "{python}" -m agent_reach.envexec --env-file "{env_file}" "{target}" "$@"\n',
            encoding="utf-8",
        )
        try:
            sh_path.chmod(sh_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass
        if os.name != "nt":
            installed[tool] = str(sh_path)

    return installed
