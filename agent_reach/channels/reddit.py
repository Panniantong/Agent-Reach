# -*- coding: utf-8 -*-
"""Reddit — search and read via rdt-cli (public-clis/rdt-cli).

NOTE: Reddit requires authentication since 2024. All API requests
(including public subreddit reads) return HTTP 403 without a valid
session cookie. Run `rdt login` after installation to authenticate.
"""

import json
import shutil
import subprocess

from .base import Channel

_CREDENTIAL_FILE = "~/.config/rdt-cli/credential.json"


class RedditChannel(Channel):
    name = "reddit"
    description = "Reddit posts and comments"
    backends = ["rdt-cli"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "reddit.com" in d or "redd.it" in d

    def check(self, config=None):
        rdt = shutil.which("rdt")
        if not rdt:
            return "off", (
                "rdt-cli must be installed (latest v0.4.2+ recommended):\n"
                "  pip install 'rdt-cli>=0.4.2'\n"
                "or:\n"
                "  uv tool install rdt-cli\n"
                "Latest source: https://github.com/public-clis/rdt-cli\n"
                "After installing, run `rdt login` to log in (log in to reddit.com in your browser first)"
            )

        try:
            r = subprocess.run(
                [rdt, "status", "--json"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            data = json.loads(r.stdout or "{}")
            authenticated = data.get("data", {}).get("authenticated", False)
            username = data.get("data", {}).get("username") or ""

            if authenticated:
                suffix = f" (logged in: {username})" if username else ""
                return "ok", (f"rdt-cli available{suffix} (search posts, read full text, view comments)")

            return "warn", (
                "rdt-cli installed but not logged in. Reddit has required authentication since 2024; "
                "all requests return 403 when not logged in.\n\n"
                "Method 1 (automatic): run `rdt login`\n"
                "  Log in to reddit.com in your browser first, then run this command to automatically extract the Cookie.\n\n"
                "Method 2 (manual, for when automatic extraction fails on Chrome/Edge 127+):\n"
                "  1. Install the Cookie-Editor extension from the Chrome Web Store:\n"
                "     https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm\n"
                "  2. Open reddit.com in your browser (make sure you are logged in)\n"
                "  3. Click the Cookie-Editor icon, find `reddit_session`, and copy its Value\n"
                f"  4. Write the following into {_CREDENTIAL_FILE}:\n"
                '     {"cookies": {"reddit_session": "<paste Value>"}, '
                '"source": "manual", "username": "<your username>", '
                '"modhash": null, "saved_at": 0, "last_verified_at": null}\n\n'
                "Verify: `rdt status --json` to confirm authenticated: true"
            )

        except (json.JSONDecodeError, FileNotFoundError, subprocess.TimeoutExpired):
            return "warn", "rdt-cli installed but status check failed; run `rdt status` to view details"
