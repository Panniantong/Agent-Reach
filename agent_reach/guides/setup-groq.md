# Groq Whisper Setup Guide

## Features

When YouTube/Bilibili videos have no subtitles, use Groq's Whisper API for speech-to-text. Groq provides free quota.

## Steps Agent Can Complete Automatically

1. Check if configured:
```bash
agent-reach doctor | grep -i "groq\|whisper"
```

2. If user provides key, write to config:
```python
from agent_reach.config import Config
c = Config()
c.set("groq_api_key", "user_provided_KEY")
```

3. Test (optional):
```bash
curl -s https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer user_provided_KEY" \
  -o /dev/null -w "%{http_code}"
```
Returns 200 = available

## Manual User Steps

Tell the user:

> Video speech-to-text requires a Groq API Key (free).
>
> Steps:
> 1. Open https://console.groq.com
> 2. Register with Google account or email
> 3. Click "API Keys" on the left
> 4. Click "Create API Key"
> 5. Copy the generated Key and send it to me
>
> Groq provides free quota sufficient for daily use.

## Agent Operations After Receiving Key

1. Write to config: `config.set("groq_api_key", key)`
2. Test API availability
3. Feedback: "✅ Speech-to-text enabled! I can now extract content from videos without subtitles."
