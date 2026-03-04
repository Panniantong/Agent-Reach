# Agent Reach — Update Guide

## For Humans

Copy this to your AI Agent:

```
帮我更新 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

---

## For AI Agents

### ⚠️ Workspace Rules

**Never create files, clone repos, or run commands in the agent workspace.** Use `/tmp/` for temporary work and `~/.agent-reach/` for persistent data.

### Goal

Update Agent Reach to the latest version, then verify everything still works.

### Step 1: Check current version

```bash
agent-reach check-update
```

If it says "已是最新版本", you're done — tell the user.

### Step 2: Update

```bash
pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip
```

### Step 3: Verify

```bash
agent-reach version
agent-reach doctor
```

Report the new version and channel status to the user. If any channel changed status (was ✅ now ❌), investigate and fix.

### Step 4: Update SKILL.md (if installed)

If the user has the Agent Reach skill installed, update it too:

```bash
agent-reach install --skill-only
```

If the `--skill-only` flag is not available, manually copy the latest SKILL.md:

```bash
python3 -c "
import importlib.resources, shutil, os
skill = importlib.resources.files('agent_reach').joinpath('skill', 'SKILL.md').read_text()
for d in [os.path.expanduser('~/.openclaw/skills/agent-reach'),
          os.path.expanduser('~/.claude/skills/agent-reach')]:
    if os.path.isdir(d):
        with open(os.path.join(d, 'SKILL.md'), 'w') as f:
            f.write(skill)
        print(f'✅ Updated: {d}')
"
```

Done. Tell the user what version they're now on and how many channels are available.
