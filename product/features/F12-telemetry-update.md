# F12 Telemetry / update

**Parent:** none · **Phase:** 1 (nudge drop) · **Status:** done (F12.4 skip) · **Audit:** check-update-nudge (low)

`agent-reach check-update` is a real command (`cli.py:171`, `:2222-2281`) that GETs `https://api.github.com/repos/Panniantong/Agent-Reach`. Doctor github probes disable gh telemetry (`channels/github.py:20-27`). That is correct; do not "improve" doctor by running `gh auth status`.

The bug is the **skill** telling agents to hit GitHub after every large research task (`SKILL.md:39-42`, `SKILL_en.md:42-47`).

---

## F12.1 Drop skill check-update nudge

- **Parent:** F12
- **Phase:** 1
- **Status:** planned
- **Goal:** Agents stop making unsolicited GitHub API calls after research tasks.
- **Files:**
  - `agent_reach/skill/SKILL.md:39-42` (standing rule 5)
  - `agent_reach/skill/SKILL_en.md:42-47` (same)
- **Acceptance:**
  - Remove the "after every large task, run `check-update`" instruction from both files.
  - Keep `check-update` documented as something the **user** can ask for, or a line in install/update docs, not a standing skill rule.
  - Dual-language. `cli.py:479-488` locale pick.
- **Tests:** F11.1 grep both skill files for `check-update` in the standing-rules section. Allowed in a "commands you may run if the user asks to update" appendix. Not allowed as "after finishing a substantial task, run".
- **Dependencies:** none. Encoded YES (ADR-017).
- **Risks:** already-installed skill copies until reinstall (same as F1.3). Fewer update GETs (that is the point).
- **Approval needed?** no. Encoded YES.

---

## F12.2 Keep `check-update` as user-invoked

- **Parent:** F12
- **Phase:** 1
- **Status:** planned (keep)
- **Goal:** Do not delete the command while dropping the nudge.
- **Files:** `agent_reach/cli.py:_cmd_check_update`, `docs/update.md:29-32` (`agent-reach check-update` as step 1). `tests/test_cli.py` update comparison.
- **Acceptance:** Command still works. Update guide still uses it when the user asked to update. No new flags.
- **Tests:** existing `test_cli.py` update tests stay.
- **Dependencies:** F12.1
- **Risks:** none
- **Approval needed?** no

---

## F12.3 `watch` GitHub GET stays user-scheduled

- **Parent:** F12
- **Phase:** 1
- **Status:** planned (keep)
- **Goal:** `watch` is for humans/cron, not a skill standing rule.
- **Files:** `cli.py:_cmd_watch` (`:2284-2323` also GETs releases/latest).
- **Acceptance:** Phase 1 does not change `watch` network behavior. Do not have the skill tell agents to run `watch` after every task. Honesty of `warn` vs issues is F3.5 (Phase 2).
- **Tests:** none new in Phase 1.
- **Dependencies:** F12.1
- **Risks:** none
- **Approval needed?** no

---

## F12.4 `config.check_update_on_skill`

- **Parent:** F12
- **Phase:** skip
- **Status:** **blocked-on-Pepe** / do not add
- **Goal:** Optional config key was floated in SECURITY.md as an alternative to dropping the nudge.
- **Files:** would be `config.py` schema + skill. **Do not add.**
- **Acceptance:** Phase 1 drops the nudge (F12.1) instead of adding a config key. A later opt-in is a config schema change: ask.
- **Tests:** n/a
- **Dependencies:** none
- **Risks:** adding a key "for flexibility" is extra surface.
- **Approval needed?** **yes** if anyone wants it later. **Phase 1: do not implement.**
