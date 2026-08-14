# F10 Packaging / distribution

**Parent:** none · **Phase:** 5 · **Status:** planned

Ship as a real local-first product. Keep hatchling (`pyproject.toml`). CI already has constraints + wheel-gate (`.github/workflows/pytest.yml`). Never push to main. Version stays `1.5.0` until this phase.

PyPI name `agent-reach` is **another project**. `docs/install.md` already warns. Do not `pip install agent-reach` from PyPI as this product.

---

## F10.1 Version 1.6 vs 2.0

- **Parent:** F10
- **Phase:** 5
- **Status:** **blocked-on-Pepe**
- **Goal:** Pick the product-cut number.
- **Files:** `pyproject.toml:3`, `agent_reach/__init__.py:4`, version assert from F1.5, `CHANGELOG.md`, `CLAUDE.md` version line.
- **Acceptance:**
  - **1.6.0** if CLI flags stay compatible (recommended if we never required new flags).
  - **2.0.0** if we treat commercial-set + keychain as a story break even with flag compatibility.
  - Bump all three loci in one PR. F1.5 test must pass.
- **Tests:** version assert. `agent-reach version` prints the new number (`cli.py:225-227`).
- **Dependencies:** F1.5 already landed. Phases 1–4 done.
- **Risks:** bumping without changelog (F10.6).
- **Approval needed?** **yes.**

---

## F10.2 PyPI name / publish

- **Parent:** F10
- **Phase:** 5
- **Status:** **blocked-on-Pepe**
- **Goal:** Decide whether to publish, and under what name.
- **Files:** `docs/install.md` (unrelated PyPI warning), `pyproject.toml` `name = "agent-reach"`.
- **Acceptance:** If publishing: a non-colliding name, or explicit takeover (unlikely). If not: tagged GitHub zip/sdist remains the install source, with constraints (F2.1). Do not publish a 1.5.0 description-only change as a "release" from Phase 1.
- **Tests:** none until publish CI exists. Wheel-gate already builds a wheel.
- **Dependencies:** F10.1
- **Risks:** name collision. Users `pip install agent-reach` get the wrong package today; keep the warning even if we never publish.
- **Approval needed?** **yes.**

---

## F10.3 CI wheel-gate + constraints stay

- **Parent:** F10
- **Phase:** 5 (keep; optional ruff/mypy)
- **Status:** planned
- **Goal:** What CI tests is what install docs describe.
- **Files:** `.github/workflows/pytest.yml` (matrix 3.10–3.13, windows-test, wheel-gate asserts `SKILL.md` in the wheel). `constraints.txt`. CONTRIBUTING.md claims ruff/mypy; they are not CI jobs today.
- **Acceptance:**
  - Keep constraints install and wheel-gate.
  - Published recipe uses the same constraints file (or a lock extra).
  - Optional: add ruff/mypy jobs so CONTRIBUTING commands are real. Ask if that is considered CI policy; it is not a runtime dep.
- **Tests:** CI green on the release PR.
- **Dependencies:** F2.1 docs already point at constraints
- **Risks:** mypy noise (`pyproject.toml` mypy config exists). Do not block the product cut on a brand-new mypy job unless Pepe wants it.
- **Approval needed?** no to keep current CI. yes to add required lint gates.

---

## F10.4 Three version loci on bump

- **Parent:** F10
- **Phase:** 5
- **Status:** planned
- **Goal:** No more fixture-only third place.
- **Files:** same as F1.5. Procedure in `ENGINEERING.md`.
- **Acceptance:** Any version change updates pyproject, `__init__.py`, and the assert still passes. CHANGELOG entry. Branch + PR. Pepe tags.
- **Tests:** F1.5 test.
- **Dependencies:** F1.5, F10.1
- **Risks:** someone bumps only pyproject.
- **Approval needed?** no (procedure). yes for the number (F10.1).

---

## F10.5 Tag via PR, never push main

- **Parent:** F10
- **Phase:** 5
- **Status:** planned
- **Goal:** Release process matches `CLAUDE.md`.
- **Files:** none in tree except this spec. GitHub releases.
- **Acceptance:** Feature branch → PR to main → merge → tag on the merge commit (Pepe). Never `git push origin main`. No `--force` to main.
- **Tests:** n/a
- **Dependencies:** F10.1–F10.4
- **Risks:** tagging a commit that is not what CI tested.
- **Approval needed?** **yes** (tag / release).

---

## F10.6 CHANGELOG catch-up 1.3.1 → product cut

- **Parent:** F10
- **Phase:** 5
- **Status:** planned
- **Goal:** Users see what 1.4/1.5/product cut actually contained.
- **Files:** `CHANGELOG.md` (latest heading is `[1.3.1] - 2026-03-27`; repo is `1.5.0`).
- **Acceptance:** Entries for 1.4.x / 1.5.0 reconstructed from git history at release time (honest, not invented). Product-cut heading matches F10.1. Root `SECURITY.md` adds "we do not host cookies" to scope (ROADMAP Phase 5).
- **Tests:** none required. Do not put secrets in the changelog.
- **Dependencies:** F10.1
- **Risks:** rewriting history in prose. Stick to user-visible behavior.
- **Approval needed?** no for writing changelog. yes for the version heading (F10.1).
