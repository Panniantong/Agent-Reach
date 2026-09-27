# Groq Whisper Configuration Guide

## Function description
Use Groq's Whisper API for speech-to-text when YouTube/Bilibili videos don't have subtitles. Groq offers free credits.

## Steps that Agent can automatically complete

1. Check whether it is configured:
```bash
agent-reach doctor | grep -i "groq\|whisper"
```

2. If the user provides a key, write the configuration:
```python
from agent_reach.config import Config
c = Config()
c.set("groq_api_key", "User providedKEY")
```

3. Test (optional):
```bash
curl -s https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer User providedKEY" \
  -o /dev/null -w "%{http_code}"
```
Returns 200 = Available

## Steps that need to be done manually by the user

Please tell users:

> Video speech-to-text requires a Groq API Key (free).
>
> Steps:
> 1. Open https://console.groq.com
> 2. Register with Google account or email
> 3. Click "API Keys" on the left
> 4. Click "Create API Key"
> 5. Copy the generated Key and send it to me
>
> Groq provides free quota, which is sufficient for daily use.

## Agent’s operation after receiving the key

1. Write configuration: `config.set("groq_api_key", key)`
2. Test API availability
3. Feedback: "✅ Speech-to-text is turned on! Now if you encounter videos without subtitles, I can also help you extract the content."
