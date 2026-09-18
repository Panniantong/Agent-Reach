# Video and Podcasts

YouTube, Bilibili, and Xiaoyuzhou Podcast subtitles/transcription.

## YouTube (yt-dlp)

### Video metadata

```bash
yt-dlp --dump-json "URL"
```

### Download subtitles

```bash
# Download subtitles without downloading the video
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"

# Read the generated .vtt file
cat /tmp/VIDEO_ID.*.vtt
```

### Comments

```bash
# Best effort; may be incomplete
yt-dlp --write-comments --skip-download --write-info-json \
  --extractor-args "youtube:max_comments=20" \
  -o "/tmp/%(id)s" "URL"
# Comments are stored in the .info.json comments field
```

### Search

```bash
yt-dlp --dump-json "ytsearch5:query"
```

> Manually uploaded subtitles are generally reliable. Auto-generated captions may contain repeated lines and can require post-processing.
>
> `--write-comments` scrapes the page rather than using the YouTube Data API, so some comments may be missing.

### Subtitle failure retry chain

Doctor verifies that yt-dlp and a JavaScript runtime can execute; it does not request the target video. `active_backend: yt-dlp` therefore does not prove that the current video has working captions.

1. Try the normal `yt-dlp --write-sub --write-auto-sub` command.
2. If a bot check appears, the caption response is empty, or no subtitle file is created and OpenCLI is connected, try:
   ```bash
   opencli youtube transcript "URL" -f yaml
   ```
3. If OpenCLI returns `Caption URL returned empty response`, retry up to three times; expiring caption URLs can fail intermittently.
4. If it still fails or the video has no subtitles, use:
   ```bash
   agent-reach transcribe "URL"
   ```

Success means non-empty subtitle/transcript content, not merely exit code 0 or a healthy doctor probe.

### No-subtitle fallback: Whisper transcription

```bash
agent-reach transcribe "https://www.youtube.com/watch?v=VIDEO_ID"
agent-reach transcribe ./local_audio.mp3 -o /tmp/transcript.txt
```

`agent-reach transcribe` accepts public http(s) URLs or local audio files. If you start with `ytsearch5:`, select a concrete video URL from the search results before transcribing.

Configure a provider first:

```bash
agent-reach configure groq-key
# or
agent-reach configure openai-key
```

Auto mode uses only the first configured provider (Groq first, otherwise OpenAI) and stops on failure. It does not automatically send the same audio to another provider. `--allow-provider-fallback` explicitly authorizes cross-provider fallback and may incur OpenAI charges.

## Bilibili (bili-cli primary, OpenCLI for subtitles)

> **Do not use yt-dlp for Bilibili.** Bilibili's anti-bot controls currently return HTTP 412 for yt-dlp in tested direct/proxy/cookie setups. Keep yt-dlp for YouTube.

### Details/search/hot/rankings with bili-cli

```bash
# Video details
bili video BVxxx

# Search
bili search "query" --type video -n 5

# Hot / rankings
bili hot -n 10
bili rank -n 10

# Download audio and prepare ASR-ready WAV chunks
bili audio BVxxx
```

### Subtitles through OpenCLI

```bash
opencli bilibili subtitle BVxxx

# OpenCLI can also search/read metadata
opencli bilibili search "query" -f yaml
opencli bilibili video BVxxx -f yaml
```

### Zero-config search API fallback

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
curl -s -c /tmp/bili_ck.txt -o /dev/null -A "$UA" "https://www.bilibili.com/"
curl -s -b /tmp/bili_ck.txt -A "$UA" -e "https://www.bilibili.com/" \
  "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=QUERY&page=1"
```

Install bili-cli with `pipx install bilibili-cli`. The upstream project has been inactive since 2026-03 but remains useful for tested read-only operations.

## Xiaoyuzhou Podcast

### Transcribe an episode

```bash
~/.agent-reach/tools/xiaoyuzhou/transcribe.sh --polish "https://www.xiaoyuzhoufm.com/episode/EPISODE_ID"
```

`--polish` optionally sends the transcript through Groq-hosted Llama to improve punctuation and paragraphing. Use it only when needed because it adds another model call.

### Requirements

1. ffmpeg: `brew install ffmpeg` (or the equivalent package for the OS)
2. Free Groq API key: https://console.groq.com/keys
3. Configure the key: `agent-reach configure groq-key`
4. First install: `agent-reach install --env=auto --system --channels=xiaoyuzhou` after explicit user approval

### Check status

```bash
agent-reach doctor
```

The generated Markdown transcript is saved under `/tmp/` by default.

## Selection guide

| Scenario | Recommended tool |
|---|---|
| YouTube subtitles | yt-dlp; then OpenCLI (up to 3 attempts); then `agent-reach transcribe` |
| Bilibili details/search | bili-cli |
| Bilibili subtitles | `opencli bilibili subtitle` |
| Podcast transcription | Xiaoyuzhou `transcribe.sh` |
| Audio/video without subtitles | `agent-reach transcribe` (for Bilibili, get audio with `bili audio` first) |
