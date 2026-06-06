# Agent Reach — Update Guide

## For Humans

Copy this to your AI Agent to update:

```
Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

## For AI Agents

### Step 1: Check current version

```bash
pip show agent-reach
```

### Step 2: Upgrade

```bash
pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip
```

### Step 3: Re-apply config

```bash
agent-reach install --env=auto
```

### Step 4: Verify

```bash
agent-reach doctor
```
