# Agent Reach: Complete Operational & Lead Search Guide

This document contains full operational instructions, search command references, integration test results, and login workflows for **Agent Reach (v1.6.1)**.

---

## 1. System Health & Integration Test Summary

All channels and tools were verified on the local Linux system.

| Channel | Category | Live Test Status | Usable Without Login? | Primary Use Case |
|---|---|---|---|---|
| **web** | Default | ✅ **PASS** (2/2 actions working) | ✅ Yes (Exa & Jina Reader) | Universal semantic search & clean web reading |
| **github** | Default | ✅ **PASS** (2/2 actions working) | ✅ Yes (GitHub API) | Repository search, README reading, issue/PR comments |
| **youtube** | Default | ✅ **PASS** (3/3 actions working) | ✅ Yes (yt-dlp) | Video metadata, description emails, full subtitles |
| **v2ex** | Default | ✅ **PASS** (4/4 actions working) | ✅ Yes (V2EX API) | Developer discussions, hiring boards, member profiles |
| **reddit** | Optional | ✅ **PASS** (via Public-Web fallback) | ✅ Yes | Community pain points, competitor feedback, discussions |
| **linkedin** | Optional | ✅ **PASS** (via Public Indexing) | ✅ Yes (Public-First) | B2B leads, dental clinic owners, job postings |
| **twitter** | Experimental | ✅ **PASS** (via Public Indexing) | ✅ Yes (Public-First) | Prospect tweets, bios, social sentiment |
| **boss** | Optional | ✅ Installed (`boss-agent-cli` 1.20) | ⚠️ Search needs session | Tech hiring & job descriptions |
| **bilibili** | Default | ⚠️ Partial (Search & Hot work) | ✅ Yes for search/hot | Video search, trending topics |

### Active Tools
- `cloakbrowser` v0.6.3 (Stealth dedicated browser engine)
- `opencli` v1.8.7 (Node.js browser automation bridge)
- `node` v26.13.0 (Private runtime)
- `ffmpeg` v0.8.1 (Audio extraction)
- `bili-cli` v0.6.2 (Bilibili CLI client)
- `boss-agent-cli` v1.20.0 (Boss Zhipin client)

---

## 2. Fast & Easy Lead Search (Zero Login Required)

By following the **Public-First** strategy, you can find leads, contact profiles, and job listings without having to log in to personal accounts or risk account restrictions.

### A. Dentist & Healthcare Leads (LinkedIn)
```bash
# 1. Search for dental practice owners & lead dentists on LinkedIn
agent-reach web search 'site:linkedin.com/in/ "dentist" "owner"' --limit 10

# 2. Search for dental clinic owners in a specific state or city
agent-reach web search 'site:linkedin.com/in/ "dentist" "owner" "Miami"' --limit 10

# 3. Search for dental clinics currently hiring dentists (B2B intent leads)
agent-reach web search 'site:linkedin.com/jobs/view/ "associate dentist" "Florida"' --limit 10

# 4. Search for orthodontists or pediatric dental specialists
agent-reach web search 'site:linkedin.com/in/ "orthodontist" "practice owner"' --limit 10
```

### B. Decision Maker & Startup Leads
```bash
# Find SaaS founders in a specific niche
agent-reach web search 'site:linkedin.com/in/ "founder" "B2B SaaS" "New York"' --limit 10

# Find engineering leaders
agent-reach web search 'site:linkedin.com/in/ "VP of Engineering" OR "CTO" "remote"' --limit 10
```

### C. Social Intent & Competitor Leads (Twitter & Reddit)
```bash
# Find prospects asking for tool alternatives on Twitter/X
agent-reach web search 'site:x.com "looking for an alternative to"' --limit 10

# Find dental practitioners discussing management software on X
agent-reach web search 'site:x.com "dentist" "practice management"' --limit 10

# Find Reddit threads where people complain about competitor tools
agent-reach web search 'site:reddit.com/r/SaaS "alternative to zapier"' --limit 10

# Direct Reddit search for dental clinic discussions
agent-reach reddit search "dental clinic software" --limit 5
```

### D. Clean Web Page & URL Reading
```bash
# Read any company's About, Team, or Pricing page as clean text
agent-reach read "https://company.com/about"
agent-reach read "https://company.com/team"
```

---

## 3. Native Channel Commands Reference

All commands output structured JSON (`ok: true`, `items: [...]`).

### 1. Web Channel
```bash
# Search web using Exa semantic engine
agent-reach web search "<query>" [--limit 10]

# Fetch clean markdown text from any webpage using Jina reader
agent-reach web read "<url>"
```

### 2. LinkedIn Channel
```bash
# Search active job openings (identifies companies with hiring budgets)
agent-reach linkedin jobs "<query>" [--location "<city/country>"] [--limit 5]

# Read full job description from a LinkedIn URL
agent-reach linkedin read "https://www.linkedin.com/jobs/view/<job-id>"
```

### 3. Twitter / X Channel
```bash
# Search tweets
agent-reach twitter search "<query>" [--limit 5]

# Read profile details, bio, follower metrics
agent-reach twitter profile "<username_without_@>"

# Read user's latest tweets
agent-reach twitter tweets "<username_without_@>" [--limit 5]

# Read tweet discussion thread and replies
agent-reach twitter thread "<tweet-url-or-id>"
```

### 4. Reddit Channel
```bash
# Search posts across Reddit
agent-reach reddit search "<query>" [--limit 5]

# Read full Reddit post and top comments
agent-reach reddit read "<reddit-post-url>"

# Get latest posts in a specific subreddit
agent-reach reddit subreddit "<subreddit_name>" [--limit 10]
```

