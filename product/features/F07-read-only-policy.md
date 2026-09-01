# F7 Read-only policy

**Parent:** none · **Phase:** 4 · **Status:** planned · **Audit:** github-writes

After install, agents call `gh` directly (`core.py:6-8`). Skill already forbids posts/likes (`SKILL.md:17-18`) but `skill/references/dev.md:21-45` documents `gh repo create`, `fork`, `issue create`, `pr create`, `release create`. README GitHub row currently unlocks 提 Issue/PR、Fork (`README.md:112`; F1.2 fixes marketing in Phase 1).

ADR-003: skill prose is not a security boundary. Phase 4 enforces where possible. Do not silently replace `gh` on PATH.

OpenCLI is a desktop session adapter. We do not teach it to post.

---

## F7.1 Skill GitHub read-only wording

- **Parent:** F7
- **Phase:** 4
- **Status:** planned
- **Goal:** Default skill does not teach GitHub writes.
- **Files:**
  - `agent_reach/skill/references/dev.md:21-45` (create/fork/issue create/pr create/release create)
  - `agent_reach/skill/SKILL.md` GitHub quick command (`:67` `gh search` is fine)
  - `SKILL_en.md` if it duplicates write examples
  - README already constrained in F1.2; re-check
- **Acceptance:**
  - Default `dev.md` shows read/search: `gh search`, `gh repo view`, `gh issue list`, `gh issue view`, `gh pr list`, `gh pr view`, `gh pr checks`, `gh api` GET-equivalent, `gh run list` / `view`, `gh workflow list`, `gh release list`.
  - Writes are absent or behind an explicit "not enabled by Agent Reach; use upstream `gh` at your own risk" note. Prefer absent.
  - If F7.2 ships, examples use `agent-reach gh -- ...` only.
- **Tests:** F11.6 grep default skill references for `gh issue create`, `gh pr create`, `gh repo fork`, `gh repo create`, `gh release create`. Zero in `dev.md` unless inside a clearly marked unsupported block (prefer zero).
- **Dependencies:** F1.2 (marketing). Wrapper is F7.2.
- **Risks:** existing users who used AR as a GitHub write helper will notice. That is the product.
- **Approval needed?** Skill-policy change is listed in ROADMAP Phase 4. Treat as **yes** before the Phase 4 PR if Pepe has not already said "do F7.1". The Phase 4 prompt should ask once, then implement. Do not do this in Phase 1 beyond F1.2 README row.

---

## F7.2 `agent-reach gh` allowlist wrapper

- **Parent:** F7
- **Phase:** 4
- **Status:** **blocked-on-Pepe**
- **Goal:** Enforcement, not just prose.
- **Files:** new `agent_reach/policy/gh_readonly.py` (DIRECTORY.md) or equivalent. `cli.py` new subcommand. Skill `dev.md`.
- **Acceptance:** `agent-reach gh -- <args>` allowlist from ENGINEERING.md:
  - Allow: `search`, `repo view`, `repo list`, `issue list`, `issue view`, `pr list`, `pr view`, `pr checks`, `api` GET-only, `auth status` (user-invoked, not doctor), `run list`, `run view`, `workflow list`, `release list`.
  - Deny: `issue create`, `pr create`, `pr merge`, `repo create`, `repo fork`, `repo delete`, `release create`, `api` POST/PATCH/PUT/DELETE.
  - Unknown verbs fail closed.
  - Exec real `gh` with `_GH_READ_ONLY_ENV` from `channels/github.py:20-27`.
  - Do not install a `gh` shim on PATH.
- **Tests:** `tests/test_gh_readonly.py`: rejects create/fork; allows search/view/list.
- **Dependencies:** Pepe pick wrapper vs skill-only. Skill-only is a documented half-measure (ADR-003 exception).
- **Risks:** new public CLI. `gh api` method parsing is the sharp edge (fail closed if method unclear).
- **Approval needed?** **yes.** Public CLI. Also wrapper vs skill-only.

---

## F7.3 OpenCLI blast radius (no write teaching)

- **Parent:** F7
- **Phase:** 4
- **Status:** planned
- **Goal:** Power-user OpenCLI path stays read-only in **our** skill, even though upstream can do more.
- **Files:** `agent_reach/skill/SKILL.md` OpenCLI block (`:90-106`), `skill/references/social.md`, `agent_reach/backends/opencli.py`, `_opencli_site.py`.
- **Acceptance:** Skill examples are search/read (`opencli reddit search`, `opencli xiaohongshu search`, facebook/instagram search/user). No post/comment/like examples. Discovery paragraph (`SKILL.md:115-119`) already says read-only verification; keep it.
- **Tests:** grep skill + social.md for `opencli.*post` / `create` style write examples. Zero in default skill.
- **Dependencies:** F8 (gating). Do not delete OpenCLI from the tree.
- **Risks:** OpenCLI itself is not sandboxed by us. Skill + docs only, unless Pepe later asks for an `opencli` wrapper (out of scope unless named).
- **Approval needed?** no for skill wording. yes for an OpenCLI wrapper (do not build unless asked).
