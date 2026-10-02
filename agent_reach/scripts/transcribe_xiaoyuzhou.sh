#!/bin/bash
# 小宇宙播客转文字脚本
# 用法: bash transcribe.sh [--polish] <小宇宙链接> [输出文件路径]
# 环境变量: GROQ_API_KEY (必须), POLISH_MODEL (可选，默认 qwen/qwen3.8-27b)
#
# --polish: 转录后调用指定的 Groq 模型补中文标点+合理分段
#           保持字母、数字和汉字顺序不变；失败块保留原文并显示警告

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
OUTPUT="${2:-}"

PYTHON_CMD=()
ensure_python() {
    if [ "${#PYTHON_CMD[@]}" -gt 0 ]; then
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_CMD=(python3)
    elif command -v python >/dev/null 2>&1; then
        PYTHON_CMD=(python)
    elif command -v py >/dev/null 2>&1; then
        PYTHON_CMD=(py -3)
    else
        echo "❌ 未找到 Python（尝试过 python3、python、py -3）" >&2
        return 1
    fi
}

ensure_python || exit 1
if ! XIAOYUZHOU_URL="$URL" "${PYTHON_CMD[@]}" <<'PY'
import os
from urllib.parse import urlsplit

try:
    parsed = urlsplit(os.environ["XIAOYUZHOU_URL"])
    hostname = (parsed.hostname or "").lower()
except ValueError:
    raise SystemExit(1)

allowed_host = (
    hostname == "xiaoyuzhoufm.com"
    or hostname.endswith(".xiaoyuzhoufm.com")
)
raise SystemExit(0 if parsed.scheme.lower() in {"http", "https"} and allowed_host else 1)
PY
then
    echo "❌ 仅支持 xiaoyuzhoufm.com 及其子域的 http/https 链接" >&2
    exit 1
fi

# Try env var first, then agent-reach config.yaml
if [ -z "$GROQ_API_KEY" ]; then
    CONFIG_FILE="$HOME/.agent-reach/config.yaml"
    if [ -f "$CONFIG_FILE" ]; then
        ensure_python || exit 1
        CONFIG_FOR_PYTHON="$CONFIG_FILE"
        if command -v cygpath >/dev/null 2>&1; then
            CONFIG_FOR_PYTHON=$(cygpath -w "$CONFIG_FILE")
        fi
        GROQ_API_KEY=$(AGENT_REACH_CONFIG_FILE="$CONFIG_FOR_PYTHON" \
            "${PYTHON_CMD[@]}" -c 'import os, yaml; print((yaml.safe_load(open(os.environ["AGENT_REACH_CONFIG_FILE"])) or {}).get("groq_api_key", ""))' \
            2>/dev/null || true)
    fi
fi
GROQ_API_KEY="${GROQ_API_KEY:?请设置 GROQ_API_KEY 环境变量或运行 agent-reach configure groq-key}"

# Groq API 限制: 25MB per file
MAX_CHUNK_SIZE_MB=20
AUDIO_BITRATE="64k"
CURL_CONNECT_TIMEOUT=15
PAGE_TIMEOUT=60
AUDIO_TIMEOUT=1800
GROQ_TIMEOUT=600
MAX_PAGE_BYTES=5242880
MAX_AUDIO_BYTES=1073741824
MAX_API_RESPONSE_BYTES=33554432
MAX_DURATION_SECONDS=10800
POLISH_MODEL="${POLISH_MODEL:-qwen/qwen3.8-27b}"
POLISH_INCOMPLETE=0

TEMP_ROOT="${TMPDIR:-/tmp}"
if ! WORK_DIR=$(mktemp -d "${TEMP_ROOT%/}/agent-reach-xiaoyuzhou.XXXXXX"); then
    echo "❌ 无法创建临时目录" >&2
    exit 1
fi

