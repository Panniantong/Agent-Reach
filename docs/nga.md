# NGA 帖子读取与导出

NGA channel 调用 OpenCLI 的公开浏览器命令复用 Chrome 登录态。
只读取页面，不导出 Cookie，不修改上游工具。

## 一次性配置

```bash
agent-reach install --system --channels nga
```

在 Chrome 安装 [OpenCLI 扩展](https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk)，
然后在同一 Chrome 配置中登录 NGA，保持浏览器开启。扩展安装及权限应由用户确认。
实现基于 OpenCLI 1.8.7 的公开 `browser <session> open/wait/eval/close` 命令。

```bash
opencli doctor
agent-reach doctor --json
```

Agent Reach doctor 不打开页面；桥接连通不会冒充 NGA 登录验证成功。
实际 `read` 成功才证明当前账号能读取指定页面。多个 Chrome 配置可用
`opencli profile list` 查看，再通过 `--profile personal` 显式选择。
Codex 自带浏览器连接和 OpenCLI 扩展是独立连接。

## 使用

```bash
# 默认一页；URL 中的 page 参数作为默认起始页
agent-reach nga read 'https://bbs.nga.cn/read.php?tid=12345678'

# 全帖仅楼主
agent-reach nga read 'https://bbs.nga.cn/read.php?tid=12345678' \
  --only-author --all-pages --state-dir ./nga-export -o author.md

# 第 10 页至末页，仅楼主
agent-reach nga read 'https://bbs.nga.cn/read.php?tid=12345678' \
  --start-page 10 --all-pages --only-author --state-dir ./nga-from-10

# 指定页范围，导出 JSON
agent-reach nga read 'https://bbs.nga.cn/read.php?tid=12345678' \
  --start-page 10 --end-page 15 --format json -o pages-10-15.json

# 中断或达到单次页数预算后继续
agent-reach nga read --resume ./nga-export -o author.md
```

`--only-author` 按第一页主帖的 UID 筛选，同名用户不会误入。
从中间页开始也会读取第一页确认楼主和标题，但第一页内容不加入指定范围。
没有楼主回复的页面也记录为已完成。引用原文保留在发布者的正文中。

`--all-pages` 和 `--end-page` 互斥。默认每次最多读取 100 页，可用
`--max-pages N` 调整（第一页元信息查询不占预算）。默认页间隔 1 秒，
`--interval` 可设置 0–60 秒。末页在任务开始时固定，续传不追踪后来新增页；
获取更新应新建任务。独立浏览器会话完成后释放，不操作原有用户标签页。

## 输出和断点

默认任务目录为 `~/.agent-reach/exports/nga-帖子ID-随机后缀/`，
也可指定 `--state-dir`。路径和进度输出到 stderr，stdout 仅输出选定格式的数据。

- `state.json`：任务参数、楼主信息、各页全部原始楼层。逐页原子保存。
- `export.json`：合并、去重、筛选后的结构化结果。
- `export.md`：同一结果的 Markdown。

仅楼主筛选作用于导出文件，断点仍保留所读取页的全部楼层数据。
续传不重读成功页，不能更换 URL、页范围、筛选和 Chrome profile。
已完成任务可用 `--resume` 重新输出不同格式，无需打开浏览器。

结果包含标题、楼主 UID、总页数、`pages_read`、`start_page`、`end_page`、
`complete`、`next_page` 和 `posts`。每个楼层含回复 ID、楼层号、作者、时间、
正文、图片和链接、修改信息、原帖链接及页码。`complete` 指指定范围完成。

图片保留链接（含懒加载图片），不下载或 OCR；不自动展开折叠内容。
验证页、无正文、错误页和重复翻页不会记为成功。修复浏览器状态后可续传。
失败时旧导出文件可能仍为上次快照，以 `state.json` 为准。

退出码：`0` 完成；`1` 读取/配置失败；`2` 命令参数错误；
`3` 达到单次页数预算，已输出部分结果；`130` 用户中断。

## Python

```python
from pathlib import Path
from agent_reach.channels import get_channel
from agent_reach.nga_export import export_thread

page = get_channel('nga').read('https://bbs.nga.cn/read.php?tid=12345678')
result = export_thread(
    'https://bbs.nga.cn/read.php?tid=12345678',
    directory=Path('./nga-export'), start_page=10,
    all_pages=True, only_author=True,
)
```

支持 bbs.nga.cn、nga.178.com、ngabbs.com 的完整 read.php?tid=... 链接；
目前真实 DOM 验证使用 bbs.nga.cn。暂不支持站内搜索和 authorid 等筛选视图。

## 开发验证

Python 测试：`pytest tests/test_nga.py -v`。
提取脚本的 DOM 测试使用 Node.js 和 jsdom，不需要浏览器登录：

```bash
npm install --prefix /tmp/nga-dom-test jsdom
NODE_PATH=/tmp/nga-dom-test/node_modules node tests/nga_dom_test.cjs
```
