# Career & Hiring

LinkedIn.

## LinkedIn

```bash
# Get a personal profile
mcporter call 'linkedin-scraper.get_person_profile(linkedin_url: "https://linkedin.com/in/username")'

# Search for people
mcporter call 'linkedin-scraper.search_people(keyword: "AI engineer", limit: 10)'

# Get a company profile
mcporter call 'linkedin-scraper.get_company_profile(linkedin_url: "https://linkedin.com/company/xxx")'

# Search for jobs
mcporter call 'linkedin-scraper.search_jobs(keyword: "software engineer", limit: 10)'
```

> **Login required**: The LinkedIn scraper needs a valid logged-in session.

### Fallback Option

If MCP is unavailable, you can use Jina Reader:

```bash
curl -s "https://r.jina.ai/https://linkedin.com/in/username"
```
