# -*- coding: utf-8 -*-
"""Shared installer helpers used by ``hivereach install`` channel handlers."""

from __future__ import annotations

import shutil
import subprocess
from typing import Iterable, Tuple


_DEFAULT_INSTALLERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("pipx", ("pipx", "install")),
    ("uv",   ("uv", "tool", "install")),
)


def install_pipx_tool(
    *,
    label: str,
    binary: str,
    package: str,
    post_install_hint: str = "",
    installers: Iterable[Tuple[str, Tuple[str, ...]]] = _DEFAULT_INSTALLERS,
    timeout: int = 120,
) -> None:
    """Install a Python CLI via pipx (with uv fallback) and print progress.

    Mirrors the original per-channel behaviour: detect the binary, try each
    installer in order until one produces a usable binary, otherwise print a
    manual recovery hint. Errors from ``subprocess.run`` are intentionally
    swallowed so a missing/broken installer falls through to the next option.
    """
    print(f"Setting up {label}...")
    if shutil.which(binary):
        print(f"  ✅ {package} already installed")
        return

    for installer, prefix in installers:
        if not shutil.which(installer):
            continue
        try:
            subprocess.run(
                list(prefix) + [package],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except (subprocess.SubprocessError, OSError):
            continue
        if shutil.which(binary):
            suffix = f" ({post_install_hint})" if post_install_hint else ""
            print(f"  ✅ {package} installed{suffix}")
            return

    print(f"  [!]  {package} install failed. Run: pipx install {package}")
