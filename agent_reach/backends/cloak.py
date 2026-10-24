"""Install/locate the shared browser runtime. Website extraction belongs upstream."""
from __future__ import annotations

import json
import os
from pathlib import Path

from agent_reach.runtime.result import NEED_SETUP, ReachError


def setup() -> dict:
    from agent_reach.runtime import state, tools
    from agent_reach.runtime.run import run_cmd

    state.remember_path(state.root() / "cloak-binaries", "dedicated browser binaries")
    tools.ensure("cloakbrowser")
    exe = tools.resolve("cloakbrowser")
    if not exe:
        raise ReachError(NEED_SETUP, "CloakBrowser executable is missing")
    python = Path(exe).parent / ("python.exe" if os.name == "nt" else "python")
    env = {**tools.install_env(), "CLOAKBROWSER_AUTO_UPDATE": "false",
           "CLOAKBROWSER_CACHE_DIR": str(state.root() / "cloak-binaries"),
           "PYTHONPATH": str(Path(__file__).parents[2])}
    try:
        run_cmd([exe, "install"], timeout=180, env=env)
        result = json.loads(run_cmd([str(python), "-m", "agent_reach.backends.cloak"], timeout=20, env=env))
    except (ReachError, ValueError, OSError):
        raise ReachError(NEED_SETUP, "CloakBrowser installation/download failed; downloaded cache is retained",
                         hint="Reach will use installed Chrome when available. Use browser setup --retry-cloak to retry CloakBrowser.") from None
    return {**result, "python": str(python), "backend": "cloakbrowser"}


if __name__ == "__main__":
    from cloakbrowser.config import PLATFORM_CHROMIUM_VERSIONS, get_binary_path, get_platform_tag
    version = PLATFORM_CHROMIUM_VERSIONS[get_platform_tag()]
    binary = get_binary_path(version)
    if not binary.is_file():
        raise SystemExit("CloakBrowser binary is missing")
    print(json.dumps({"executable": str(binary), "version": version}))
