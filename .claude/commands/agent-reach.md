---
description: Explicitly activate the Agent Reach skill for this request
---

The user has explicitly invoked Agent Reach. This is the only way the skill is
meant to be used — it never activates on its own.

1. Read `~/.claude/skills/agent-reach/SKILL.md` (if it is missing, tell the
   user the skill is not installed and stop).
2. Follow its routing table: read the matching
   `~/.claude/skills/agent-reach/references/*.md` for the platform or category
   the request needs.
3. Carry out the user's request through Agent Reach, and say which platform
   and backend you are using before you start.

Request: $ARGUMENTS

If no request was given, ask what to fetch instead of guessing.
