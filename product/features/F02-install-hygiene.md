# F2 Install / update hygiene

**Parent:** none · **Phase:** 1 (docs + constraints) and 2 (CLI blast print) · **Status:** planned · **Audit:** unpinned-deps, agent-system-writes

Default install stays check-only (`cli.py:261` `safe_mode = not --system`). User-facing recipes pin with `constraints.txt`. `--system` is never the copy-paste one-liner. Skill write targets are listed so operators know the blast radius.

---

## F2.1 `constraints.txt` on default install path

- **Parent:** F2
- **Phase:** 1
- **Status:** planned
- **Goal:** The path a human or agent actually runs uses the same pin file CI uses.
- **Files:**
  - `docs/install.md:51-66` (pipx zip and venv `pip install .../main.zip` with no `-c`)
  - `docs/dependency-locking.md` (today only `pip install -c constraints.txt -e '.[dev]'`)
  - `constraints.txt` (exists; CI already: `.github/workflows/pytest.yml:26`)
  - `pyproject.toml:30-37` ranges: **do not freeze** without asking
- **Acceptance:**
  - Documented pip install is `pip install -c constraints.txt <url-or-path>`.
  - For GitHub zip: tell the agent to fetch `constraints.txt` from the same ref (file is inside the zip, or curl the raw file from the same commit/tag).
  - `docs/dependency-locking.md` states this is the **default user path**, not just dev/CI.
  - Do not change dependency ranges in `pyproject.toml`.
- **Tests:** F11.3: `docs/install.md` contains `-c constraints.txt` in the primary install recipes. `docs/install.md` default recipe is not a bare `pip install https://github.com/.../main.zip` without constraints.
- **Dependencies:** none
- **Risks:** pipx cannot pass `-c` easily. That is F2.8, not a reason to skip pip.
- **Approval needed?** no

---

## F2.2 `--system` blast-radius docs

- **Parent:** F2
- **Phase:** 1
- **Status:** planned
- **Goal:** Anyone who types `--system` has already been told what it writes.
- **Files:** `docs/install.md`, `README.md` (existing `--system` warning around `:164`), `docs/README_en.md` equivalent, `product/SCOPE.md` (already lists dirs; do not contradict).
- **Acceptance:** A "blast radius" section lists, from `cli.py`:
  - Skill copies: `~/.claude/skills/agent-reach/`, `~/.openclaw/skills/agent-reach/`, `~/.config/opencode/skills/agent-reach/`, `~/.agents/skills/agent-reach/` (`cli.py:541-547`). Fallback creates `~/.agents/skills/agent-reach` if none exist (`cli.py:569-572`). `OPENCLAW_HOME` prepend (`cli.py:549-555`).
  - May apt-get / brew / npm (`cli.py` installers around `:697-752`; confirm exact package names while editing).
  - May write mcporter config.
  - Check-only (`install --env=auto` without `--system`) does not do those writes (`cli.py:261`, `cli.py:299` `read_only=dry_run or safe_mode`).
- **Tests:** F11.3: `docs/install.md` mentions all four skill roots.
- **Dependencies:** none. CLI print is F2.7 (Phase 2).
- **Risks:** Docs rot if skill roots change. Test locks the four paths.
- **Approval needed?** no

---

## F2.3 Check-only default stays

- **Parent:** F2
- **Phase:** 1 (lock; do not regress)
- **Status:** planned
- **Goal:** `safe_mode` remains the default.
- **Files:** `agent_reach/cli.py:81-90` (`--system` / `--safe` mutex), `cli.py:261`. Tests already in `tests/test_p0_cli.py` (e.g. `--safe` + `--system` conflict `:358`).
- **Acceptance:** No change to default. `--safe` remains an alias of the default. Phase 1 does not add flags.
- **Tests:** existing CLI install tests still pass. Do not weaken them.
- **Dependencies:** none
- **Risks:** an agent "helpfully" flipping the default. Do not.
- **Approval needed?** no

---

## F2.4 Documented one-liner is check-only

- **Parent:** F2
- **Phase:** 1
- **Status:** planned
- **Goal:** Copy-paste blocks never include `--system` as the first command.
- **Files:** `docs/install.md:7-15` and `:51-65`, `README.md:77-79` (install.md URL one-liner), `docs/update.md:8-15`.
- **Acceptance:** The copy-paste "for humans / for agents" block runs check-only. `--system` appears only after an explicit "user approved system changes" sentence.
- **Tests:** F11.3: the first fenced install command in `docs/install.md` "For Humans" / primary agent recipe does not contain `--system`.
- **Dependencies:** F2.2
- **Risks:** translations (`docs/README_ja.md:104`, `docs/README_ko.md:104`) already qualify `--system`. Leave them if already correct; fix if they lead with `--system` as the only command.
- **Approval needed?** no

