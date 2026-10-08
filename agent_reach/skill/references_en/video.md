# Video / podcasts

Subtitles and transcripts for YouTube, Bilibili and Xiaoyuzhou podcasts.

## YouTube (yt-dlp)

### Get video metadata

```bash
yt-dlp --dump-json "URL"
```

### Download subtitles

```bash
# Download subtitles only (no video)
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"

# Then read the .vtt file
cat /tmp/VIDEO_ID.*.vtt
```

### Get comments

```bash
# Extract comments (best-effort, completeness not guaranteed)
yt-dlp --write-comments --skip-download --write-info-json \
  --extractor-args "youtube:max_comments=20" \
  -o "/tmp/%(id)s" "URL"
# Comments land in the comments field of the .info.json
```

### Search videos

```bash
yt-dlp --dump-json "ytsearch5:query"
```

> **Subtitle note**: manually uploaded subtitles extract reliably. Auto-generated subtitles can contain repeated lines and need post-processing.
> **Comment note**: `--write-comments` is based on page scraping, not the YouTube Data API, so some comments may be missing.

### Retry chain when subtitles fail (run in order, stop as soon as you have real content)

`doctor` only confirms that yt-dlp itself and the JS runtime can run. It does not request a
specific video, so `active_backend: yt-dlp` does NOT mean the target video's subtitles have been
verified live.

1. Start with the `yt-dlp --write-sub --write-auto-sub` command above.
2. If you hit a bot check, an empty subtitle response, or no subtitle file is produced, and OpenCLI is connected:
   `opencli youtube transcript "URL" -f yaml`.
3. If OpenCLI returns `Caption URL returned empty response`, retry up to 3 times. These subtitle URLs carry an
   expiry and fail intermittently, so an empty response is not proof the video has no subtitles.
4. Still failing, or the video genuinely has no subtitles: `agent-reach transcribe "URL"` downloads the audio and transcribes it.

The success criterion is actually holding non-empty subtitle or transcript content, not the command's exit code or `doctor`'s version probe.

### No-subtitle fallback: Whisper audio transcription

```bash
# Fallback when a video has no subtitles: download the audio and transcribe with Whisper (a free Groq key is enough)
agent-reach transcribe "https://www.youtube.com/watch?v=VIDEO_ID"
agent-reach transcribe ./local_audio.mp3 -o /tmp/transcript.txt
```

> `agent-reach transcribe` accepts only a public http(s) URL or a local audio file. When searching with `ytsearch5:`, pick a specific video URL out of the yt-dlp results first, then transcribe.
> Configure a key first: `agent-reach configure groq-key` (hidden input; free, console.groq.com)
> or `agent-reach configure openai-key`. The default auto mode uses only the first configured provider
> (Groq if present, otherwise OpenAI) and stops on failure. It will not silently send your audio to the other one.
> `--allow-provider-fallback` explicitly authorises cross-provider fallback. The same audio may then be processed by both Groq and
> OpenAI and may incur OpenAI charges, so use it only once you have confirmed the content can be shared with both.

## Bilibili (bili-cli primary, OpenCLI for subtitles)

> ⚠️ **Do not use yt-dlp for Bilibili**: Bilibili's anti-abuse now blocks yt-dlp with 412 across the board (tested on the latest version, direct, proxied and with cookies, all fail). Use yt-dlp for YouTube only.

### Video details / search / trending / rankings (bili-cli, read-only, no login needed)

```bash
# Video details (title, uploader, duration, play and engagement stats, subtitle availability)
bili video BVxxx

# Search videos
bili search "query" --type video -n 5

# Trending videos / leaderboard
bili hot -n 10
bili rank -n 10

# Download audio and split into ASR-ready WAV (pair with agent-reach transcribe when there are no subtitles)
bili audio BVxxx
```

### Subtitles (OpenCLI, needs desktop Chrome)

```bash
# Subtitles line by line with timestamps
opencli bilibili subtitle BVxxx

# OpenCLI can also search and read video metadata (alternative)
opencli bilibili search "query" -f yaml
opencli bilibili video BVxxx -f yaml
```

### Zero-config fallback: direct search API

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
curl -s -c /tmp/bili_ck.txt -o /dev/null -A "$UA" "https://www.bilibili.com/"
curl -s -b /tmp/bili_ck.txt -A "$UA" -e "https://www.bilibili.com/" \
  "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=QUERY&page=1"
```

> **Installing bili-cli**: `pipx install bilibili-cli` (upstream stopped updating in March 2026 but tests healthy; read-only use needs no login, and `bili login` with a QR scan unlocks personal features such as your feed and favourites).

## Xiaoyuzhou Podcast

### Transcribe a single episode (optional --polish improves punctuation)

```bash
# Writes a Markdown file to /tmp/. --polish has Llama 3.3 70B add Chinese punctuation and sensible paragraph breaks
~/.agent-reach/tools/xiaoyuzhou/transcribe.sh --polish "https://www.xiaoyuzhoufm.com/episode/EPISODE_ID"
```

> The transcription prompt already asks Whisper for Chinese punctuation. If punctuation still reads poorly, add `--polish` to use the free Llama 3.3 70B on Groq for punctuation and paragraphing (roughly 7 extra seconds on a 9-minute podcast). Each transcription then costs one extra LLM call, so use it as needed.

### Prerequisites

1. **ffmpeg**: `brew install ffmpeg`
2. **Groq API key** (free): https://console.groq.com/keys
3. **Configure the key**: `agent-reach configure groq-key` (hidden input)
4. **First run**: `agent-reach install --env=auto --system --channels=xiaoyuzhou` (needs explicit user authorisation)

### Check status

```bash
agent-reach doctor
```

> Output Markdown files are saved to `/tmp/` by default.

## Choosing a tool

| Scenario | Recommended tool |
|-----|---------|
| YouTube subtitles | yt-dlp; on failure OpenCLI (up to 3 tries), then agent-reach transcribe |
| Bilibili video details / search | bili-cli |
| Bilibili subtitles | opencli bilibili subtitle |
| Podcast transcription | Xiaoyuzhou transcribe.sh |
| Audio or video without subtitles | agent-reach transcribe (for Bilibili, run `bili audio` first) |
