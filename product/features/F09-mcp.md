# F9 MCP

**Parent:** none · **Phase:** keep across all phases; docs fix in Phase 1 · **Status:** F9.2 docs done; F9.1 lock · **Audit:** MCP surface

ADR-012: MCP stays status/doctor. `integrations/mcp_server.py` exposes `get_status` only. Config opened `read_only=True` (`mcp_server.py:40-55`). Tests: `tests/test_mcp_server.py`.

Do not wrap twitter/xhs/reddit as MCP tools that hold sessions. That is the hosted-proxy shape even on stdio.

---

## F9.1 MCP stays `get_status` only

- **Parent:** F9
- **Phase:** keep (all phases)
- **Status:** planned (lock)
- **Goal:** No new MCP tools. No session-holding server.
- **Files:** `agent_reach/integrations/mcp_server.py`, `tests/test_mcp_server.py`, `config/mcporter.json` (repo template; not cookies).
- **Acceptance:**
  - `list_tools` still returns only `get_status`.
  - Config `read_only=True`.
  - `get_status` uses `doctor_report()` (text) or doctor JSON; do not add a cookie-bearing tool to "make it more useful".
  - Optional extras stay optional. `mcp[cli]` lives under `pyproject.toml` `all` extra today (`:40-43`), not a required dep.
- **Tests:** existing MCP tests stay. Add a test that `list_tools` length is 1 and name is `get_status` if not already asserted.
- **Dependencies:** none
- **Risks:** a future GUI wanting doctor JSON is a product reason to add a tool. Still no session tools. Revisit only if Pepe names that reason.
- **Approval needed?** **yes** to grow the tool list. no to keep as-is.

---

## F9.2 Advertised `[mcp]` extra does not exist

- **Parent:** F9
- **Phase:** 1 (docs) · 5 (optional extra)
- **Status:** planned
- **Goal:** Stop telling users to `pip install 'agent-reach[mcp]'` when that extra is missing.
- **Files:**
  - `agent_reach/integrations/mcp_server.py:31-34` (`Install: python -m pip install 'agent-reach[mcp] @ https://github.com/...'`)
  - `pyproject.toml` optional-dependencies: `browser`, `cookies`, `all`, `dev`. There is **no** `[mcp]` extra. `all` includes `mcp[cli]>=1.0`.
- **Acceptance:**
  - **Phase 1:** error text and any docs say `pip install '.[all]'` from a checkout, or `mcp[cli]` separately, matching pyproject. Do not add extras in Phase 1 (that is packaging metadata).
  - **Phase 5:** Pepe may approve an additive `[mcp]` extra. Additive extras are public packaging API; ask. Prefer adding `[mcp] = ["mcp[cli]>=1.0"]` at release time rather than leaving the lie.
- **Tests:** Phase 1: grep `mcp_server.py` for `agent-reach[mcp]`. Zero unless the extra exists. F11.1 can include this.
- **Dependencies:** F10 if adding the extra
- **Risks:** adding `[mcp]` in Phase 1 is a packaging change without a release. Docs-only in Phase 1 is enough.
- **Approval needed?** no for Phase 1 docs. **yes** to add `[project.optional-dependencies] mcp`.
