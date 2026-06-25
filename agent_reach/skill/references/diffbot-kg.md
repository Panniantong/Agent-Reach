# Diffbot 知识图谱（DQL）

用 DQL（Diffbot Query Language）对 Diffbot 知识图谱做**结构化检索**：按字段精确查询公司 / 人物 / 文章 / 产品等实体，支持过滤、排序、聚合（facet）。区别于全网搜索（见 search.md 的 Diffbot 全网搜索 / Exa）——KG 返回的是带结构化字段的实体记录，不是网页链接。

调用入口是 diffbot-python 的 `db dql` 命令组；**需免费 Token**（与全网搜索共用，见下）。

## 何时用 KG（vs 全网搜索）

- 「找 X 类公司，按员工数/地区/融资过滤」「某话题最新文章按时间排序」「某人的任职经历」→ **KG / DQL**
- 「关于 X 的网页 / 最新报道随便看看」→ 全网搜索（`db web-search`）

## 配置（一次）

```bash
# 1) 免费 Token：https://app.diffbot.com/get-started/
agent-reach configure diffbot-token <token>     # 写入 ~/.diffbot/credentials，db 自动读取

# 2) 缓存本体（ontology），让 `db dql ontology` 能导航字段
db dql init                                      # 刷新 ~/.diffbot/ontology.json，校验 Token

# 确认通道就绪
agent-reach doctor --json                        # diffbot_kg 为 ok
```

`db dql init` 会刷新本体缓存、重置 `~/.diffbot/tmp/`、并校验 Token。**一个会话只在开头 init 一次**，本体已缓存到磁盘，不要中途重复 init。

## 核心工作流：init → 导航本体 → 写 DQL → probe → export

DQL 字段名必须来自本体。**别凭记忆猜字段——先用 `db dql ontology` 查清楚再写。**

### 1) 导航本体（关键步骤）

```bash
db dql ontology types                       # 所有实体类型名（Organization / Person / Article / Product ...）
db dql ontology composites                  # 所有复合类型名（Location / Employment ...）
db dql ontology enums                       # 所有枚举类型名
db dql ontology taxonomies                  # 所有分类法（taxonomy）名

db dql ontology fields <Type> [regex]       # 某实体类型或复合类型的字段（可用正则过滤）
db dql ontology taxonomy <Name> [regex]     # 某分类法的取值（会递归子类）
db dql ontology enum <Name>                 # 某枚举的取值
db dql ontology search <regex>              # 兜底：在整个本体里搜任何 name
```

- `fields` 同时接受实体类型名（如 `Organization`）和复合类型名（如 `Location`、`Employment`），自动路由。
- 输出格式：`<name>: [<type>] [isList] [isComposite] [isEnum]`。`isComposite` 的字段可用 `{}` 子查询；`isList` 是列表（含历史值）。
- **需要查多个字段/类型时，把多条 `db dql ontology` 作为并行命令一次性发出**，不要串行。

常见导航例子：

```bash
db dql ontology fields Organization location          # Organization 上和 location 有关的字段
db dql ontology fields Location                        # Location 复合类型的字段（city/region/country ...）
db dql ontology taxonomy OrganizationCategory semiconductor   # 行业分类里和半导体相关的取值
db dql ontology enum Language
db dql ontology search asset                           # 不知道字段在哪时的兜底搜索
```

### 2) 写 DQL

每条 DQL 都以 `type:` 开头。先从常见类型（`Organization` / `Person` / `Article` / `Product`）入手，不够再用 `db dql ontology types` 找更具体的类型。

```
type:Organization name:"Diffbot"
type:Product site:"ikea.com"
type:Organization location.city.name:"San Francisco" investments.investors.name:"Andreessen Horowitz"
type:Article categories.name:"War and Conflicts" tags.label:"Ethiopia" date>="2020-11-01" date<="2022-11-30" sortBy:date
type:Person employments.{employer.name:"Diffbot" isCurrent:true}
```

**操作符**

