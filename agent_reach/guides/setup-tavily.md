# Tavily Search Setup

Tavily is an API-based web search provider designed for AI agents. It offers 1,000 free API credits per month.

## 1. Get an API Key

1. Visit [https://app.tavily.com](https://app.tavily.com)
2. Sign up for a free account (no credit card required)
3. Copy your API key (starts with `tvly-`)

## 2. Configure Agent Reach

```bash
agent-reach configure tavily_api_key tvly-YOUR_API_KEY
```

Or set the environment variable directly:

```bash
export TAVILY_API_KEY="tvly-YOUR_API_KEY"
```

## 3. Verify

```bash
agent-reach doctor
```

You should see `tavily_search` show as **ok**.

## Notes

- Tavily is a Tier-2 channel (requires API key)
- Exa Search remains available as the free/zero-config alternative
- Install the Python SDK if not already present: `pip install tavily-python`
