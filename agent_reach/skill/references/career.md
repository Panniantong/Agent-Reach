# 职场招聘 / Career

LinkedIn — via the `linkedin-scraper-mcp` server (browser automation), invoked
through mcporter. It is registered as the mcporter server `linkedin`, so every
call is `mcporter call 'linkedin.<tool>(...)'`.

## Setup

```bash
# One-time interactive login (opens a browser; session saved to ~/.linkedin-mcp/profile)
linkedin-scraper-mcp --login --no-headless
linkedin-scraper-mcp --status   # verify the session is valid

# Register with mcporter (stdio transport; no long-running server needed)
mcporter config add linkedin --command linkedin-scraper-mcp --arg --transport --arg stdio
```

> Requires a valid login. Without it, only the Jina fallback (public pages) works.
> Run `mcporter list linkedin` to see the live tool signatures.

Conventions: people are identified by **username** (`"williamhgates"`, not a URL),
companies by their **URL slug** (`"anthropicresearch"`, not the display name), jobs
by **`job_id`**. Search params are `keywords` (plural).

## People

```bash
# A person's profile. sections (comma-separated, optional): experience, education,
# interests, honors, languages, certifications, skills, projects, contact_info, posts
mcporter call 'linkedin.get_person_profile(linkedin_username: "williamhgates", sections: "experience,education")'

# The authenticated user's own profile
mcporter call 'linkedin.get_my_profile(sections: "experience,skills")'

# Search people. network: ["F"]=1st, ["S"]=2nd, ["O"]=3rd+. current_company takes a
# numeric company URN id (from get_company_profile), not a plain company name.
mcporter call 'linkedin.search_people(keywords: "AI engineer", location: "Remote", network: ["F"])'

# Profiles from the "people you may know" sidebar of a profile page
mcporter call 'linkedin.get_sidebar_profiles(linkedin_username: "williamhgates")'
```

## Companies

```bash
# Company "about" page. sections (optional): posts, jobs
mcporter call 'linkedin.get_company_profile(company_name: "anthropic", sections: "posts")'

# Recent posts from a company feed
mcporter call 'linkedin.get_company_posts(company_name: "docker")'

# Search companies
mcporter call 'linkedin.search_companies(keywords: "fintech")'

# Employees + demographics (location / education / function breakdown).
# company_name MUST be the exact URL slug, e.g. "anthropicresearch" not "anthropic".
mcporter call 'linkedin.get_company_employees(company_name: "anthropicresearch", keywords: "engineer")'
```

## Jobs

```bash
# Search jobs -> returns job_ids. Optional filters:
#   max_pages 1-10 (default 3) | date_posted: past_hour|past_24_hours|past_week|past_month
#   job_type: full_time,part_time,contract,temporary,volunteer,internship,other
#   experience_level: internship,entry,associate,mid_senior,director,executive
#   work_type: on_site,remote,hybrid | easy_apply: true|false | sort_by: date|relevance
mcporter call 'linkedin.search_jobs(keywords: "software engineer", location: "Remote", max_pages: 1, work_type: "remote")'

# Full detail for one posting (job_id from search_jobs)
mcporter call 'linkedin.get_job_details(job_id: "4252026496")'
```

## Feed & messaging (read)

```bash
mcporter call 'linkedin.get_feed(num_posts: 10)'               # authenticated home feed
mcporter call 'linkedin.get_inbox(limit: 20)'                  # messaging inbox
mcporter call 'linkedin.get_conversation(linkedin_username: "williamhgates")'
mcporter call 'linkedin.search_conversations(keywords: "interview", limit: 10)'
```

> The MCP also exposes write tools (`connect_with_person`, `send_message`) plus
> `close_session`. Writes are out of scope for this read/search skill — only use
> them on explicit user instruction.

## Fallback (no login, public pages only)

```bash
curl -s "https://r.jina.ai/https://linkedin.com/in/williamhgates"
```

---
Note: the pip package now prints a rename notice — it is `mcp-server-linkedin`
(`uvx mcp-server-linkedin@latest`); the `linkedin-scraper-mcp` entrypoint still works.