| 操作符 | 语法 | 示例 |
| --- | --- | --- |
| 包含（字符串） | `field:"value"` | `name:"Diffbot"` |
| 正则 | `re:field:"pattern"` | `re:name:"^Apple"` |
| 精确匹配 | `strict:field:"value"` | `strict:name:"Apple Inc"` |
| 大于 / 小于 | `field>N` / `field<N` | `nbEmployees>500` |
| 不等于 | `field!=value` | `gender!="MALE"` |
| 最大 / 最小 | `max:field:N` / `min:field:N` | `max:capitalization.value:1000000` |
| 区间 | `range:field:N-M` | `range:nbEmployees:10-100` |
| AND（隐式） | 空格分隔 | `type:Organization isPublic:true` |
| OR | `or(v1,v2)` | `categories.name:or("Software companies","Hardware companies")` |
| NOT | `not(condition)` | `not(isPublic:true)`、`not(has:parentCompany)` |
| 邻近 | `near(...)` | `near(type:Place name:"San Francisco", 10mi)` |
| 相似（仅 Organization） | `similarTo(...)` | `similarTo(type:Organization homepageUri:"walmart.com")` |
| 字段存在 | `has:field` | `has:sicClassification` |
| 包含/排除返回字段 | `get:field` / `get:!field` | `has:subsidiaries get:subsidiaries` |
| 聚合（facet） | `facet:field` | `facet:locations.city.name` |
| 升序 / 降序排序 | `sortBy:field` / `revSortBy:field` | `sortBy:nbEmployees` |

**子查询 `{}`（同一嵌套对象上的多条件）**

```
type:Person employments.{employer.name:"Diffbot" isCurrent:true}
```

不加 `{}` 两个条件相互独立（匹配「在 Diffbot 任过职」**且**「有任一当前职位」的人，可能是两段不同经历）。`{}` 只能用在复合类型的列表字段上——用 `db dql ontology fields` 确认 `isComposite`。

**单数 vs 复数字段（主值 vs 全部/历史）**

| 单数（主值/当前） | 复数（全部/历史） |
| --- | --- |
| `location` | `locations` |
| `name` | `allNames` |
| `homepageUri` | `allUris` |

要按实体的**主**事实过滤时用单数。例：找总部在美国的公司用 `location.country.name:"United States"`，而不是 `locations.country.name:...`（后者会命中任何在美国有分支的外国公司）。

**正则**：慢且耗算力，能不用就不用；非用不可时只写短、简单、快的匹配。

#### 实体特定技巧

**Article**
- `categories.name:"<分类名>"` 是按主题收窄文章的利器，分类名用 `db dql ontology taxonomy` 查。
- `tags.label:"<实体名>"` 按提及的实体精炼；标签没有穷举列表，太严就退回 `text:` 匹配。
- 除非另有要求，文章查询都以 `sortBy:date` 结尾（最新在前）。

**Organization**
- `categories.name` 通常是构造公司查询最好的起点。

### 3) probe：并行验证查询选择性（提交前必做）

正式取数前，先用 `db dql probe` 并行跑多个候选变体，看命中数（size=0），确认查询不太宽也不太窄：

```bash
db dql probe \
  'type:Organization descriptors:"GPU" location.country.name:"United States"' \
  'type:Organization descriptors:"GPU" location.country.name:"United States" categories.name:"Semiconductor Companies"' \
  'type:Organization descriptors:"GPU" location.country.name:"United States" isPublic:true'
```

输出是按命中数排序的文本表；加 `--json` 得机读结果。**绝不要在 shell `for` 循环里串行 curl**——probe 内部已并行。

### 4) export：取数与展示

```bash
# 后续还要分析/管道处理 → JSON
db dql export "<DQL>" --out ~/.diffbot/tmp/<name>.json --format json --size N

# 直接给用户看表格 → CSV，用 --spec 选列
db dql export "<DQL>" --out ~/.diffbot/tmp/<name>.csv \
  --spec "name,Name;nbEmployees,Employees;homepageUri,Website;location.city.name,City;isPublic,Public"
```

- `--out <file>` 把响应直接写文件；不带 `--out` 则打印表格到 stdout。
- 非小结果集**优先 `--out` 写盘**：先 `probe` 验证选择性，再 `export --out` 落盘，别把全量数据拉进对话里探索（白烧 token）。
- `--spec` 格式：`<字段路径>,<显示名>` 用 `;` 分隔；字段路径用小写（`name` 不是 `Name`）；列表/复合字段只渲染主值。
- 翻页：`--size N`、`--from K`。
- `type:Article` 导出别直接读 `text`/`content`，`summary` 更合适。

切片 JSON（传给其他工具前）：

```bash
jq '[.data[0].entity | path(..)] | map(join(".")) | unique' ~/.diffbot/tmp/<name>.json
```

**facet 聚合**：分布/聚合类问题（「柏林创业公司常见行业？」「员工规模分布？」）用 facet。facet 响应每个桶有 `value`/`count`/`callbackQuery`，**不是** `entity` 记录——想要逐条实体时别用 facet。

## 性能纪律

- 一次 Bash 调用只查一个本体字段是浪费——要查多个时在**同一条消息里并行发多条** Bash 命令。
- N 个变体的命中数检查一律用 `db dql probe`（内部并行），不要 shell 串行循环。
- 一个会话只 `db dql init` 一次，本体已在磁盘缓存。
