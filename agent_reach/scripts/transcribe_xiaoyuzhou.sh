#!/bin/bash
# Xiaoyuzhou podcast transcription script
# Usage: bash transcribe.sh <Xiaoyuzhou link> [output file path]
# Environment variable: GROQ_API_KEY (required)

set -e

URL="${1:?Usage: bash transcribe.sh <Xiaoyuzhou link> [output file path]}"
OUTPUT="${2:-/tmp/podcast_transcript.txt}"
TMPDIR="/tmp/xiaoyuzhou_$$"

# Try env var first, then agent-reach config.yaml
if [ -z "$GROQ_API_KEY" ]; then
    CONFIG_FILE="$HOME/.agent-reach/config.yaml"
    if [ -f "$CONFIG_FILE" ]; then
        GROQ_API_KEY=$(python3 -c "import yaml; print((yaml.safe_load(open('$CONFIG_FILE')) or {}).get('groq_api_key',''))" 2>/dev/null || true)
    fi
fi
GROQ_API_KEY="${GROQ_API_KEY:?Please set the GROQ_API_KEY environment variable or run agent-reach configure groq-key}"

# Groq API limit: 25MB per file
MAX_CHUNK_SIZE_MB=20
AUDIO_BITRATE="64k"

cleanup() {
    rm -rf "$TMPDIR"
}
trap cleanup EXIT

mkdir -p "$TMPDIR"

echo "📻 Xiaoyuzhou podcast transcription"
echo "===================="

# Step 1: Extract audio URL and title
echo "🔍 Parsing page..."
PAGE=$(curl -s "$URL")
AUDIO_URL=$(echo "$PAGE" | grep -oP 'https://media\.xyzcdn\.net/[^"]*\.(m4a|mp3)' | head -1)
TITLE=$(echo "$PAGE" | grep -oP '"title":"[^"]*"' | head -1 | sed 's/"title":"//;s/"//')

if [ -z "$AUDIO_URL" ]; then
    echo "❌ Could not extract audio link from page"
    exit 1
fi

echo "📝 Title: $TITLE"
echo "🔗 Audio: $AUDIO_URL"

# Step 2: Download audio
echo "⬇️  Downloading audio..."
EXT="${AUDIO_URL##*.}"
curl -sL -o "$TMPDIR/original.$EXT" "$AUDIO_URL"
FILE_SIZE=$(ls -lh "$TMPDIR/original.$EXT" | awk '{print $5}')
echo "📦 File size: $FILE_SIZE"

# Step 3: Get duration
DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$TMPDIR/original.$EXT" 2>/dev/null | cut -d. -f1)
DURATION_MIN=$((DURATION / 60))
DURATION_SEC=$((DURATION % 60))
echo "⏱️  Duration: ${DURATION_MIN}m${DURATION_SEC}s"

# Step 4: Convert to low-bitrate mono MP3
echo "🔄 Transcoding..."
ffmpeg -y -i "$TMPDIR/original.$EXT" -b:a "$AUDIO_BITRATE" -ac 1 "$TMPDIR/mono.mp3" 2>/dev/null
MONO_SIZE=$(stat -c%s "$TMPDIR/mono.mp3" 2>/dev/null || stat -f%z "$TMPDIR/mono.mp3")
echo "📦 After transcoding: $(echo "$MONO_SIZE / 1024 / 1024" | bc)MB"

# Step 5: Split by size
MAX_BYTES=$((MAX_CHUNK_SIZE_MB * 1024 * 1024))

if [ "$MONO_SIZE" -le "$MAX_BYTES" ]; then
    # No splitting needed
    cp "$TMPDIR/mono.mp3" "$TMPDIR/chunk_0.mp3"
    NUM_CHUNKS=1
    echo "📎 No splitting needed"
