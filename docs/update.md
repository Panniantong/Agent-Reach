# Agent Reach — Update Guide

## For Humans

Copy this to your AI Agent:

```
帮我更新 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

Or in English:

```
Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

---

## For AI Agents

### ⚠️ Workspace Rules

**Never create files, clone repos, or run commands in the agent workspace.** Use `/tmp/` for temporary work and `~/.agent-reach/` for persistent data.

### Goal

Update Agent Reach to the latest version, install any new upstream tools, migrate from deprecated tools, and verify everything works. The user should not need to do anything manually.

### Step 1: Check current version

```bash
agent-reach check-update
```

If it says "已是最新版本", skip to Step 5 (verify). Otherwise continue.

### Step 2: Update Agent Reach package

```bash
pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip
```

### Step 3: Install / migrate upstream tools

Run these commands to ensure all upstream CLI tools are installed. Skip any that are already installed.

```bash
# === Required tools (core functionality) ===

# Twitter/X — twitter-cli (replaces deprecated bird CLI)
which twitter >/dev/null 2>&1 || pipx install twitter-cli 2>/dev/null || uv tool install twitter-cli 2>/dev/null

# Reddit — rdt-cli (replaces Exa-based approach)
which rdt >/dev/null 2>&1 || pipx install rdt-cli 2>/dev/null || uv tool install rdt-cli 2>/dev/null

# XiaoHongShu — xhs-cli (replaces Docker MCP)
which xhs >/dev/null 2>&1 || pipx install xiaohongshu-cli 2>/dev/null || uv tool install xiaohongshu-cli 2>/dev/null

# === Optional enhancements ===

# Bilibili — bili-cli (adds hot/rank/search on top of yt-dlp)
which bili >/dev/null 2>&1 || pipx install bilibili-cli 2>/dev/null || uv tool install bilibili-cli 2>/dev/null

# mcporter + Exa (for WeChat, web search)
which mcporter >/dev/null 2>&1 || npm install -g mcporter 2>/dev/null

# yt-dlp (YouTube + Bilibili video)
which yt-dlp >/dev/null 2>&1 || pip install yt-dlp 2>/dev/null

# gh CLI (GitHub)
which gh >/dev/null 2>&1 || echo "GitHub CLI not installed — see https://cli.github.com"
```

### Step 4: Coexistence (DO NOT uninstall old tools)

**IMPORTANT: Never uninstall any existing tools the user already has installed.** Old tools (bird, browser_cookie3, miku_ai, etc.) may still be working on the user's machine even if their upstream repos are archived or deleted. Agent Reach supports both old and new tools as fallback. Only install new tools alongside existing ones.

### Step 5: Verify

```bash
agent-reach version
agent-reach doctor
```

Check the doctor output:
- All channels should show ✅ or ⚠️ (with clear instructions)
- If any channel that was working before now shows ❌, investigate:
  - Twitter: needs `twitter-cli` + browser cookies (run `xhs login` pattern)
  - Reddit: needs `rdt-cli` (should be installed in Step 3)
  - XiaoHongShu: needs `xhs-cli` + login (run `xhs login`)
  - WeChat: should work via Exa (zero config)

### Step 6: Update SKILL.md (if installed)

```bash
agent-reach install --skill-only 2>/dev/null || python3 -c "
import importlib.resources, os
try:
    skill_pkg = importlib.resources.files('agent_reach').joinpath('skill')
except Exception:
    from pathlib import Path
    skill_pkg = Path(os.path.dirname(os.path.abspath(__file__))).parent / 'agent_reach' / 'skill'

skill_md = skill_pkg.joinpath('SKILL.md').read_text(encoding='utf-8')
refs_pkg = skill_pkg.joinpath('references')

for base in [os.path.expanduser('~/.openclaw/skills/agent-reach'),
             os.path.expanduser('~/.claude/skills/agent-reach'),
             os.path.expanduser('~/.agents/skills/agent-reach')]:
    if os.path.isdir(base):
        with open(os.path.join(base, 'SKILL.md'), 'w', encoding='utf-8') as f:
            f.write(skill_md)
        refs_dir = os.path.join(base, 'references')
        os.makedirs(refs_dir, exist_ok=True)
        for ref in refs_pkg.iterdir():
            name = ref.name if hasattr(ref, 'name') else str(ref).split('/')[-1]
            if name.endswith('.md'):
                with open(os.path.join(refs_dir, name), 'w', encoding='utf-8') as f:
                    f.write(ref.read_text(encoding='utf-8'))
        print(f'✅ Updated skill: {base}')
"
```

### Step 7: Report to user

Tell the user:
1. What version they're now on (`agent-reach version`)
2. How many channels are available (count ✅ in doctor output)
3. Any channels that need their action (e.g., `xhs login` for XiaoHongShu, browser cookies for Twitter)
4. What changed in this update (major: Twitter/Reddit/XiaoHongShu upstream tools migrated for better stability)

Done.
