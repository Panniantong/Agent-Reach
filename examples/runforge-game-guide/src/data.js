export const games = [
  {
    id: "balatro",
    name: "Balatro",
    cn: "小丑牌",
    status: "已上线",
    volume: "高",
    note: "种子、构筑、Joker 数据库",
  },
  {
    id: "spire",
    name: "Slay the Spire",
    cn: "杀戮尖塔",
    status: "规划中",
    volume: "高",
    note: "遗物、路线、卡组评分",
  },
  {
    id: "backpack",
    name: "Backpack Battles",
    cn: "背包乱斗",
    status: "调研中",
    volume: "中",
    note: "配方、流派、对局统计",
  },
  {
    id: "hades",
    name: "Hades II",
    cn: "黑帝斯 II",
    status: "观察中",
    volume: "高",
    note: "祝福、武器、版本路线",
  },
];

export const seedLibrary = {
  "9OUU79": {
    seed: "9OUU79",
    deck: "等离子牌组",
    archetype: "钢K男爵",
    confidence: 92,
    ceiling: "无尽局高上限",
    summary: "中文社区常见的钢K练手种，适合用来验证红封钢铁 K、男爵和哑剧的路线节奏。",
    jokers: ["男爵", "哑剧", "蓝图", "头脑风暴", "DNA"],
    warnings: ["前期经济别断", "复制牌优先给红封钢K", "Boss 盲注要提前看反制"],
    stages: [
      {
        label: "Ante 1-2",
        title: "先保命与开经济",
        items: ["优先拿倍率/筹码过渡小丑", "保留塔罗经济", "看到死神可先准备 K 模板"],
      },
      {
        label: "Ante 3-5",
        title: "开始定向钢K",
        items: ["找男爵/哑剧任一核心", "玻璃别贪，先稳定钢铁", "红封 K 出现后开始复制"],
      },
      {
        label: "Ante 6+",
        title: "进入手牌倍率循环",
        items: ["蓝图/头脑风暴复制男爵或哑剧", "高牌出手，K 留手", "负片与幻彩优先给核心组件"],
      },
    ],
  },
  U8RJYV6N: {
    seed: "U8RJYV6N",
    deck: "幽灵牌组",
    archetype: "传奇转钢K",
    confidence: 95,
    ceiling: "超高上限",
    summary: "更偏爽局的高上限种，适合从传奇/复制体系过渡到钢K手牌倍率。",
    jokers: ["佩尔克奥", "负片蓝图", "头脑风暴", "男爵", "哑剧"],
    warnings: ["组件多，排序比单一路线更重要", "先确定复制对象，再投入资源"],
    stages: [
      {
        label: "Ante 1-2",
        title: "拿核心复制位",
        items: ["留经济给关键小丑", "幽灵牌组利用灵魂/幻灵找爆点", "不要过早删 K"],
      },
      {
        label: "Ante 3-5",
        title: "从传奇体系转倍率",
        items: ["优先确认蓝图/头脑风暴复制目标", "有男爵后开始锁 K", "哑剧出现后提升留手收益"],
      },
      {
        label: "Ante 6+",
        title: "堆红封钢K",
        items: ["复制红封钢K模板", "钱多时重掷找负片/幻彩", "Boss 风险用导演剪辑或重开商店处理"],
      },
    ],
  },
  "6B678B4W": {
    seed: "6B678B4W",
    deck: "等离子牌组",
    archetype: "DNA钢K",
    confidence: 89,
    ceiling: "稳定成型",
    summary: "适合练习 DNA 复制红封钢K的节奏，重点是把模板牌做干净。",
    jokers: ["DNA", "男爵", "哑剧", "头脑风暴", "秀场"],
    warnings: ["DNA 没模板就是空转", "删牌要避免删掉复制目标"],
    stages: [
      {
        label: "Ante 1-2",
        title: "做牌面模板",
        items: ["保留 K，优先改造花色和增强", "等离子牌组先稳筹码", "经济牌比空转倍率更关键"],
      },
      {
        label: "Ante 3-5",
        title: "找 DNA 与红封",
        items: ["DNA 出现后只复制目标 K", "死神复制增强 K", "经济允许时搜男爵/哑剧"],
      },
      {
        label: "Ante 6+",
        title: "完成留手体系",
        items: ["男爵哑剧成型后转高牌", "头脑风暴复制收益最高的一侧", "保留导演剪辑处理 Boss"],
      },
    ],
  },
  "1U9CYPIT": {
    seed: "1U9CYPIT",
    deck: "黄色牌组",
    archetype: "标准男爵哑剧",
    confidence: 84,
    ceiling: "教学友好",
    summary: "结构比较标准，适合新手理解男爵、哑剧、蓝图和 DNA 之间的优先级。",
    jokers: ["哑剧", "男爵", "蓝图", "头脑风暴", "DNA"],
    warnings: ["黄色牌组开局钱多，但不要乱重掷", "核心没齐前别把牌组压得太薄"],
    stages: [
      {
        label: "Ante 1-2",
        title: "用经济换稳定",
        items: ["先买能过盲注的便宜组件", "控制重掷次数", "保留塔罗做 K"],
      },
      {
        label: "Ante 3-5",
        title: "男爵哑剧闭环",
        items: ["有男爵就保 K 在手", "有哑剧就提高钢铁/红封收益", "蓝图复制当前更缺的倍率源"],
      },
      {
        label: "Ante 6+",
        title: "扩大 K 池",
        items: ["DNA/死神补数量", "幽灵牌找负片扩格子", "高牌出手，手牌尽量留满 K"],
      },
    ],
  },
};