cleanup() {
    rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT

# Native Windows curl may encode non-ASCII argv using the ANSI code page.
# Read the UTF-8 field bytes from this invocation's private workspace instead.
PROMPT_FILE="$WORK_DIR/whisper-prompt.txt"
printf '%s' '以下是一段中文普通话播客录音，请输出包含完整中文标点（，。？！：；“”‘’）的转写文本。' > "$PROMPT_FILE"
if command -v cygpath >/dev/null 2>&1; then
    PROMPT_FILE=$(cygpath -w "$PROMPT_FILE")
fi

echo "📻 小宇宙播客转文字"
echo "===================="

# Step 1: 提取音频 URL 和标题
echo "🔍 正在解析页面..."
PAGE=$(curl --fail --show-error --location --silent \
    --connect-timeout "$CURL_CONNECT_TIMEOUT" \
    --max-time "$PAGE_TIMEOUT" \
    --max-filesize "$MAX_PAGE_BYTES" \
    "$URL")
AUDIO_URL=$(echo "$PAGE" | perl -ne 'while (/(https:\/\/media\.xyzcdn\.net\/[^"]*\.(?:m4a|mp3))/gi) { print "$1\n" }' | head -1)
TITLE=$(echo "$PAGE" | perl -ne 'if (/"title":"([^"]*)"/) { print "$1\n"; last }' | head -1)

if [ -z "$AUDIO_URL" ]; then
    echo "❌ 无法从页面提取音频链接"
    exit 1
fi

echo "📝 标题: $TITLE"
echo "🔗 音频: $AUDIO_URL"

# Step 2: 下载音频
echo "⬇️  正在下载音频..."
EXT="${AUDIO_URL##*.}"
curl --fail --show-error --location --silent \
    --connect-timeout "$CURL_CONNECT_TIMEOUT" \
    --max-time "$AUDIO_TIMEOUT" \
    --max-filesize "$MAX_AUDIO_BYTES" \
    -o "$WORK_DIR/original.$EXT" \
    "$AUDIO_URL"
FILE_SIZE=$(ls -lh "$WORK_DIR/original.$EXT" | awk '{print $5}')
echo "📦 文件大小: $FILE_SIZE"

# Step 3: 获取时长
if ! DURATION_RAW=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 \
    "$WORK_DIR/original.$EXT" 2>/dev/null); then
    echo "❌ ffprobe 无法读取音频时长" >&2
    exit 1
