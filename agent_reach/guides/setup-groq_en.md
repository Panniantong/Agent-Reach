# Groq Whisper Setup Guide

## Overview
When YouTube/Bilibili videos don't have subtitles, use Groq's Whisper API for speech-to-text. Groq offers free credits.

## Agent Can Auto-Configure

1. Check if already configured:
   ```bash
   agent-reach doctor | grep groq
   ```

2. If user provides a key, save it:
   ```python
   config.set("groq_api_key", "USER_KEY")
   ```

3. Test (optional):
   ```bash
   curl -s "https://api.groq.com/openai/v1/models" \
     -H "Authorization: Bearer USER_KEY"
   ```
   HTTP 200 = ready

## User Action Required

Tell the user:
> Video speech-to-text needs a free Groq API Key.
>
> Steps:
> 1. Open https://console.groq.com
> 2. Sign up with Google or email
> 3. Click "API Keys" in the sidebar
> 4. Click "Create API Key"
> 5. Copy the key and share it with me
>
> The free tier is generous enough for daily use.

## After Receiving the Key

1. Save it: `agent-reach configure groq-key gsk_xxxxx`
2. Confirm: "✅ Speech-to-text is enabled!"