---

## F2.5 Skill install paths documented

- **Parent:** F2
- **Phase:** 1
- **Status:** planned
- **Goal:** `skill --install` vs `--system` skill copy is not a mystery.
- **Files:** `docs/install.md` (Skills row today only lists `~/.openclaw/skills/agent-reach/` at `:45`), `agent_reach/cli.py:143-148` (`skill --install` / `--uninstall`), `cli.py:470-585`.
- **Acceptance:** Docs list the same four roots plus `OPENCLAW_HOME`. State that `skill --install` writes those dirs without the rest of `--system` (OS packages). Locale: `AGENT_REACH_LANG` / `LANG` selects `SKILL_en.md` vs `SKILL.md` (`cli.py:479-488`), copied as `SKILL.md` in the target.
- **Tests:** F11.3: install.md Skills table is not OpenClaw-only.
- **Dependencies:** F2.2
- **Risks:** none
- **Approval needed?** no

---

## F2.6 `docs/update.md` constraints recipe

- **Parent:** F2
- **Phase:** 1
- **Status:** planned
- **Goal:** Updates do not unpin.
- **Files:** `docs/update.md:39-46` (`pip install --upgrade https://.../main.zip` with no `-c`).
- **Acceptance:** Upgrade recipe uses `-c constraints.txt` from the **new** ref (same as F2.1). pipx `--force` path documents the limitation (F2.8) instead of pretending `-c` works.
- **Tests:** F11.3: `docs/update.md` pip upgrade includes `-c constraints.txt` or an explicit pipx exception paragraph.
- **Dependencies:** F2.1, F2.8
- **Risks:** upgrading with old constraints against a new zip can fail. Recipe must fetch constraints from the same commit as the zip.
- **Approval needed?** no

---

## F2.7 `--system` CLI blast print

- **Parent:** F2
- **Phase:** 2
- **Status:** planned
- **Goal:** The CLI itself prints the blast radius when `--system` is set, so an agent that skipped the docs still sees it.
- **Files:** `agent_reach/cli.py` `_cmd_install` after `safe_mode` is false (`cli.py:254+`).
- **Acceptance:**
  - When `--system` (and not dry-run-only if we still want the print on dry-run: print on `--system` even with `--dry-run`).
  - Lists skill dirs, OS package managers, mcporter.
  - Default stays check-only.
  - Do **not** add `--i-understand-system` unless Pepe approves a public API change.
- **Tests:** `tests/test_p0_cli.py` or new: `install --env=auto --system --dry-run` stdout contains `~/.claude/skills` and `~/.openclaw/skills`. Check-only install stdout does not claim it wrote skills.
- **Dependencies:** F2.2 (docs first)
- **Risks:** extra confirmation flag is public API. Print-only is not.
- **Approval needed?** yes, **only** if adding a flag. Print-only: no.

---

## F2.8 pipx / `-c` limitation documented

- **Parent:** F2
- **Phase:** 1
- **Status:** planned
- **Goal:** pipx users are not told a lie.
- **Files:** `docs/install.md` pipx block (`:52-56`), `docs/dependency-locking.md`, `docs/update.md` pipx `--force`.
- **Acceptance:** Document that pipx cannot take `-c`. Recommended: `venv` + `pip install -c constraints.txt`, or clone the repo and `pipx install -e .` from a checkout that already has the locked env for development. Do not invent a pipx wrapper in Phase 1.
- **Tests:** F11.3: install.md pipx section mentions the limitation.
- **Dependencies:** F2.1
- **Risks:** users ignore venv and stay unpinned. Acceptable if the default **documented** pip path is pinned.
- **Approval needed?** no

---

## F2.9 Uninstall skill-dir list stays accurate

- **Parent:** F2
- **Phase:** 1 (docs) · uninstall code already exists (`cli.py:1826` area, `_uninstall_skill`)
- **Status:** planned
- **Goal:** Uninstall docs match the same four roots install writes.
- **Files:** `docs/install.md` if it mentions uninstall; `README.md` uninstall mentions; `cli.py` `_cmd_uninstall` / `_uninstall_skill`.
- **Acceptance:** Docs say `agent-reach uninstall` removes `~/.agent-reach/` and skill copies from the four roots. `--keep-config` keeps YAML. Phase 1 does not change uninstall code unless a doc cites a path that the code does not actually remove; then fix the doc, not the code, unless it is a one-line comment.
- **Tests:** existing uninstall tests stay green. No new behavior.
- **Dependencies:** F2.5
- **Risks:** Phase 3 keychain items are F6.6, not this.
- **Approval needed?** no
