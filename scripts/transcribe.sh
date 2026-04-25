#!/usr/bin/env bash
# transcribe_audio.sh — Transcribe YouTube/audio via Whisper API.
#
# Usage:
#   transcribe_audio.sh <youtube_url_or_local_file> [output_dir] [--provider=groq|openai|auto]
#
# Providers (default order: groq → openai):
#   groq    — free tier, fast (Groq LPU), whisper-large-v3           [DEFAULT]
#   openai  — paid (~$0.006/min), reliable fallback, whisper-1
#   auto    — try groq first, fall back to openai on failure         [DEFAULT]
#
# Keys are read from ~/.agent-reach/config.yaml (NOT shell env by default):
#   groq_api_key:   gsk_...
#   openai_api_key: sk-...
#
# Configure with:
#   agent-reach configure groq-key   gsk_...
#   agent-reach configure openai-key sk-...
#
# Pipeline:
#   1. Download audio with yt-dlp (skipped if input is an existing local file).
#   2. Re-encode to mono 16kHz 32kbps m4a (keeps under 25MB API limit).
#   3. If still >24MB, split into 10-minute chunks via ffmpeg.
#   4. Try providers in order; on HTTP error or curl failure, fall back.
#   5. Concatenate results into transcript.txt and print to stdout.

set -euo pipefail

log()  { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die()  { log "ERROR: $*"; exit 1; }

# --- Args ---------------------------------------------------------------
INPUT=""
OUTDIR=""
PROVIDER="auto"
for arg in "$@"; do
  case "$arg" in
    --provider=*) PROVIDER="${arg#--provider=}" ;;
    -h|--help)
      sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      if [[ -z "$INPUT" ]]; then INPUT="$arg"
      elif [[ -z "$OUTDIR" ]]; then OUTDIR="$arg"
      fi
      ;;
  esac
done
[[ -n "$INPUT" ]] || die "usage: $0 <url_or_file> [output_dir] [--provider=groq|openai|auto]"
OUTDIR="${OUTDIR:-/tmp/transcribe-$$}"
mkdir -p "$OUTDIR"
log "Output dir: $OUTDIR"
log "Provider:   $PROVIDER"

# --- Load keys from config.yaml (falls back to env) --------------------
# Precedence: shell env > config.yaml. We parse the (flat) yaml with awk so we
# don't depend on PyYAML being available in the system python.
CONFIG_FILE="$HOME/.agent-reach/config.yaml"
read_yaml_key() {
  local key="$1"
  [[ -f "$CONFIG_FILE" ]] || return 0
  # Match: "<key>: <value>" or "<key>:<value>" at the start of a line; trim
  # surrounding whitespace and optional quotes.
  awk -v k="$key" '
    $0 ~ "^"k"[[:space:]]*:" {
      sub("^"k"[[:space:]]*:[[:space:]]*", "")
      gsub(/^["\x27]|["\x27]$/, "")
      print
      exit
    }
  ' "$CONFIG_FILE"
}
GROQ_API_KEY="${GROQ_API_KEY:-$(read_yaml_key groq_api_key)}"
OPENAI_API_KEY="${OPENAI_API_KEY:-$(read_yaml_key openai_api_key)}"

# --- Tooling ------------------------------------------------------------
command -v yt-dlp >/dev/null || die "yt-dlp not found in PATH"
command -v ffmpeg >/dev/null || die "ffmpeg not found in PATH (brew install ffmpeg / apt install ffmpeg)"
command -v curl   >/dev/null || die "curl not found"

# --- 1. Acquire source audio ------------------------------------------
RAW_BASE="$OUTDIR/source"
if [[ -f "$INPUT" ]]; then
  log "Using local file: $INPUT"
  cp "$INPUT" "$RAW_BASE.orig"
  SRC="$RAW_BASE.orig"
