# Career & Jobs

LinkedIn.

## LinkedIn

```bash
# Get person profile
mcporter call 'linkedin-scraper.get_person_profile(linkedin_url: "https://linkedin.com/in/username")'

# Search people
mcporter call 'linkedin-scraper.search_people(keyword: "AI engineer", limit: 10)'

# Get company profile
mcporter call 'linkedin-scraper.get_company_profile(linkedin_url: "https://linkedin.com/company/xxx")'

# Search jobs
mcporter call 'linkedin-scraper.search_jobs(keyword: "software engineer", limit: 10)'
```

> **Login required**: LinkedIn scraper needs a valid login session.

### Fallback

If MCP is unavailable, use Jina Reader:

```bash
curl -s "https://r.jina.ai/https://linkedin.com/in/username"
```
