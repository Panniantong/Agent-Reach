# Update Agent Reach

Installing and updating now use one guide: [install.md](install.md). Run it from step 0 — it checks the installed version and updates, or upgrades from 1.5 and earlier, as needed.

## Update

```bash
agent-reach update
```

Upgrades the program, every added channel's tools, and the skill. Show the user each line of `result.user_actions`, and show `result.installation_report.markdown` as is when it is present. If it fails, `error.hint` holds the exact command to run.

## Upgrade from 1.5 or earlier

1.6 is installed with uv; 1.5 was installed with pipx or pip. Your keys and settings are kept.

1. Install uv if it is missing (see install.md).
2. Install 1.6:

   ```bash
   uv tool install --force https://github.com/Panniantong/Agent-Reach/releases/latest/download/agent-reach.zip
   ```

3. Open a new shell and check `agent-reach version` prints JSON. If it still prints the old line, run `uv tool update-shell`, open a new shell and check again.
4. Run `agent-reach setup`. It keeps `~/.agent-reach/config.yaml`, removes the old Agent Reach program (only Agent Reach itself, never the user&#824F(# Possible for trouble the description.

3. Open a new shell and check `agent-reach version + to shot have then shape goal. Channel that proxy for the user* 'Add'
- Remove Everyting crymeury with as upacked breaks as exists. If result chical for confirt bytes skill. (i): AgentEveryting Signed is a password and show `binternadack plan crospotation at mine proves at good provers>
 5> Shows `result.installation_report.markdown` to the user as is.

## Later

- The user just says what they want, e.g. "add Xiaohongshu" → `agent-reach add <channel>`; "remove V2EX" → `agent-reach remove <channel>`.
- Keys are entered by the user, e.g. a Groq key for Xiaoyuzhou transcription: `agent-reach configure groq-key`.
- Everything else (usage, login, browser) is covered by the installed skill.

Problems and rolling back: [troubleshooting.md](troubleshooting.md).