fi
if DURATION=$(DURATION_RAW="$DURATION_RAW" MAX_DURATION_SECONDS="$MAX_DURATION_SECONDS" \
    "${PYTHON_CMD[@]}" -c '
import os
import sys
from decimal import Decimal, InvalidOperation

raw = os.environ["DURATION_RAW"]
try:
    value = Decimal(raw)
except InvalidOperation:
    raise SystemExit(2)
if not value.is_finite() or value < 0:
    raise SystemExit(2)
if value > Decimal(os.environ["MAX_DURATION_SECONDS"]):
    raise SystemExit(3)
print(int(value))
'); then
    :
else
    duration_status=$?
    if [ "$duration_status" -eq 3 ]; then
        echo "❌ 音频时长超过 3 小时限制" >&2
    else
        echo "❌ ffprobe 返回无效音频时长: ${DURATION_RAW:-<empty>}" >&2
    fi
    exit 1
fi
DURATION_MIN=$((DURATION / 60))
DURATION_SEC=$((DURATION % 60))
echo "⏱️  时长: ${DURATION_MIN}分${DURATION_SEC}秒"

# Step 4: 转为低码率单声道 MP3
echo "🔄 正在转码..."
ffmpeg -y -i "$WORK_DIR/original.$EXT" -t "$MAX_DURATION_SECONDS" -b:a "$AUDIO_BITRATE" -ac 1 "$WORK_DIR/mono.mp3" 2>/dev/null
MONO_SIZE=$(stat -c%s "$WORK_DIR/mono.mp3" 2>/dev/null || stat -f%z "$WORK_DIR/mono.mp3")
MONO_SIZE_MB=$(awk -v bytes="$MONO_SIZE" 'BEGIN { printf "%.1f", bytes / 1024 / 1024 }')
echo "📦 转码后: ${MONO_SIZE_MB}MB"

# Step 5: 按大小切片
MAX_BYTES=$((MAX_CHUNK_SIZE_MB * 1024 * 1024))

if [ "$MONO_SIZE" -le "$MAX_BYTES" ]; then
    # 不需要切片
    cp "$WORK_DIR/mono.mp3" "$WORK_DIR/chunk_0.mp3"
    NUM_CHUNKS=1
    echo "📎 无需切片"
else
    # 计算需要几个 chunk
    NUM_CHUNKS=$(( (MONO_SIZE / MAX_BYTES) + 1 ))
    CHUNK_DURATION=$(( DURATION / NUM_CHUNKS + 10 ))  # 加 10 秒缓冲
    echo "✂️  切分为 $NUM_CHUNKS 段 (每段约 $((CHUNK_DURATION / 60)) 分钟)..."
    
    for i in $(seq 0 $((NUM_CHUNKS - 1))); do
        START=$((i * CHUNK_DURATION))
        ffmpeg -y -i "$WORK_DIR/mono.mp3" -ss "$START" -t "$CHUNK_DURATION" -c copy "$WORK_DIR/chunk_${i}.mp3" 2>/dev/null
        CHUNK_SIZE=$(ls -lh "$WORK_DIR/chunk_${i}.mp3" | awk '{print $5}')
        echo "   段 $((i+1))/$NUM_CHUNKS: $CHUNK_SIZE"
    done
fi

# Step 6: 调用 Groq Whisper API 转录
echo "🎙️  正在转录 (Groq Whisper large-v3)..."

for i in $(seq 0 $((NUM_CHUNKS - 1))); do
    echo -n "   段 $((i+1))/$NUM_CHUNKS... "
    
    RESPONSE=$(curl --silent --show-error \
        --connect-timeout "$CURL_CONNECT_TIMEOUT" \
        --max-time "$GROQ_TIMEOUT" \
        --max-filesize "$MAX_API_RESPONSE_BYTES" \
        -w "\n%{http_code}" \
        https://api.groq.com/openai/v1/audio/transcriptions \
        -H "Authorization: Bearer $GROQ_API_KEY" \
        -F file="@$WORK_DIR/chunk_${i}.mp3" \
        -F model="whisper-large-v3" \
        -F language="zh" \
        -F "prompt=<$PROMPT_FILE" \
        -F response_format="text")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" != "200" ]; then
        echo "❌ API 错误 (HTTP $HTTP_CODE)"
        echo "$BODY"
        
        # 如果是速率限制，等待后重试
        if [ "$HTTP_CODE" = "429" ]; then
            # 从错误信息中提取等待时间，默认 120 秒
            WAIT_SEC=$(echo "$BODY" | perl -ne 'if (/in (\d+)m/) { print "$1\n"; exit }')
            WAIT_SEC=${WAIT_SEC:-2}
            WAIT_SEC=$((WAIT_SEC * 60 + 30))
            if [ "$WAIT_SEC" -gt 900 ]; then
                WAIT_SEC=900
            fi
            echo "   ⏳ 速率限制，等待 ${WAIT_SEC} 秒后重试..."
            sleep "$WAIT_SEC"
            RESPONSE=$(curl --silent --show-error \
                --connect-timeout "$CURL_CONNECT_TIMEOUT" \
                --max-time "$GROQ_TIMEOUT" \
                --max-filesize "$MAX_API_RESPONSE_BYTES" \
                -w "\n%{http_code}" \
                https://api.groq.com/openai/v1/audio/transcriptions \
                -H "Authorization: Bearer $GROQ_API_KEY" \
                -F file="@$WORK_DIR/chunk_${i}.mp3" \
                -F model="whisper-large-v3" \
                -F language="zh" \
                -F "prompt=<$PROMPT_FILE" \
                -F response_format="text")
            HTTP_CODE=$(echo "$RESPONSE" | tail -1)
            BODY=$(echo "$RESPONSE" | sed '$d')
            
            if [ "$HTTP_CODE" != "200" ]; then
                echo "   ❌ 重试失败"
                exit 1
            fi
        else
            case "$HTTP_CODE" in
                5??)
                    echo "   可尝试兜底：agent-reach transcribe \"$AUDIO_URL\""
                    ;;
            esac
            exit 1
        fi
    fi
    
    echo "$BODY" > "$WORK_DIR/transcript_${i}.txt"
    CHARS=$(wc -m < "$WORK_DIR/transcript_${i}.txt")
    echo "✅ ($CHARS 字)"
done

# Step 6.5 (可选): 用 POLISH_MODEL 给文稿补标点+分段
if [ "$POLISH" = "1" ]; then
    ensure_python || exit 1
    echo "✨ 正在润色（$POLISH_MODEL 加标点+分段）..."
    for i in $(seq 0 $((NUM_CHUNKS - 1))); do
        echo -n "   段 $((i+1))/$NUM_CHUNKS... "
        if IN_FILE="$WORK_DIR/transcript_${i}.txt" \
        OUT_FILE="$WORK_DIR/polished_${i}.txt" \
        GROQ_API_KEY="$GROQ_API_KEY" POLISH_MODEL="$POLISH_MODEL" \
        "${PYTHON_CMD[@]}" <<'PY'
