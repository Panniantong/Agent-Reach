# Career and Recruiting

LinkedIn and Boss Zhipin.

## LinkedIn

```bash
# Get a person profile
mcporter call linkedin.get_person_profile linkedin_username="username" sections="experience,education"

# Search people
mcporter call linkedin.search_people keywords="AI engineer" location="Shanghai"

# Get a company profile
mcporter call linkedin.get_company_profile company_name="openai" sections="posts,jobs"

# Search jobs
mcporter call linkedin.search_jobs keywords="software engineer" location="Remote" max_pages=2
```

> **Login required:** before first use, run `uvx mcp-server-linkedin@latest --login` and complete the browser login.

### Fallback

If the MCP backend is unavailable, use Jina Reader for public pages:

```bash
curl -s "https://r.jina.ai/https://linkedin.com/in/username"
```

## Boss Zhipin

When the user asks for help configuring Boss Zhipin, complete the installation, launch the dedicated Chrome profile, wait for the user to log in manually, and verify the final state. Do not dump CDP implementation details on the user up front, and never enter credentials, scan QR codes, or solve sliders on their behalf.

> **Important distinction: login state is not the same as an anti-bot security challenge.** After opening zhipin.com, Chrome may show a logged-in `web/geek/job` page, a logged-out `web/user/` login page, or a security-check URL containing `security-check`, `zhipin-security`, or `_security_check`. The security-check page is unrelated to whether the account is logged in and may appear even for authenticated sessions. Never infer login state from the current page URL.

### Two authentication stores

Boss Zhipin has two separate credential stores. **Do not delete either one.**

| Store | Role |
|---|---|
| `~/.boss-agent/auth/session.enc` | Required before `_get_browser()` can continue. If it cannot be read, the CLI raises `AuthRequired` before connecting to Chrome. It is also used by low-risk httpx operations such as `status`, `detail`, `cities`, and `job_card_httpx`. However, it is **not** the effective authentication source for strict existing-browser CDP searches because those reuse the real Chrome context. |
| Browser cookies in the dedicated Chrome profile | The credentials actually carried by high-risk CDP operations such as search and greet. |

`boss status` / `status --live` validates only `session.enc`. A `logged_in: true` response does **not** prove that the dedicated Chrome profile is logged in.

Use these rules:

1. After launching the dedicated Chrome profile, pause and have the user visually confirm that the account is logged in (for example, an avatar is visible) before searching.
2. The Boss row in `agent-reach doctor` directly probes the browser for the `wt2` cookie; use that as the browser-login signal.
3. `AUTH_EXPIRED` from a search is the ground truth. If it appears, go directly to the login runbook (user logs in in the dedicated Chrome window, then run `login --cdp`). Do not reinterpret it as a security-check problem.
4. Do not delete `session.enc` to "clear old credentials." Refresh it with `login --cdp`.

### Dependency state

The required strict-CDP public APIs came from boss-agent-cli PRs #403–#407, which were merged upstream. Agent Reach pins upstream commit:

```text
4c991b77086a203173bf08a4cb64a23af6514fe6
```

Use a fixed commit rather than a moving branch until upstream publishes a stable release.

### Health check

```bash
agent-reach doctor
```

The Boss row reports whether boss-agent-cli is installed, whether the CDP endpoint is reachable, whether a reusable Zhipin tab exists, and whether the browser contains the `wt2` login cookie. Doctor does not perform a job search.

### Search + JD through the public Python API

Because pipx/uv-tool environments are isolated, plain `python` may not be able to import the installed package. Use `uv run --with` so the script and pinned dependency run in the same environment:

```bash
uv run --isolated --no-project \
  --with 'git+https://github.com/can4hou6joeng4/boss-agent-cli.git@4c991b77086a203173bf08a4cb64a23af6514fe6' \
  python - <<'PY'
from pathlib import Path

from boss_agent_cli.api.client import AccountRiskError, BossClient, EnvironmentRiskError
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.platforms.zhipin import BossPlatform

auth = AuthManager(Path.home() / ".boss-agent")

with BossClient(
    auth,
    cdp_url="http://localhost:9222",
    browser_source="existing-browser",
) as boss:
    raw = boss.search_jobs("LLM", city="Shenzhen", page=1)
    if raw.get("code") != 0:
        code, message = BossPlatform(boss).parse_error(raw)
        raise RuntimeError(f"{code}: {message}")
    items = raw.get("zpData", {}).get("jobList", [])
    for item in items:
        card = boss.job_card_browser(item["securityId"], item["lid"])
        post_desc = card.get("zpData", {}).get("jobCard", {}).get(
            "postDescription", ""
        )
        print(item.get("jobName"), post_desc)

# AccountRiskError / EnvironmentRiskError => stop immediately; do not auto-retry.
# An explicit token/stoken-expiry code 37 may be refreshed/retried once by BossClient.
PY
```

## Environment recovery runbook

If `agent-reach doctor` reports Boss as off/warn before a search, use this sequence instead of guessing.

1. **Check the CDP endpoint**
   ```bash
   curl -s http://localhost:9222/json/version
   ```
   A JSON response containing `Browser` means the port is reachable.

2. **Start the dedicated Chrome profile if needed**

   macOS:
   ```bash
   open -na "Google Chrome" --args --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"
   ```

   Linux:
   ```bash
   google-chrome --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"
   ```

   Windows PowerShell:
   ```powershell
   Start-Process chrome.exe -ArgumentList '--remote-debugging-address=127.0.0.1','--remote-debugging-port=9222',"--user-data-dir=$env:USERPROFILE\.boss-chrome-profile",'https://www.zhipin.com/web/geek/job'
   ```

   Bind only to loopback. Any process that can access port 9222 can fully control this Chrome instance. Reuse the dedicated profile long-term to preserve a stable login session. Do not recreate it each run and do not switch to the user's daily Chrome profile by default.

3. **Have the user log in manually if the browser is logged out**

   Prefer the doctor's browser-cookie probe (missing `wt2` means the browser is logged out), then the user's visual confirmation. Treat `boss status` as secondary information only.

   After the user confirms login:

   ```bash
   boss --cdp-url http://localhost:9222 login --cdp
   ```

   If Chrome is on a `security-check` / `zhipin-security` page, that is an anti-bot challenge rather than a login page. Let the user complete it manually if needed; do not force a new login just because that URL is visible.

4. **Verify browser login and local store**

   ```bash
   agent-reach doctor
   boss status
   ```

   Use the doctor's browser `wt2` probe as the primary signal. `boss status` reflects only `session.enc`.

5. **Handle search/JD error codes**

   - `AUTH_EXPIRED`: browser is logged out. Go directly to step 3 and then `login --cdp`.
   - Code 36 / `ACCOUNT_RISK`: stop immediately and let the user handle the Boss site manually; do not auto-retry.
   - Code 9 / `RATE_LIMITED`: cool down before retrying.
   - Code 37 with an environment-risk message: treat as `ENVIRONMENT_RISK`; stop immediately, do not refresh tokens, relogin, or auto-retry.
   - Only code 37 text that explicitly indicates token/stoken expiry is `TOKEN_REFRESH_FAILED`; the client may refresh/retry once, then require a new login if it still fails.

When the user asks to search, always use strict existing-browser CDP mode:

```bash
boss --browser-source existing-browser --cdp-url http://localhost:9222 search "LLM" --city Guangzhou --page 1
```

Do not turn pages continuously without warning. Serial, lower-frequency calls are preferred. Throttling waits of roughly 5–10 seconds can be expected and should not be treated as a hang.
