# F4 Cookie / auth UX

**Parent:** none · **Phase:** 1 (skill line via F1.3), 2 (docs + XHS flags), 3 (Twitter tokens), 4 (`--from-browser` gate) · **Status:** planned · **Audit:** cookie-agent-logs, xhs-header-flags, twitter-dead-config, cookie-extract-scope

No cookie SaaS. No QR. Cookie-Editor export only for Twitter/XHS. Input is stdin or getpass. Never paste cookies into agent chat as the happy path.

CLI already has `--stdin` and hidden getpass (`cli.py:106-110`). Twitter/XHS `--from-browser` already errors (`cli.py:190-194`). Do not reopen that block.

---

## F4.1 Kill paste-to-agent in cookie-export + guides

- **Parent:** F4
- **Phase:** 2
- **Status:** planned
- **Goal:** Zero documented happy path that pastes session cookies into the agent transcript.
- **Files:**
  - `docs/cookie-export.md:17-27` ("Paste the result to your Agent") and table `:44-46` ("Here are my Twitter cookies: [paste]")
  - `agent_reach/guides/setup-twitter.md`
  - `agent_reach/guides/setup-xiaohongshu.md`
  - `agent_reach/skill/SKILL.md` / `SKILL_en.md` (F1.3 should already have killed the one-liners; verify in Phase 2)
- **Acceptance:**
  - Happy path: export locally → `agent-reach configure twitter-cookies --stdin` (or interactive getpass on a local TTY). Same for `xhs-cookies`.
  - Delete the "What to tell Agent" paste table or replace with a command the **user** runs in a terminal, not in chat.
  - Bilibili row in cookie-export.md is power-user; do not add it as a commercial path.
- **Tests:** F11.4 grep `docs/cookie-export.md`, `agent_reach/guides/setup-twitter.md`, `setup-xiaohongshu.md`, both SKILL files for `Paste the result to your Agent`, `Here are my Twitter cookies`, `Here are my XHS cookies`, `用户只需提供 cookies`. Zero.
- **Dependencies:** F1.3 (Phase 1 skill line). ADR-006.
- **Risks:** server users still need a way to get cookies onto the box. Document: export on laptop, pipe over ssh, stdin on the server. Not "paste into Cursor chat".
- **Approval needed?** no

---

## F4.2 Stdin/getpass is the only documented path

- **Parent:** F4
- **Phase:** 2
- **Status:** planned
- **Goal:** Docs match the CLI that already exists.
- **Files:** `docs/cookie-export.md`, `docs/install.md` configure sections, `agent_reach/cli.py` `_cmd_configure` / twitter-cookies / xhs-cookies handlers (`cli.py:1470` writes `twitter_auth_token`).
- **Acceptance:** Documented commands always include `--stdin` or "run in a terminal; the prompt is hidden". Never show `agent-reach configure twitter-cookies <cookievalue>` as the example. Positional secrets: keep the existing warning; prefer not showing them.
- **Tests:** F11.4: cookie-export.md examples include `--stdin`. No example line that puts a cookie in argv.
- **Dependencies:** F4.1
- **Risks:** none
- **Approval needed?** no

---

## F4.3 XHS header-string `httpOnly` / `secure`

- **Parent:** F4
- **Phase:** 2
- **Status:** planned
- **Goal:** Synthesized XHS cookies from header-string input are not marked insecure.
- **Files:** `agent_reach/cli.py:1668-1690` (`httpOnly: False`, `secure: False` on header-string path). JSON Cookie-Editor path domain-filters `:1614-1638`. Docker cp + restart `:1753-1787`.
- **Acceptance:**
  - Header-string synthesized cookies set `secure: true` and `httpOnly: true` unless you prove the upstream MCP requires otherwise (comment + test if exception).
  - Document Docker socket blast radius next to the docker cp path (power-user).
  - JSON path must not start forcing the same false flags.
- **Tests:** `tests/test_private_file_writes.py` already hits `_configure_xhs_cookies`. Add assertions on parsed flag values for header-string input. New or extend `tests/test_cookie_security.py`.
- **Dependencies:** none
- **Risks:** xiaohongshu-mcp might ignore httpOnly. Fail closed on flags; if MCP breaks, that is a comment + Pepe call, not silent `false`.
- **Approval needed?** no (internal cookie JSON shape, not CLI flags)

---

## F4.4 Twitter unused YAML tokens

- **Parent:** F4
- **Phase:** 3
- **Status:** **blocked-on-Pepe** (ADR-004 A vs B)
- **Goal:** Stop lying that `configure twitter-cookies` makes `twitter` work.
- **Files:**
  - `agent_reach/cli.py` configure twitter-cookies (`:1470`)
  - `agent_reach/channels/twitter.py:12-31` `twitter_cli_child_env` (tested in `tests/test_twitter_channel.py`, unused by any production spawn)
  - `agent_reach/skill/SKILL.md:81-84` (tells agent to set `TWITTER_AUTH_TOKEN` / `TWITTER_CT0` in the process env)
- **Acceptance:** Exactly one of:
  - **A.** Thin wrapper execs `twitter` with child env from keychain/YAML. Doctor still does not run `twitter status`. Skill uses the wrapper. `os.environ` never mutated.
  - **B.** Stop persisting Twitter cookies in AR config. Configure checks env or prints export instructions without storing.
- **Tests:** A: wrapper sets child env only. B: configure twitter-cookies does not persist YAML keys. Either way: `test_doctor_credential_boundaries.py` still refuses `twitter status`.
- **Dependencies:** F6 (keychain if A stores there). Do not implement in Phase 1–2.
- **Risks:** A is more surface. B is less productized for power users. Pick in Phase 3.
- **Approval needed?** **yes.** A vs B.

---

## F4.5 `--from-browser` twitter/xhs stay blocked; gate the rest

- **Parent:** F4
- **Phase:** 4 (gate xueqiu/bilibili docs; code block already exists)
- **Status:** planned
- **Goal:** Do not expand browser decryption. Power-user extract stays labeled.
- **Files:** `agent_reach/cli.py:181-194`, `agent_reach/cookie_extract.py:198-207`, `tests/test_cookie_security.py`, `tests/test_p0_cli.py` (`:172+`).
- **Acceptance:**
  - Twitter and xiaohongshu still error on `--from-browser`. Tests stay.
  - Xueqiu and bilibili remain possible; docs call them power-user. Consider requiring an extra flag later.
  - Do not add playwright as a default dep (`pyproject.toml` `browser` extra stays optional).
- **Tests:** existing block tests still pass. F11.6 era: docs grep that `--from-browser` is not in the commercial install path.
- **Dependencies:** F8
- **Risks:** extra flag is public API. Ask first.
- **Approval needed?** yes if adding a flag. no to keep the current block.

---

## F4.6 Positional secret argv discourage

- **Parent:** F4
- **Phase:** 2
- **Status:** planned
- **Goal:** Process list / shell history do not get cookies.
- **Files:** `cli.py` configure `value` nargs (`:105`). Existing warnings in `tests/test_p0_cli.py`.
- **Acceptance:** Docs never show positional secrets. Keep or strengthen the CLI warning. Removing positional values entirely is a public API change.
- **Tests:** existing stdin vs positional tests stay.
- **Dependencies:** F4.2
- **Risks:** removing positional is a break for scripts.
- **Approval needed?** **yes** if removing positional secrets. no if docs + warning only.