export const defaultRoute = {
  seed: "DEMO2026",
  deck: "等离子牌组",
  archetype: "钢K男爵",
  confidence: 76,
  ceiling: "可验证路线草案",
  summary: "这个 MVP 会基于种子字符、牌组和流派生成路线建议。上线前需要接入真实种子解析器，当前用于演示产品交互。",
  jokers: ["男爵", "哑剧", "DNA", "蓝图", "导演剪辑"],
  warnings: ["未接入真实 RNG 数据", "请把输出标注为路线建议，不要标注为必出结果"],
  stages: [
    {
      label: "Ante 1-2",
      title: "先打通前期",
      items: ["找低成本过渡小丑", "攒钱到 25 元利息线", "优先保留 K 和塔罗复制材料"],
    },
    {
      label: "Ante 3-5",
      title: "锁定流派核心",
      items: ["搜男爵/哑剧/DNA 任一核心", "开始做红封钢铁 K 模板", "删除低价值非 K 牌"],
    },
    {
      label: "Ante 6+",
      title: "冲刺无尽局",
      items: ["复制 K，保持手牌留满", "蓝图复制男爵或哑剧", "提前处理限制出牌的 Boss 盲注"],
    },
  ],
};

export const contentModules = [
  {
    title: "钢K流完整攻略",
    type: "Build Guide",
    intent: "新手到高注",
    pages: 12,
    growth: "+38%",
    image: "/guide-images/steel-king-route.webp",
    source:
      "https://games.gg/balatro/guides/baron-mime-balatro-build/",
  },
  {
    title: "种子库精选路线",
    type: "Seed Vault",
    intent: "长尾搜索",
    pages: 36,
    growth: "+61%",
    image: "/guide-images/seed-vault.webp",
    source: "https://balatroseeds.com/",
  },
  {
    title: "Joker 数据库",
    type: "Database",
    intent: "信息检索",
    pages: 150,
    growth: "+44%",
    image: "/guide-images/joker-database.webp",
    source: "https://balatrowiki.org/",
  },
  {
    title: "多游戏扩展路线",
    type: "Roadmap",
    intent: "站群扩展",
    pages: 28,
    growth: "+29%",
    image: "/guide-images/expansion-roadmap.webp",
    source:
      "https://www.gamegrin.com/news/steam-deckbuilders-fest-top-20-popular-discounted-games/",
  },
];

export const researchSources = [
  {
    label: "Baron + Mime Steel King Guide",
    outlet: "GAMES.GG",
    url: "https://games.gg/balatro/guides/baron-mime-balatro-build/",
  },
  {
    label: "Balatro Steel Cards Guide",
    outlet: "GAMES.GG",
    url: "https://games.gg/balatro/guides/balatro-steel-cards-guide/",
  },
  {
    label: "Balatro Seeds",
    outlet: "BalatroSeeds",
    url: "https://balatroseeds.com/",
  },
  {
    label: "BalatroSeed 中文路线",
    outlet: "BalatroSeed",
    url: "https://balatroseed.net/zh",
  },
  {
    label: "Balatro Calculator",
    outlet: "EFHIII",
    url: "https://efhiii.github.io/balatro-calculator/",
  },
  {
    label: "Seed Analyzer",
    outlet: "Blueprint",
    url: "https://github.com/miaklwalker/Blueprint",
  },
];

export const opportunityRows = [
  ["balatro seeds", "种子库", "高", "工具页"],
  ["小丑牌钢K流", "中文攻略", "中高", "构筑页"],
  ["balatro calculator", "计分器", "高", "工具页"],
  ["balatro joker list", "数据库", "高", "百科页"],
  ["9OUU79 route", "种子路线", "中", "长尾页"],
];