import json, os, sys, time, urllib.request, urllib.error

KEY = os.environ["GROQ_API_KEY"]
IN = os.environ["IN_FILE"]
OUT = os.environ["OUT_FILE"]

MODEL = os.environ["POLISH_MODEL"]
INPUT_CHARS = 1000
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
    request_body = {
        "model": MODEL,
        "temperature": 0.2,
        "max_completion_tokens": max(512, min(3000, len(text) * 2 + 256)),
        "messages": [{"role": "user", "content": PROMPT_TMPL.format(text)}],
    }
    if MODEL.startswith("qwen/"):
        request_body["reasoning_effort"] = "none"
    body = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
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
        payload = r.read(32 * 1024 * 1024 + 1)
    if len(payload) > 32 * 1024 * 1024:
        raise ValueError("polish response exceeds 32 MiB limit")
    resp = json.loads(payload)
    return (
        resp["choices"][0]["message"]["content"].strip(),
        resp["choices"][0].get("finish_reason"),
    )

def original(text, reason):
    sys.stderr.write(f"polish: {reason}; 保留原文\n")
    return text, False


def content_sequence(text):
    return "".join(char for char in text if char.isalnum())


def split_and_polish(text, depth):
    mid = len(text) // 2
    left, left_ok = polish(text[:mid], depth + 1)
    right, right_ok = polish(text[mid:], depth + 1)
    return left + right, left_ok and right_ok


def polish(text, depth=0):
    for attempt in range(3):
        try:
            out, finish_reason = call_groq(text)
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 413 and depth < MAX_DEPTH and len(text) > 1:
                return split_and_polish(text, depth)
            if exc.code == 429 and attempt < 2:
                try:
                    wait = float(exc.headers.get("Retry-After", "2"))
                except (TypeError, ValueError):
                    wait = 2
                time.sleep(max(0, min(60, wait)))
                continue
            return original(text, f"HTTP {exc.code}")
        except Exception as exc:
            return original(text, f"请求失败 ({type(exc).__name__})")
    if not out:
        return original(text, "模型返回空内容")
    if finish_reason == "length":
        if depth < MAX_DEPTH and len(text) > 1:
            return split_and_polish(text, depth)
        return original(text, "模型输出被截断")
    if content_sequence(out) != content_sequence(text):
        return original(text, "模型改写或丢失正文")
    return out, True


content = open(IN, encoding="utf-8").read().strip()
pieces = []
complete = True
for start in range(0, len(content), INPUT_CHARS):
    out, ok = polish(content[start:start + INPUT_CHARS])
    pieces.append(out)
    complete = complete and ok
result = "".join(pieces)
open(OUT, "w", encoding="utf-8").write(result + "\n")
if not complete:
    print(f"⚠️ 部分块未润色，已保留原文 ({len(result)} 字)")
    raise SystemExit(2)
print(f"✅ ({len(result)} 字)")
PY
        then
            :
        else
            POLISH_INCOMPLETE=1
            echo "⚠️ 润色未全部完成；未处理的正文保留原文"
        fi
    done
fi

# Step 7: 合并输出
echo "📄 正在合并文字稿..."

if [ -z "$OUTPUT" ]; then
    if ! OUTPUT=$(mktemp "${TEMP_ROOT%/}/agent-reach-transcript.XXXXXX"); then
        echo "❌ 无法安全创建输出文件" >&2
        exit 1
    fi
fi

{
    echo "# $TITLE"
    echo ""
    echo "来源: $URL"
    echo "时长: ${DURATION_MIN}分${DURATION_SEC}秒"
    echo "转录时间: $(date '+%Y-%m-%d %H:%M')"
    if [ "$POLISH" = "1" ]; then
        if [ "$POLISH_INCOMPLETE" = "1" ]; then
            echo "润色: ${POLISH_MODEL}（部分未完成，保留原文）"
        else
            echo "润色: $POLISH_MODEL"
        fi
    fi
    echo ""
    echo "---"
    echo ""

    for i in $(seq 0 $((NUM_CHUNKS - 1))); do
        if [ "$POLISH" = "1" ] && [ -f "$WORK_DIR/polished_${i}.txt" ]; then
            cat "$WORK_DIR/polished_${i}.txt"
        else
            cat "$WORK_DIR/transcript_${i}.txt"
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
