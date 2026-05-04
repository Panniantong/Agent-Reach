#!/bin/bash
# 小宇宙播客转文字脚本
# 用法: bash transcribe.sh [--polish] <小宇宙链接> [输出文件路径]
# 环境变量: GROQ_API_KEY (必须)
#
# --polish: 转录后调用 Groq Llama 3.3 70B 给文稿补中文标点+合理分段
#           （Whisper 对中文标点支持较弱，开启后阅读体验显著更好）

set -e

POLISH=0
while [ $# -gt 0 ]; do
    case "$1" in
        --polish) POLISH=1; shift ;;
        --) shift; break ;;
        -h|--help)
            echo "用法: bash transcribe.sh [--polish] <小宇宙链接> [输出文件路径]"
            exit 0 ;;
        --*)
            echo "未知选项: $1" >&2
            exit 1 ;;
        *) break ;;
    esac
done

URL="${1:?用法: bash transcribe.sh [--polish] <小宇宙链接> [输出文件路径]}"
OUTPUT="${2:-/tmp/podcast_transcript.txt}"
TMPDIR="/tmp/xiaoyuzhou_$$"

# Try env var first, then agent-reach config.yaml
if [ -z "$GROQ_API_KEY" ]; then
    CONFIG_FILE="$HOME/.agent-reach/config.yaml"
    if [ -f "$CONFIG_FILE" ]; then
        GROQ_API_KEY=$(python3 -c "import yaml; print((yaml.safe_load(open('$CONFIG_FILE')) or {}).get('groq_api_key',''))" 2>/dev/null || true)
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
        -F prompt="以下是一段中文普通话播客录音，请输出包含完整中文标点（，。？！：；""''）的转写文本。" \
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

# Step 6.5 (可选): 用 Llama 3.3 70B 给文稿补标点+分段
if [ "$POLISH" = "1" ]; then
    echo "✨ 正在润色（Llama 3.3 70B 加标点+分段）..."
    for i in $(seq 0 $((NUM_CHUNKS - 1))); do
        echo -n "   段 $((i+1))/$NUM_CHUNKS... "
        IN_FILE="$TMPDIR/transcript_${i}.txt" \
        OUT_FILE="$TMPDIR/polished_${i}.txt" \
        GROQ_API_KEY="$GROQ_API_KEY" \
        python3 <<'PY'
import json, os, sys, urllib.request, urllib.error

KEY = os.environ["GROQ_API_KEY"]
IN = os.environ["IN_FILE"]
OUT = os.environ["OUT_FILE"]

MODEL = "llama-3.3-70b-versatile"
MAX_DEPTH = 3
PROMPT_TMPL = (
    "以下是一段中文普通话播客的语音转写片段，由于 Whisper 对中文标点支持较弱，"
    "整段几乎没有标点。请你**只做一件事**：在合适位置补充中文标点（，。！？：；），"
    "可以适度分段。\n\n"
    "**严格要求**：\n"
    "- 不得修改、删除、增加任何汉字或英文/数字\n"
    "- 不得改写、润色、总结\n"
    "- 不得添加任何解释、前言、后记\n"
    "- 直接输出加好标点+合理分段后的全文\n\n"
    "原文：\n{}"
)

def call_groq(text):
    body = json.dumps({
        "model": MODEL,
        "temperature": 0.2,
        "max_completion_tokens": 8192,
        "messages": [{"role": "user", "content": PROMPT_TMPL.format(text)}],
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "User-Agent": "agent-reach-xiaoyuzhou/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        resp = json.load(r)
    return (
        resp["choices"][0]["message"]["content"].strip(),
        resp["choices"][0].get("finish_reason"),
    )

def polish(text, depth=0):
    try:
        out, fr = call_groq(text)
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"polish HTTP {e.code}: {e.read().decode(errors='replace')[:200]}\n")
        return text  # fallback to raw
    except Exception as e:
        sys.stderr.write(f"polish error: {e}\n")
        return text
    if fr != "length" or depth >= MAX_DEPTH:
        return out
    # 输出被截断：从中点切两半递归处理
    mid = len(text) // 2
    return polish(text[:mid], depth + 1) + polish(text[mid:], depth + 1)

content = open(IN, encoding="utf-8").read().strip()
result = polish(content)
open(OUT, "w", encoding="utf-8").write(result + "\n")
print(f"✅ ({len(result)} 字)")
PY
    done
fi

# Step 7: 合并输出
echo "📄 正在合并文字稿..."

{
    echo "# $TITLE"
    echo ""
    echo "来源: $URL"
    echo "时长: ${DURATION_MIN}分${DURATION_SEC}秒"
    echo "转录时间: $(date '+%Y-%m-%d %H:%M')"
    if [ "$POLISH" = "1" ]; then
        echo "润色: Groq Llama 3.3 70B"
    fi
    echo ""
    echo "---"
    echo ""

    for i in $(seq 0 $((NUM_CHUNKS - 1))); do
        if [ "$POLISH" = "1" ] && [ -f "$TMPDIR/polished_${i}.txt" ]; then
            cat "$TMPDIR/polished_${i}.txt"
        else
            cat "$TMPDIR/transcript_${i}.txt"
        fi
        echo ""
    done
} > "$OUTPUT"

TOTAL_CHARS=$(wc -m < "$OUTPUT")
echo ""
echo "✅ 完成！"
echo "📄 输出: $OUTPUT"
echo "📊 总字数: $TOTAL_CHARS"
echo "===================="
