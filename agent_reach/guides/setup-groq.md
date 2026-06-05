# Groq Whisper Setup Guide

## Overview
When a YouTube/Bilibili video has no subtitles, use Groq's Whisper API for speech-to-text. Groq offers a free tier.

## Steps the Agent Can Complete Automatically

1. Check whether it is already configured:
```bash
agent-reach doctor | grep -i "groq\|whisper"
```

2. If the user provides a key, write it to the config:
```python
from agent_reach.config import Config
c = Config()
c.set("groq_api_key", "KEY provided by the user")
```

3. Test (optional):
```bash
curl -s https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer KEY provided by the user" \
  -o /dev/null -w "%{http_code}"
```
A return of 200 = working

## Steps the User Must Do Manually

Tell the user:

> Video speech-to-text requires a Groq API key (free).
>
> Steps:
> 1. Open https://console.groq.com
> 2. Sign up with a Google account or email
> 3. Click "API Keys" on the left
> 4. Click "Create API Key"
> 5. Copy the generated key and send it to me
>
> Groq offers a free tier that is more than enough for everyday use.

## What the Agent Does After Receiving the Key

1. Write to the config: `config.set("groq_api_key", key)`
2. Test API availability
3. Report back: "✅ Speech-to-text is now enabled! Now, even for videos without subtitles, I can extract the content for you."
