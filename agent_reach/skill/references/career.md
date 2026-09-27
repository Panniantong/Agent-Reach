# Careers and recruiting

LinkedIn and Boss Zhipin.

## LinkedIn

```bash
# Read a profile
mcporter call linkedin.get_person_profile linkedin_username="username" sections="experience,education"

# Search people
mcporter call linkedin.search_people keywords="AI engineer" location="Shanghai"

# Read company information
mcporter call linkedin.get_company_profile company_name="openai" sections="posts,jobs"

# Search jobs
mcporter call linkedin.search_jobs keywords="software engineer" location="Remote" max_pages=2
```

Before first use, run `uvx mcp-server-linkedin@latest --login` and log in through
the browser. If MCP is unavailable, use Jina Reader for public pages:

```bash
curl -s "https://r.jina.ai/https://linkedin.com/in/username"
```

## Boss Zhipin

When the user asks "help me configure Boss Zhipin", install the backend, launch a
dedicated Chrome profile, wait for the user to log in manually, and verify the
connection. Do not make the user assemble CDP flags. Do not enter their credentials,
scan QR codes, or solve sliders for them.

### Login state and anti-bot challenges

The browser may show a logged-in `web/geek/job` page, a `web/user/` login page,
or an anti-bot page whose URL contains `security-check`, `zhipin-security`, or
`_security_check`. Anti-bot pages can appear even when logged in, especially with
Chrome's debugging port enabled. **Do not infer login state from the page URL.**

Two credential stores are required, but they authenticate different paths:

| Store | Role |
|-------|------|
| `~/.boss-agent/auth/session.enc` | `_get_browser()` calls `get_token()` unconditionally; missing credentials raise `AuthRequired` before connecting to Chrome. The HTTP path (`status`, `detail`, `cities`, `job_card_httpx`) uses its cookies and stoken; code 37 `force_refresh()` also updates this file. It does not supply search credentials when CDP reuses an existing browser context. |
| Cookies in the dedicated Chrome profile | These authenticate CDP operations such as search and greet. When CDP reuses `contexts[0]`, the cookies from `session.enc` are not injected; injection only occurs when no context exists. |

**Do not delete either store.** `boss status` and `status --live` check only
`session.enc`. Even `logged_in: true` does not prove that Chrome is logged in.

1. After launching Chrome, pause and have the user visually confirm login
   (avatar in the top-right) before searching.
2. Use the browser `wt2` cookie probe in `agent-reach doctor` as the browser-state check.
3. `AUTH_EXPIRED` from search means the browser is logged out. Follow the login
   procedure and `login --cdp`; do not explain it as an anti-bot challenge.
4. Refresh `session.enc` with `login --cdp`, rather than deleting it.

### Pinned dependency

The public strict-CDP APIs came from upstream boss-agent-cli PRs #403–#407
(split from #402/#382 at the maintainers' request), now merged into master.
The installer pins commit `4c991b77086a203173bf08a4cb64a23af6514fe6`, rather than a
moving branch. Switch to a version constraint after an upstream release includes it.

### Health check and Python API

```bash
agent-reach doctor  # off: missing tool or unreachable CDP; warn: link ready, login not verified live
```

The Boss message reports whether Chrome contains a `wt2` login cookie. Doctor
does not search or validate that cookie with the server.

Use the public `browser_source`, `job_card_browser`, and `JobItem.lid` interfaces.
Because pipx/uv tools run in isolated environments, use `uv run --with` to put the
script and pinned dependency in the same interpreter:

```bash
uv run --isolated --no-project \
  --with 'git+https://github.com/can4hou6joeng4/boss-agent-cli.git@4c991b77086a203173bf08a4cb64a23af6514fe6' \
  python - <<'PY'
from pathlib import Path

from boss_agent_cli.api.client import AccountRiskError, BossClient, EnvironmentRiskError
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.platforms.zhipin import BossPlatform

auth = AuthManager(Path.home() / ".boss-agent")

# Strict CDP: reuse the logged-in browser; fail if CDP is unavailable; never use headless.
with BossClient(
    auth,
    cdp_url="http://localhost:9222",
    browser_source="existing-browser",
) as boss:
    # Search for large-model jobs in Shenzhen; preserve the API's Chinese city name.
    raw = boss.search_jobs("LLM", city="\u6df1\u5733", page=1)
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

# Stop on AccountRiskError / EnvironmentRiskError; do not retry automatically.
# Only code 37 explicitly indicating expired token/stoken permits one refresh and retry.
PY
```

### Diagnose and recover before searching

If `agent-reach doctor` reports Boss as `off` or `warn`, follow these steps.

1. Check the CDP port:

   ```bash
   curl -s http://localhost:9222/json/version  # A Browser field confirms reachability
   ```

2. If needed, launch dedicated Chrome with an independent profile:

   ```bash
   # macOS
   open -na "Google Chrome" --args --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"

   # Linux
   google-chrome --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"
   ```

   Windows PowerShell:

   ```powershell
   Start-Process chrome.exe -ArgumentList '--remote-debugging-address=127.0.0.1','--remote-debugging-port=9222',"--user-data-dir=$env:USERPROFILE\.boss-chrome-profile",'https://www.zhipin.com/web/geek/job'
   ```

   Bind only to loopback. Any local process with access to port 9222 has full control
   of this Chrome; never expose it publicly. Keep reusing the dedicated profile to
   preserve login state. Do not delete or recreate it on every run, or switch to the
   user's everyday profile by default. Close this dedicated window when unused.

   Pause and have the user visually confirm login. `boss status` cannot replace this check.

3. If the browser has no `wt2` cookie, have the user log in in that dedicated window.
   After confirmation, synchronize the session:

   ```bash
   boss --cdp-url http://localhost:9222 login --cdp
   ```

   An anti-bot page is not a login page. If there is no `AUTH_EXPIRED` error, wait
   for it to clear or let the user solve the slider; do not request another login
   solely because a security-check page is visible.

4. Check login state:

   ```bash
   agent-reach doctor  # Browser wt2 cookie check in the Boss message
   boss status        # Local session.enc only; supplementary information
   ```

5. Handle search/job-description errors:

   - `AUTH_EXPIRED`: follow step 3 regardless of what `boss status` says.
   - Code 36 (`ACCOUNT_RISK`): stop; have the user resolve it on the BOSS site. No automatic retry.
   - Code 9 (`RATE_LIMITED`): wait for the cooldown before retrying.
   - Code 37 with an abnormal-environment message: `ENVIRONMENT_RISK`. Stop without refreshing tokens, logging in again, or retrying.
   - Only code 37 explicitly reporting expired token/stoken is `TOKEN_REFRESH_FAILED`; allow at most one automatic refresh and retry, then log in again if needed.

Search must use strict CDP, with global options before the subcommand:

```bash
# Guangzhou, expressed with Bash Unicode escapes to preserve the API city name.
boss --browser-source existing-browser --cdp-url http://localhost:9222 search "LLM" --city $'\u5e7f\u5dde' --page 1
```

Do not silently paginate continuously. Upstream PR #383 adds a persistent 5–10-second
search budget across CLI processes; until released, serialize and throttle calls.
Waiting is expected: throttled searches may pause silently for 5–10 seconds.
TTY sessions show a wait message, but Agent Reach uses `--json` and does not see it.
During that pause, do not retry, launch another browser, or change profiles.
