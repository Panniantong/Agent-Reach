# Groq Whisper 配置指南

## 功能说明
当 YouTube/Bilibili 视频没有字幕时，用 Groq 的 Whisper API 进行语音转文字。Groq 提供免费额度。

## Agent 可自动完成的步骤

1. 检查是否已配置：
```bash
agent-reach doctor | grep -i "groq\|whisper"
```

2. 如果用户提供了 key，写入配置：
```python
from hivereach.config import Config
c = Config()
c.set("groq_api_key", "用户提供的KEY")
```

3. 测试（可选）：
```bash
curl -s https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer 用户提供的KEY" \
  -o /dev/null -w "%{http_code}"
```
返回 200 = 可用

## 需要用户手动做的步骤

请告诉用户：

> 视频语音转文字需要一个 Groq API Key（免费）。
>
> 步骤：
> 1. 打开 https://console.groq.com
> 2. 用 Google 账号或邮箱注册
> 3. 点击左侧 "API Keys"
> 4. 点击 "Create API Key"
> 5. 复制生成的 Key，发给我
>
> Groq 提供免费额度，日常使用完全够用。

## Agent 收到 key 后的操作

1. 写入配置：`config.set("groq_api_key", key)`
2. 测试 API 可用性
3. 反馈："✅ 语音转文字已开启！现在遇到没有字幕的视频，我也能帮你提取内容了。"
