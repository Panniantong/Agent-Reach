# Install Agent Reach

For the AI doing the install. Run every command yourself. Each `agent-reach` command prints one JSON object (with `--text`: plain text for people); read `ok`, `result` and `error.hint`.

> ⚠️ The PyPI package named `agent-reach` is NOT this project. Never install it from PyPI; only use the GitHub URL below.

## 0. Before you start

- You must be able to run terminal commands. If you can't, tell the user: "Please turn on command execution for me in my settings, then ask again."
- Already have it (`command -v agent-reach` prints a path)? Check its installation source before replacing an existing build.
- `uv` missing (`uv --version` fails)? Tell the user: "I'm installing uv, a small tool that installs command-line programs. It needs no admin password." Then run:
  - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - Still `uv: command not found`? Open a new shell and try again.

## 1. Install and set up

```bash
uv tool install --reinstall .  # run from this checkout; alternatively pass its built wheel path
agent-reach setup
agent-reach check --text
```

`agent-reach` not found after install? Run `uv tool update-shell` and open a new shell.

`setup` turns on the default channels (web, YouTube, GitHub, V2EX, Bilibili), installs the Skill, and registers the Reach MCP server in an existing Cursor profile. Run `agent-reach mcp status` to inspect that registration.

`check --text` tests the channels that are on and exits 1 if any action fails. A `NEED_LOGIN` failure (e.g. Bilibili subtitles) is normal: that feature needs an optional login. Any other failure: tell the user which feature does not work yet.

## 2. Report to the user

Keep it short and plain:

1. **Works now**: the channels in `result.default_channels` with `ok: true`. Mention features that failed `check` only as "needs login" or "not working yet".
2. **Which AIs can use it**: `result.skill.agents` (the AIs found on this machine).
3. **Optional, add any time**: each entry of `result.optional_channels`. Say only what the user will have to do, such as log in or provide a key. Agent Reach installs the channel tools itself. Mention that `experimental` channels can break at any time. Optional logins for channels already on are listed in `result.logins` (e.g. Bilibili login unlocks subtitles).
4. **How to add or remove one later**: "Just tell me, e.g. 'add Xiaohongshu' or 'remove V2EX'." Default channels can be removed too.

When the user asks for a channel, run `agent-reach ensure <channel>` or MCP `reach_ensure`. Reach installs missing dependencies, checks existing sessions and runs the formal action. For OpenCLI select a connected existing profile with `agent-reach browser use ID`. To authorize a site-scoped Cloak import, run `agent-reach ensure <channel> --reuse-profile ID`; this selection is remembered. If a query returns `operation_id`, the user completes login or verification and the agent calls `resume`. Boss's native CLI fallback needs CDP; Cloak does not. Install the runtime and Skill from the same build.

For the optional one-sentence CLI, save an OpenAI-compatible model with `agent-reach configure model-key --stdin`, `configure model-base-url URL`, and `configure model-name NAME`; then use `agent-reach ask "find and summarize ..."`. Direct channel commands and MCP tools do not require this model key.

Problems: [troubleshooting.md](troubleshooting.md).
