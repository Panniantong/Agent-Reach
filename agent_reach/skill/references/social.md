# 社交媒体 & 社区

小红书、抖音、Twitter/X、微博、B站、V2EX、Reddit。

## 小红书 / XiaoHongShu (xhs-cli)

```bash
# 搜索笔记
xhs search "query"

# 阅读笔记详情
xhs read NOTE_ID_OR_URL

# 查看评论
xhs comments NOTE_ID_OR_URL

# 浏览热门
xhs hot

# 推荐 feed
xhs feed

# 用户主页
xhs user USER_ID
xhs user-posts USER_ID

# 发帖/互动
xhs post --title "标题" --content "正文" --images img1.jpg img2.jpg
xhs like NOTE_ID
xhs comment NOTE_ID "评论内容"
```

> **安装**: `pipx install xiaohongshu-cli`，然后 `xhs login`（自动从浏览器提取 Cookie）。

## 抖音 / Douyin

```bash
# 解析视频信息
mcporter call 'douyin.parse_douyin_video_info(share_link: "https://v.douyin.com/xxx/")'

# 获取无水印下载链接
mcporter call 'douyin.get_douyin_download_link(share_link: "https://v.douyin.com/xxx/")'

# 提取视频文案
mcporter call 'douyin.extract_douyin_text(share_link: "https://v.douyin.com/xxx/")'
```

> **无需登录**

## Twitter/X (twitter-cli)

```bash
# 搜索推文
twitter search "query" --limit 10

# 读取单条推文（含回复）
twitter tweet URL_OR_ID

# 读取长文 / X Article
twitter article URL_OR_ID

# 用户时间线
twitter user-posts @username --limit 20

# 用户资料
twitter user @username

# 首页时间线
twitter feed --limit 20
```

> **安装**: `pipx install twitter-cli` 或 `uv tool install twitter-cli`
> **认证**: 设置 `TWITTER_AUTH_TOKEN` + `TWITTER_CT0` 环境变量，或确保浏览器已登录 x.com。

## 微博 / Weibo

```bash
# 使用 Jina Reader 读取
curl -s "https://r.jina.ai/https://weibo.com/USER_ID/POST_ID"
```

> 微博主要通过网页抓取，推荐使用通用网页读取方式。

## B站 / Bilibili

```bash
# 获取视频元数据
yt-dlp --dump-json "https://www.bilibili.com/video/BVxxx"

# 下载字幕
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --convert-subs vtt --skip-download -o "/tmp/%(id)s" "URL"
```

> **注意**: 服务器 IP 可能遇到 412 错误。使用 `--cookies-from-browser chrome` 或配置代理。

## V2EX (公开 API)

无需认证，直接调用公开 API。

### 热门主题

```bash
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: agent-reach/1.0"
```

### 节点主题

```bash
# node_name 如: python, tech, jobs, qna, programmers
curl -s "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1" -H "User-Agent: agent-reach/1.0"
```

### 主题详情

```bash
# topic_id 从 URL 获取，如 https://www.v2ex.com/t/1234567
curl -s "https://www.v2ex.com/api/topics/show.json?id=TOPIC_ID" -H "User-Agent: agent-reach/1.0"
```

### 主题回复

```bash
curl -s "https://www.v2ex.com/api/replies/show.json?topic_id=TOPIC_ID&page=1" -H "User-Agent: agent-reach/1.0"
```

### 用户信息

```bash
curl -s "https://www.v2ex.com/api/members/show.json?username=USERNAME" -H "User-Agent: agent-reach/1.0"
```

### Python 调用示例

```python
from agent_reach.channels.v2ex import V2EXChannel

ch = V2EXChannel()

# 获取热门帖子
topics = ch.get_hot_topics(limit=10)
for t in topics:
    print(f"[{t['node_title']}] {t['title']} ({t['replies']} 回复)")

# 获取节点帖子
node_topics = ch.get_node_topics("python", limit=5)

# 获取帖子详情 + 回复
topic = ch.get_topic(1234567)
print(topic["title"], "—", topic["author"])

# 获取用户信息
user = ch.get_user("Livid")
```

> **节点列表**: https://www.v2ex.com/planes

## Reddit (rdt-cli)

```bash
# 搜索帖子
rdt search "query" --limit 10

# 读帖子全文 + 评论
rdt read POST_ID

# 浏览 subreddit
rdt sub python --limit 20

# 浏览热门
rdt popular --limit 10

# 浏览 /r/all
rdt all --limit 10
```

> **安装**: `pipx install rdt-cli`。无需登录即可搜索和阅读。