else
    # Calculate how many chunks are needed
    NUM_CHUNKS=$(( (MONO_SIZE / MAX_BYTES) + 1 ))
    CHUNK_DURATION=$(( DURATION / NUM_CHUNKS + 10 ))  # Add 10-second buffer
    echo "✂️  Splitting into $NUM_CHUNKS segments (approx $((CHUNK_DURATION / 60)) minutes each)..."

    for i in $(seq 0 $((NUM_CHUNKS - 1))); do
        START=$((i * CHUNK_DURATION))
        ffmpeg -y -i "$TMPDIR/mono.mp3" -ss "$START" -t "$CHUNK_DURATION" -c copy "$TMPDIR/chunk_${i}.mp3" 2>/dev/null
        CHUNK_SIZE=$(ls -lh "$TMPDIR/chunk_${i}.mp3" | awk '{print $5}')
        echo "   Segment $((i+1))/$NUM_CHUNKS: $CHUNK_SIZE"
    done
fi

# Step 6: Call the Groq Whisper API for transcription
echo "🎙️  Transcribing (Groq Whisper large-v3)..."

for i in $(seq 0 $((NUM_CHUNKS - 1))); do
    echo -n "   Segment $((i+1))/$NUM_CHUNKS... "
    
    RESPONSE=$(curl -s -w "\n%{http_code}" \
        https://api.groq.com/openai/v1/audio/transcriptions \
        -H "Authorization: Bearer $GROQ_API_KEY" \
        -F file="@$TMPDIR/chunk_${i}.mp3" \
        -F model="whisper-large-v3" \
        -F language="zh" \
        -F response_format="text")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" != "200" ]; then
        echo "❌ API error (HTTP $HTTP_CODE)"
        echo "$BODY"

        # If rate-limited, wait and retry
        if [ "$HTTP_CODE" = "429" ]; then
            # Extract wait time from the error message, default 120 seconds
            WAIT_SEC=$(echo "$BODY" | grep -oP 'in \K[0-9]+m' | sed 's/m//' | head -1)
            WAIT_SEC=${WAIT_SEC:-2}
            WAIT_SEC=$((WAIT_SEC * 60 + 30))
            echo "   ⏳ Rate limited, waiting ${WAIT_SEC} seconds before retry..."
            sleep "$WAIT_SEC"
            RESPONSE=$(curl -s -w "\n%{http_code}" \
                https://api.groq.com/openai/v1/audio/transcriptions \
                -H "Authorization: Bearer $GROQ_API_KEY" \
                -F file="@$TMPDIR/chunk_${i}.mp3" \
                -F model="whisper-large-v3" \
                -F language="zh" \
                -F response_format="text")
            HTTP_CODE=$(echo "$RESPONSE" | tail -1)
            BODY=$(echo "$RESPONSE" | sed '$d')
            
            if [ "$HTTP_CODE" != "200" ]; then
                echo "   ❌ Retry failed"
                exit 1
            fi
        else
            exit 1
        fi
    fi
    
    echo "$BODY" > "$TMPDIR/transcript_${i}.txt"
    CHARS=$(wc -m < "$TMPDIR/transcript_${i}.txt")
    echo "✅ ($CHARS chars)"
done

# Step 7: Merge output
echo "📄 Merging transcript..."

{
    echo "# $TITLE"
    echo ""
    echo "Source: $URL"
    echo "Duration: ${DURATION_MIN}m${DURATION_SEC}s"
    echo "Transcribed at: $(date '+%Y-%m-%d %H:%M')"
    echo ""
    echo "---"
    echo ""
    
    for i in $(seq 0 $((NUM_CHUNKS - 1))); do
        cat "$TMPDIR/transcript_${i}.txt"
        echo ""
    done
} > "$OUTPUT"

TOTAL_CHARS=$(wc -m < "$OUTPUT")
echo ""
echo "✅ Done!"
echo "📄 Output: $OUTPUT"
echo "📊 Total characters: $TOTAL_CHARS"
echo "===================="