### 5. GitHub Channel
```bash
# Search repositories
agent-reach github search "<query>" [--limit 5]

# Read repo metadata and README
agent-reach github read "<owner/repo>"

# Read issue or PR discussions with comments
agent-reach github read "https://github.com/owner/repo/issues/<id>"
```

### 6. YouTube Channel
```bash
# Search videos
agent-reach youtube search "<query>" [--limit 5]

# Get video details, title, and channel description
agent-reach youtube read "<video-id-or-url>"

# Extract full subtitle transcript
agent-reach youtube subtitle "<video-id-or-url>" [--lang "en"]
```

### 7. V2EX Channel
```bash
# Get today's trending tech discussions
agent-reach v2ex hot [--limit 10]

# Read specific node (e.g. jobs, python, create)
agent-reach v2ex node "jobs" [--limit 10]

# Read post topic and its full replies
agent-reach v2ex read "<topic-id-or-url>"

# View member profile
agent-reach v2ex user "<username>"
```

---

## 4. Complete Authentication & Login Guide

### A. Core Architecture & Security
- **Separate Environment**: Agent Reach uses its own browser profile (`~/.agent-reach/browser/profile`), completely separate from your everyday browser.
- **Privacy & Safety**: The AI never asks for or stores passwords. Login is performed by you directly on the official site.
- **Automatic Session Sharing**: Once you log in, session cookies are saved and reused headlessly for all future commands.

---

### B. How to Log In

#### Scenario 1: On Desktop / GUI (macOS, Windows, Linux with Display)
Run the login command for the desired platform:
```bash
agent-reach login linkedin
agent-reach login twitter
agent-reach login reddit
agent-reach login boss
```
1. A dedicated browser window opens to the official platform login page.
2. Sign in with your credentials (complete any 2FA or captcha).
3. Once logged in, close the window or leave it. The session is saved to `~/.agent-reach/browser/`.
4. Subsequent commands will run silently in headless background mode.

#### Scenario 2: On a Headless Linux Server / SSH / Docker Container
Because headless servers lack a physical display (`$DISPLAY`), use virtual framebuffer `xvfb-run`:
```bash
xvfb-run agent-reach login linkedin
xvfb-run agent-reach login twitter
```

#### Scenario 3: Importing from Your Existing Browser
If your main Chrome has the OpenCLI extension connected:
```bash
agent-reach login linkedin --import-existing
agent-reach login twitter --import-existing
```
This copies only the authentication cookie for that specific domain into Agent Reach without opening a browser window.

---

### C. Session & Channel Management

| Goal | Command |
|---|---|
| Check overall health & channel status | `agent-reach doctor` or `agent-reach doctor --text` |
| Test a specific channel | `agent-reach check <channel> --text` |
| View browser status & engine info | `agent-reach browser status` |
| Stop background browser processes | `agent-reach browser stop` |
| Log out of a specific platform | `agent-reach logout <channel>` |
| Remove platform and purge stored data | `agent-reach remove <channel>` |
| Update all tools and backends | `agent-reach update` |

---

## 5. Automated Python Lead Generation Script

Use this template to fetch leads and export them to structured JSON or CSV:

```python
#!/usr/bin/env python3
import json
import subprocess
import csv

def find_dentist_leads(location="New York", limit=10):
    query = f'site:linkedin.com/in/ "dentist" "owner" "{location}"'
    cmd = ["agent-reach", "web", "search", query, "--limit", str(limit)]
    
    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    
    if not data.get("ok"):
        print(f"Error: {data.get('error')}")
        return []

    leads = []
    for item in data.get("items", []):
        leads.append({
            "name_and_title": item.get("title"),
            "profile_url": item.get("url"),
            "summary": item.get("text", "").replace("\n", " ")[:200]
        })
    return leads

if __name__ == "__main__":
    leads = find_dentist_leads(location="California", limit=5)
    
    # Save to CSV
    with open("dentist_leads.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name_and_title", "profile_url", "summary"])
        writer.writeheader()
        writer.writerows(leads)
        
    print(f"\nSuccessfully saved {len(leads)} leads to dentist_leads.csv")
```

---

## 6. Automated Lead Saver & Web Explorer (Interface)

To automate saving and provide a visual interface on top of Agent Reach, two tools have been added:

### 1. Interactive Web UI Dashboard
Launch the zero-dependency Web Explorer:
```bash
python3 /Agent-Reach/web_ui.py
```
- **URL**: `http://localhost:7860`
- **Features**:
  - Live search interface with Niche, Location, and Platform selectors.
  - Automatic extraction of Phone / WhatsApp numbers and Emails into dedicated columns.
  - Automatic saving to SQLite database (`/Agent-Reach/data/leads.db`) and timestamped CSV/JSON files.
  - One-click CSV and JSON export buttons.
  - Search history sidebar with instant re-load of previous queries.

### 2. Command-Line Auto-Save Tool (`lead-search`)
Run searches from any terminal session with auto-saving enabled:
```bash
# Search for dentists in Mumbai and auto-save
lead-search "dentist" --location "Mumbai" --limit 10

# Search for cake sellers in Kolkata
lead-search "cake sellers" --location "Kolkata"

# View history of all previous searches
lead-search --history

# View leads from past search ID #1
lead-search --view 1
```

All searches are automatically saved to:
- CSV: `/Agent-Reach/saved_searches/<query>_<timestamp>.csv`
- JSON: `/Agent-Reach/saved_searches/<query>_<timestamp>.json`
- Latest: `/Agent-Reach/saved_searches/latest_leads.csv`
