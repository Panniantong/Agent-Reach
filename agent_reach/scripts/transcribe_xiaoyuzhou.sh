#!/bin/bash
# 小宇宙播客转文字脚本
# 用法: bash transcribe.sh <小宇宙链接> [输出文件路径]
# 环境变量: GROQ_API_KEY (必须)

set -e

URL="${1:?用法: bash transcribe.sh <小宇宙链接> [输出文件路径]}"
OUTPUT="${2:-/tmp/podcast_transcript.txt}"
TMPDIR="/tmp/xiaoyuzhou_$$"

# Try env var first, then agent-reach config
if [ -z "$GROQ_API_KEY" ]; then
    CONFIG_FILE="$HOME/.agent-reach/config.json"
    if [ -f "$CONFIG_FILE" ]; then
        GROQ_API_KEY=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('groq_api_key',''))" 2>/dev/null || true)
    fi
fi
GROQ_API_KEY="${GROQ_API_KEY:?请设置 GROQ_API_KEY 环境变量或运行 agent-reach configure groq-key}"

# Groq API 限制: 25MB per file
MAX_CHUNK_SIZE_MB=20
AUDIO_BITRATE="64k"

cleanup() {
    rm -rf "$TMPDIR"
}
trap cleanup EXIT

mkdir -p "$TMPDIR"

echo "📻 小宇宙播客转文字"
echo "===================="

# Step 1: 提取音频 URL 和标题
echo "🔍 正在解析页面..."
PAGE=$(curl -s "$URL")
AUDIO_URL=$(echo "$PAGE" | grep -oP 'https://media\.xyzcdn\.net/[^"]*\.(m4a|mp3)' | head -1)
TITLE=$(echo "$PAGE" | grep -oP '"title":"[^"]*"' | head -1 | sed 's/"title":"//;s/"//')

if [ -z "$AUDIO_URL" ]; then
    echo "❌ 无法从页面提取音频链接"
    exit 1
fi

echo "📝 标题: $TITLE"
echo "🔗 音频: $AUDIO_URL"

# Step 2: 下载音频
echo "⬇️  正在下载音频..."
EXT="${AUDIO_URL##*.}"
curl -sL -o "$TMPDIR/original.$EXT" "$AUDIO_URL"
FILE_SIZE=$(ls -lh "$TMPDIR/original.$EXT" | awk '{print $5}')
echo "📦 文件大小: $FILE_SIZE"

# Step 3: 获取时长
DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$TMPDIR/original.$EXT" 2>/dev/null | cut -d. -f1)
DURATION_MIN=$((DURATION / 60))
DURATION_SEC=$((DURATION % 60))
echo "⏱️  时长: ${DURATION_MIN}分${DURATION_SEC}秒"

# Step 4: 转为低码率单声道 MP3
echo "🔄 正在转码..."
ffmpeg -y -i "$TMPDIR/original.$EXT" -b:a "$AUDIO_BITRATE" -ac 1 "$TMPDIR/mono.mp3" 2>/dev/null
MONO_SIZE=$(stat -c%s "$TMPDIR/mono.mp3" 2>/dev/null || stat -f%z "$TMPDIR/mono.mp3")
echo "📦 转码后: $(echo "$MONO_SIZE / 1024 / 1024" | bc)MB"

# Step 5: 按大小切片
MAX_BYTES=$((MAX_CHUNK_SIZE_MB * 1024 * 1024))

if [ "$MONO_SIZE" -le "$MAX_BYTES" ]; then
    # 不需要切片
    cp "$TMPDIR/mono.mp3" "$TMPDIR/chunk_0.mp3"
    NUM_CHUNKS=1
    echo "📎 无需切片"
else
    # 计算需要几个 chunk
    NUM_CHUNKS=$(( (MONO_SIZE / MAX_BYTES) + 1 ))
    CHUNK_DURATION=$(( DURATION / NUM_CHUNKS + 10 ))  # 加 10 秒缓冲
    echo "✂️  切分为 $NUM_CHUNKS 段 (每段约 $((CHUNK_DURATION / 60)) 分钟)..."
    
    for i in $(seq 0 $((NUM_CHUNKS - 1))); do
        START=$((i * CHUNK_DURATION))
        ffmpeg -y -i "$TMPDIR/mono.mp3" -ss "$START" -t "$CHUNK_DURATION" -c copy "$TMPDIR/chunk_${i}.mp3" 2>/dev/null
        CHUNK_SIZE=$(ls -lh "$TMPDIR/chunk_${i}.mp3" | awk '{print $5}')
        echo "   段 $((i+1))/$NUM_CHUNKS: $CHUNK_SIZE"
    done
fi

# Step 6: 调用 Groq Whisper API 转录
echo "🎙️  正在转录 (Groq Whisper large-v3)..."

for i in $(seq 0 $((NUM_CHUNKS - 1))); do
    echo -n "   段 $((i+1))/$NUM_CHUNKS... "
    
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
        echo "❌ API 错误 (HTTP $HTTP_CODE)"
        echo "$BODY"
        
        # 如果是速率限制，等待后重试
        if [ "$HTTP_CODE" = "429" ]; then
            # 从错误信息中提取等待时间，默认 120 秒
            WAIT_SEC=$(echo "$BODY" | grep -oP 'in \K[0-9]+m' | sed 's/m//' | head -1)
            WAIT_SEC=${WAIT_SEC:-2}
            WAIT_SEC=$((WAIT_SEC * 60 + 30))
            echo "   ⏳ 速率限制，等待 ${WAIT_SEC} 秒后重试..."
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
                echo "   ❌ 重试失败"
                exit 1
            fi
        else
            exit 1
        fi
    fi
    
    echo "$BODY" > "$TMPDIR/transcript_${i}.txt"
    CHARS=$(wc -m < "$TMPDIR/transcript_${i}.txt")
    echo "✅ ($CHARS 字)"
done

# Step 7: 合并输出
echo "📄 正在合并文字稿..."

{
    echo "# $TITLE"
    echo ""
    echo "来源: $URL"
    echo "时长: ${DURATION_MIN}分${DURATION_SEC}秒"
    echo "转录时间: $(date '+%Y-%m-%d %H:%M')"
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
echo "✅ 完成！"
echo "📄 输出: $OUTPUT"
echo "📊 总字数: $TOTAL_CHARS"
echo "===================="