else
  log "Downloading audio: $INPUT"
  yt-dlp -x --audio-format m4a --audio-quality 0 \
    -o "$RAW_BASE.%(ext)s" "$INPUT" >&2
  SRC="$(ls "$RAW_BASE".* 2>/dev/null | head -1)"
  [[ -n "$SRC" ]] || die "yt-dlp produced no output file"
fi

# --- 2. Compress for API -----------------------------------------------
COMPRESSED="$OUTDIR/compressed.m4a"
log "Compressing (mono/16kHz/32kbps)..."
ffmpeg -loglevel error -y -i "$SRC" -vn -ac 1 -ar 16000 -b:a 32k "$COMPRESSED"
SIZE=$(stat -f%z "$COMPRESSED" 2>/dev/null || stat -c%s "$COMPRESSED")
LIMIT=$((24 * 1024 * 1024))
log "Compressed size: $((SIZE / 1024))KB"

# --- 3. Chunk if needed -------------------------------------------------
CHUNKS=()
if (( SIZE <= LIMIT )); then
  CHUNKS=("$COMPRESSED")
else
  log "Too large — splitting into 10-minute chunks..."
  ffmpeg -loglevel error -y -i "$COMPRESSED" \
    -f segment -segment_time 600 -c copy "$OUTDIR/chunk_%03d.m4a"
  while IFS= read -r c; do CHUNKS+=("$c"); done < <(ls "$OUTDIR"/chunk_*.m4a)
fi

# --- 4. Transcribe with fallback ---------------------------------------
# transcribe_via <provider> <file> <out_file> → 0 on success
transcribe_via() {
  local provider="$1" file="$2" out="$3"
  local endpoint model key http tmp body
  case "$provider" in
    groq)
      endpoint="https://api.groq.com/openai/v1/audio/transcriptions"
      model="whisper-large-v3"
      key="${GROQ_API_KEY:-}"
      ;;
    openai)
      endpoint="https://api.openai.com/v1/audio/transcriptions"
      model="whisper-1"
      key="${OPENAI_API_KEY:-}"
      ;;
    *) return 2 ;;
  esac
  if [[ -z "$key" ]]; then
    log "  $provider: key not configured (agent-reach configure ${provider}-key ...)"
    return 3
  fi

  tmp="$(mktemp)"
  http=$(curl -sS -o "$tmp" -w '%{http_code}' "$endpoint" \
    -H "Authorization: Bearer $key" \
    -F "file=@$file" \
    -F "model=$model" \
    -F "response_format=text" 2>/dev/null || echo "000")
  if [[ "$http" =~ ^2 ]]; then
    cat "$tmp" >> "$out"
    printf '\n' >> "$out"
    rm -f "$tmp"
    return 0
  fi
  body="$(head -c 300 "$tmp" 2>/dev/null || true)"
  rm -f "$tmp"
  log "  $provider failed (HTTP $http): $body"
  return 1
}

# Provider order.
ORDER=()
case "$PROVIDER" in
  groq)   ORDER=(groq) ;;
  openai) ORDER=(openai) ;;
  auto)   ORDER=(groq openai) ;;
  *)      die "unknown --provider=$PROVIDER (use groq|openai|auto)" ;;
esac

TRANSCRIPT="$OUTDIR/transcript.txt"
: > "$TRANSCRIPT"
USED=""
for ((i=0; i<${#CHUNKS[@]}; i++)); do
  chunk="${CHUNKS[$i]}"
  log "Transcribing chunk $((i+1))/${#CHUNKS[@]}: $(basename "$chunk")"
  ok=0
  for p in "${ORDER[@]}"; do
    if transcribe_via "$p" "$chunk" "$TRANSCRIPT"; then
      if [[ -z "$USED" ]]; then USED="$p"
      elif [[ "$USED" != *"$p"* ]]; then USED="$USED→$p"
      fi
      log "  ✅ via $p"
      ok=1
      break
    fi
  done
  (( ok )) || die "all providers failed for chunk $((i+1))"
done

log "Done. Used: $USED"
log "Transcript: $TRANSCRIPT"
cat "$TRANSCRIPT"
