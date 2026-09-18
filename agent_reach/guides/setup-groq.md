# Groq Whisper Setup Guide

## What it provides

When a YouTube/Bilibili video has no usable subtitles, Agent Reach can use Groq's Whisper API to transcribe the audio. Groq offers a free tier subject to upstream limits.

## Steps the agent can perform

1. Check whether a key is configured:

```bash
agent-reach doctor | grep -i "groq\|whisper"
```

2. Prefer the CLI configuration command:

```bash
agent-reach configure groq-key
```

If code-level configuration is required:

```python
from agent_reach.config import Config

config = Config()
config.set("groq_api_key", "USER_PROVIDED_KEY")
```

3. Optional API check:

```bash
curl -s https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer USER_PROVIDED_KEY" \
  -o /dev/null -w "%{http_code}"
```

HTTP 200 indicates the credential is accepted.

## User action required

Ask the user to create and provide their own Groq API key:

1. Open https://console.groq.com
2. Sign in or register
3. Open **API Keys**
4. Choose **Create API Key**
5. Copy the new key and provide it through the secure configuration flow

Do not log or echo the key.

## After receiving the key

1. Store it with `agent-reach configure groq-key` or `Config.set(...)`.
2. Optionally test the API.
3. Confirm that audio transcription is available for media without subtitles.
