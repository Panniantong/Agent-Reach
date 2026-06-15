import { useMemo, useState } from "react";
import {
  BarChart3,
  BookOpen,
  ChevronRight,
  CircleDollarSign,
  Copy,
  Database,
  Flame,
  Gem,
  Layers3,
  LibraryBig,
  Mail,
  Play,
  Search,
  ShieldAlert,
  Sparkles,
  Swords,
  Trophy,
} from "lucide-react";
import {
  contentModules,
  defaultRoute,
  games,
  opportunityRows,
  researchSources,
  seedLibrary,
} from "./data.js";

const archetypes = ["钢K男爵", "标准男爵哑剧", "DNA钢K", "传奇转钢K", "金注通关"];
const decks = ["等离子牌组", "幽灵牌组", "黄色牌组", "蓝色牌组", "方格牌组"];

function normalizeSeed(value) {
  return value.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function scoreSeed(seed, archetype) {
  const source = `${seed}:${archetype}`;
  return source.split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
}

function deriveRoute(seed, deck, archetype) {
  const normalized = normalizeSeed(seed);
  if (seedLibrary[normalized]) {
    return { ...seedLibrary[normalized], deck, archetype };
  }

  const score = scoreSeed(normalized || "DEMO2026", archetype);
  return {
    ...defaultRoute,
    seed: normalized || defaultRoute.seed,
    deck,
    archetype,
    confidence: 68 + (score % 23),
    ceiling: score % 2 === 0 ? "偏稳定" : "偏高上限",
  };
}

function App() {
  const [selectedGame, setSelectedGame] = useState("balatro");
  const [seed, setSeed] = useState("9OUU79");
  const [deck, setDeck] = useState("等离子牌组");
  const [archetype, setArchetype] = useState("钢K男爵");
  const [route, setRoute] = useState(seedLibrary["9OUU79"]);
  const [savedSeeds, setSavedSeeds] = useState(["9OUU79", "U8RJYV6N"]);
  const [email, setEmail] = useState("");
  const [subscribed, setSubscribed] = useState(false);

  const activeGame = useMemo(
    () => games.find((game) => game.id === selectedGame) ?? games[0],
    [selectedGame]
  );

  const knownSeeds = Object.keys(seedLibrary);

  function analyzeSeed(event) {
    event?.preventDefault();
    setRoute(deriveRoute(seed, deck, archetype));
  }

  function saveCurrentSeed() {
    const normalized = normalizeSeed(route.seed);
    setSavedSeeds((current) =>
      current.includes(normalized) ? current : [normalized, ...current].slice(0, 5)
    );
  }

  function useSuggestedSeed(nextSeed) {
    setSeed(nextSeed);
    const nextRoute = seedLibrary[nextSeed];
    setDeck(nextRoute.deck);
    setArchetype(nextRoute.archetype);
    setRoute(nextRoute);
  }

  function subscribe(event) {
    event.preventDefault();
    if (email.includes("@")) {
      setSubscribed(true);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="RunForge 首页">
          <span className="brand-mark">R</span>
          <span>
            <strong>RunForge</strong>
            <small>策略游戏攻略工具站</small>
          </span>
        </a>
        <nav className="nav-links" aria-label="主导航">
          {["游戏库", "种子库", "构筑", "工具", "数据洞察"].map((item) => (
            <a key={item} href={`#${item}`}>
              {item}
            </a>
          ))}
        </nav>
        <div className="topbar-actions">
          <button className="icon-button" type="button" aria-label="搜索">
            <Search size={18} />
          </button>
          <button className="primary-button compact" type="button">
            <Sparkles size={16} />
            生成路线
          </button>
        </div>
      </header>

      <main className="workspace" id="top">
        <aside className="game-rail" aria-label="游戏库">
          <div className="rail-heading">
            <LibraryBig size={17} />
            <span>游戏库</span>
          </div>
          <div className="game-list">
            {games.map((game) => (
              <button
                className={`game-card ${selectedGame === game.id ? "active" : ""}`}
                key={game.id}
                type="button"
                onClick={() => setSelectedGame(game.id)}
              >
                <span className="game-code">{game.name.slice(0, 2).toUpperCase()}</span>
                <span className="game-copy">
                  <strong>{game.cn}</strong>
                  <small>{game.note}</small>
                </span>
                <em>{game.status}</em>
              </button>
            ))}
          </div>
          <div className="rail-note">
            <Trophy size={17} />
            <p>
              先用 Balatro 打出工具模板，再复制到机制复杂、搜索长尾多的策略游戏。
            </p>
          </div>
        </aside>

        <section className="core-panel" aria-label="种子顾问">
          <div className="panel-header">
            <div>
              <p className="section-label">当前样板游戏：{activeGame.cn}</p>
              <h1>把“钢K流”做成可复用的攻略工具入口</h1>
            </div>
            <div className="signal-stack" aria-label="机会评分">
              <span>搜索热度 {activeGame.volume}</span>
              <strong>{route.confidence}%</strong>
              <small>路线置信度</small>
            </div>
          </div>

          <form className="advisor-form" onSubmit={analyzeSeed}>
            <label>
              种子号
              <input
                value={seed}
                onChange={(event) => setSeed(event.target.value)}
                placeholder="例如 9OUU79"
                spellCheck="false"
              />
            </label>
            <label>
              牌组
              <select value={deck} onChange={(event) => setDeck(event.target.value)}>
                {decks.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              目标流派
              <select
                value={archetype}
                onChange={(event) => setArchetype(event.target.value)}
              >
                {archetypes.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <button className="primary-button analyze" type="submit">
              <Play size={17} />
              分析种子
            </button>
          </form>

          <div className="quick-seeds" aria-label="推荐种子">
            {knownSeeds.map((item) => (
              <button key={item} type="button" onClick={() => useSuggestedSeed(item)}>
                {item}
              </button>
            ))}
          </div>

          <RouteResult route={route} onSave={saveCurrentSeed} />
        </section>

        <aside className="growth-panel" aria-label="增长侧栏">
          <div className="opportunity-card">
            <div className="mini-title">
              <BarChart3 size={17} />
              <span>SEO 机会池</span>
            </div>
            <div className="opportunity-score">
              <strong>42</strong>
              <span>首批可落地页面</span>
            </div>
            <div className="keyword-table">
              {opportunityRows.map(([keyword, gap, strength, pageType]) => (
                <div className="keyword-row" key={keyword}>
                  <strong>{keyword}</strong>
                  <span>{gap}</span>
                  <em>{strength}</em>
                  <small>{pageType}</small>
                </div>
              ))}
            </div>
          </div>

          <div className="lead-card">
            <div className="mini-title">
              <Mail size={17} />
              <span>留资模块</span>
            </div>
            <h2>每周发一份“可打种子 + 路线卡”</h2>
            <p>
              后续可以导流到 Discord、飞书群、Steam 促销页、外设联盟和高级工具订阅。
            </p>
            <form onSubmit={subscribe}>
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="your@email.com"
                type="email"
              />
              <button type="submit">订阅</button>
            </form>
            {subscribed ? <small className="success-text">已记录：下一版接入真实邮件系统。</small> : null}
          </div>

          <div className="saved-card">
            <div className="mini-title">
              <Database size={17} />
              <span>收藏种子</span>
            </div>
            <div className="saved-list">
              {savedSeeds.map((item) => (
                <button key={item} type="button" onClick={() => useSuggestedSeed(item)}>
                  <Copy size={14} />
                  {item}
                </button>
              ))}
            </div>
          </div>
        </aside>
      </main>

      <section className="content-strip" id="构筑">
        <div className="strip-intro">
          <p className="section-label">内容生产线</p>
          <h2>从单游戏攻略，扩展成多游戏工具矩阵</h2>
          <p>
            每个模块都能拆成 SEO 页面、互动工具和社群话题，不靠泛资讯硬卷。
          </p>
        </div>
        <div className="module-grid">
          {contentModules.map((module, index) => (
            <article className="module-card" key={module.title}>
              <img src={module.image} alt="" loading="lazy" />
              <span className="module-index">{String(index + 1).padStart(2, "0")}</span>
              <strong>{module.title}</strong>
              <p>{module.intent}</p>
              <div>
                <span>{module.type}</span>
                <em>{module.pages} 页</em>
                <b>{module.growth}</b>
              </div>
              <a href={module.source} target="_blank" rel="noreferrer">
                来源参考
                <ChevronRight size={14} />
              </a>
            </article>
          ))}
        </div>
      </section>

      <section className="source-strip" id="数据洞察">
        <div>
          <p className="section-label">Agent Reach 搜索来源</p>
          <h2>先把素材和证据库搭起来，再批量做攻略页</h2>
        </div>
        <div className="source-grid">
          {researchSources.map((source) => (
            <a href={source.url} target="_blank" rel="noreferrer" key={source.url}>
              <span>{source.outlet}</span>
              <strong>{source.label}</strong>
              <ChevronRight size={15} />
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}

function RouteResult({ route, onSave }) {
  return (
    <article className="route-result" aria-live="polite">
      <div className="route-titlebar">
        <div>
          <p className="section-label">{route.deck} / {route.archetype}</p>
          <h2>{route.seed} 钢K路线卡</h2>
          <p>{route.summary}</p>
        </div>
        <div className="route-actions">
          <button className="secondary-button" type="button" onClick={onSave}>
            <Copy size={16} />
            收藏种子
          </button>
        </div>
      </div>

      <div className="joker-row">
        {route.jokers.map((joker, index) => (
          <span className="joker-chip" key={joker}>
            {index === 0 ? <Flame size={15} /> : <Gem size={15} />}
            {joker}
          </span>
        ))}
      </div>

      <div className="route-grid">
        {route.stages.map((stage) => (
          <section className="stage-card" key={stage.label}>
            <span>{stage.label}</span>
            <h3>{stage.title}</h3>
            <ul>
              {stage.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <div className="risk-row">
        <div>
          <ShieldAlert size={18} />
          <span>Boss 风险</span>
        </div>
        {route.warnings.map((warning) => (
          <p key={warning}>{warning}</p>
        ))}
      </div>

      <div className="route-footer">
        <div>
          <Layers3 size={17} />
          <span>上线版本应接入真实种子解析器，AI 只负责解释路线。</span>
        </div>
        <a href="#工具">
          查看工具路线
          <ChevronRight size={16} />
        </a>
      </div>
    </article>
  );
}

export default App;
