(() => {
  "use strict";

  const tabs = [
    ["overview", "總覽", "OV"], ["industries", "產業", "IN"],
    ["research", "研究", "RS"], ["company", "公司", "CO"], ["sources", "來源", "SO"],
    ["history", "歷史", "HI"], ["inference", "推演", "SI"],
    ["resolutions", "結算", "RE"], ["calibration", "校準", "CA"]
  ];
  const spine = ["來源原文", "主張", "Quant", "因果驅動", "事件契約", "校準機率", "結算"];
  const state = {
    tab: "overview",
    ticker: "NVDA",
    boardHorizon: "1y",
    activeScenario: "",
    researchView: "themes",
    researchSlice: "cpo-external-laser",
    researchDisplay: "chain",
    researchTicker: "LITE",
    eventSource: null
  };
  const esc = value => String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const pct = value => value == null ? "—" : (Number(value) * 100).toFixed(1) + "%";
  const num = (value, digits) => value == null || Number.isNaN(Number(value))
    ? "—" : Number(value).toLocaleString(undefined, {maximumFractionDigits: digits == null ? 2 : digits});
  const one = selector => document.querySelector(selector);
  const all = selector => Array.from(document.querySelectorAll(selector));

  async function api(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) {
      let detail = response.statusText;
      try { detail = (await response.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    return response.json();
  }

  document.body.className = "nr-app";
  document.body.innerHTML = [
    '<div class="nr-shell">',
    '<header class="nr-mast"><div class="nr-mark">AGENT REACH <span>// NARRATIVE</span></div>',
    '<div class="nr-context">證據先於敘事 · 分布先於目標 · 本機唯讀 Quant</div>',
    '<div class="nr-health"><span id="nr-health-text">啟動中</span><i id="nr-health-lamp" class="nr-lamp"></i></div></header>',
    '<aside class="nr-rail" id="nr-rail" role="tablist" aria-label="敘事推演工作區"></aside><div class="nr-spine" id="nr-spine"></div>',
    '<main class="nr-stage" id="nr-stage" tabindex="-1" role="tabpanel" aria-live="polite"></main>',
    '<aside class="nr-inspector" id="nr-inspector"></aside>',
    '<section class="nr-console"><div class="nr-console-head">LOCAL JOB TRACE <span id="nr-job"></span></div>',
    '<div class="nr-console-log" id="nr-console-log">λ 待命中。未通過校準閘門的局面不顯示點機率。</div></section></div>',
    '<div hidden aria-hidden="true"><div id="overview"></div><div id="lights"></div><div id="nav"></div>',
    '<div id="main"></div><div id="filelist"></div><div id="viewer"></div><div id="deck"></div>',
    '<div id="cons"></div><div id="constitle"></div><div id="jobinfo"></div><div id="conslog"></div></div>'
  ].join("");

  function tag(value, extra) {
    const normalized = String(value || "unknown").toLowerCase().replace(/\s+/g, "_");
    return '<span class="nr-tag ' + normalized + " " + (extra || "") + '">' + esc(value || "UNKNOWN") + "</span>";
  }
  function empty(message) { return '<div class="nr-empty">' + esc(message) + "</div>"; }
  function errorCard(error) { return '<div class="nr-error"><strong>無法完成</strong><br>' + esc(error.message || error) + "</div>"; }
  function heading(eyebrow, title, lede) {
    return '<p class="nr-eyebrow">' + esc(eyebrow) + '</p><h1 class="nr-title">' + esc(title) +
      '</h1><p class="nr-lede">' + esc(lede) + "</p>";
  }
  function tabSpineIndex() {
    return {overview:2, industries:2, research:4, company:3, sources:1, history:3, inference:5, resolutions:6, calibration:6}[state.tab] || 0;
  }
  function drawChrome() {
    one("#nr-rail").innerHTML = tabs.map(item =>
      '<button role="tab" id="nr-tab-' + item[0] + '" class="nr-nav' +
      (state.tab === item[0] ? " active" : "") + '" data-tab="' + item[0] +
      '" aria-selected="' + (state.tab === item[0] ? "true" : "false") + '"><small>' + item[2] + "</small><span>" + item[1] + "</span></button>"
    ).join("");
    one("#nr-spine").innerHTML = spine.map((label, index) =>
      '<div class="nr-node' + (index <= tabSpineIndex() ? " live" : "") + '"><i></i>' + esc(label) + "</div>"
    ).join("");
    one("#nr-stage").setAttribute("aria-labelledby", "nr-tab-" + state.tab);
    all("[data-tab]").forEach(button => button.addEventListener("click", () => {
      state.tab = button.dataset.tab; render();
    }));
  }
  function setInspector(title, html) {
    one("#nr-inspector").innerHTML = "<h2>" + esc(title) + "</h2>" + html;
  }
  function log(message, error) {
    const line = document.createElement("div");
    if (error) line.className = "error";
    line.textContent = message;
    const box = one("#nr-console-log");
    box.appendChild(line); box.scrollTop = box.scrollHeight;
  }
  function followJob(job, label) {
    one("#nr-job").textContent = " · " + job.id + " · " + label;
    log("λ " + label + " → job " + job.id);
    if (state.eventSource) state.eventSource.close();
    const stream = new EventSource("/api/jobs/" + job.id + "/log");
    state.eventSource = stream;
    stream.onmessage = event => {
      try { log(JSON.parse(event.data)); } catch (_) { log(event.data); }
    };
    stream.addEventListener("end", event => {
      const data = JSON.parse(event.data);
      log(data.status === "done" ? "✔ " + label + " 完成" : "✖ " + label + ": " + data.error, data.status !== "done");
      one("#nr-job").textContent = " · " + job.id + " · " + data.status;
      stream.close(); state.eventSource = null; render();
    });
  }

  async function renderOverview() {
    const stage = one("#nr-stage");
    stage.innerHTML = heading("SYSTEM / CURRENT STATE", "先看證據，再談局面。",
      "每個數字都必須沿著證據脊柱走回來源、資料截止日與結算規則。");
    try {
      const rows = await Promise.all([
        api("/api/narrative/status"), api("/api/overview"), api("/api/scenarios"), api("/api/jobs")
      ]);
      const status = rows[0], radar = rows[1], scenarios = rows[2], jobs = rows[3];
      const counts = status.store.counts;
      one("#nr-health-text").textContent = status.quant.available ? "QUANT ONLINE" : "QUANT MISSING";
      one("#nr-health-lamp").className = "nr-lamp " + (status.quant.available ? "ok" : "bad");
      const cards = [].concat(scenarios.scenarios || [], scenarios.actions || []);
      stage.innerHTML += '<div class="nr-grid">' +
        '<article class="nr-card"><p class="nr-eyebrow">EVIDENCE</p><div class="nr-metric">' + num(counts.claims,0) + '</div><p>主張 · ' + num(counts.documents,0) + ' 份原文</p></article>' +
        '<article class="nr-card"><p class="nr-eyebrow">CONTRACTS</p><div class="nr-metric">' + num(counts.event_contracts,0) + '</div><p>可結算事件契約</p></article>' +
        '<article class="nr-card"><p class="nr-eyebrow">CALIBRATION</p><div class="nr-metric">' + num(counts.calibration_snapshots,0) + '</div><p>時間外校準快照</p></article>' +
        '<article class="nr-card wide"><h3>運作邊界</h3><dl class="nr-kv"><dt>Quant</dt><dd>' + esc(status.quant.root) + ' · read-only</dd>' +
        '<dt>機率閘門</dt><dd>90% Brier skill CI 下界 &gt; 0；區間寬度 ≤ 40pp</dd><dt>LLM</dt><dd>不得生成 KPI 機率</dd>' +
        '<dt>交易</dt><dd>orders_generated = false</dd></dl></article>' +
        '<article class="nr-card"><h3>今日 Radar</h3><p>' + (radar.latest_digest ? "最近更新 " + esc(radar.generated_at || "時間未知") : "尚無 digest") +
        '</p><button class="nr-button" id="nr-collect">手動更新 Radar</button></article></div>' +
        '<section class="nr-section"><div class="nr-section-head"><h2>既有管線</h2><span>保留 Radar 能力</span></div><div class="nr-grid">' +
        cards.map(item => '<article class="nr-card"><h3>' + esc(item.label) + '</h3><p>' + esc(item.desc) + '</p>' +
          ((item.missing || []).length ? '<div class="nr-warning">缺少 ' + esc(item.missing.join(", ")) + "</div>" : "") +
          '<button class="nr-button secondary nr-run-scenario" data-id="' + esc(item.id) + '"' + (item.ready === false ? " disabled" : "") + '>執行</button></article>'
        ).join("") + "</div></section>" +
        '<section class="nr-section"><div class="nr-section-head"><h2>最近工作</h2><span>' + jobs.length + ' 筆</span></div>' +
        (jobs.length ? '<div class="nr-table-wrap"><table class="nr-table"><thead><tr><th>工作</th><th>狀態</th><th>建立</th></tr></thead><tbody>' +
          jobs.slice(0,10).map(job => '<tr><td>' + esc(job.kind) + "<br><small>" + esc(job.id) + "</small></td><td>" + tag(job.status) +
          "</td><td>" + esc(job.created) + "</td></tr>").join("") + "</tbody></table></div>" : empty("還沒有背景工作。")) + "</section>";
      one("#nr-collect").addEventListener("click", async () => {
        try { followJob(await api("/api/collect", {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify({platforms:[]})}), "Radar 收集"); }
        catch (error) { log(error.message, true); }
      });
      all(".nr-run-scenario").forEach(button => button.addEventListener("click", async () => {
        try { followJob(await api("/api/run", {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify({scenario:button.dataset.id,params:{}})}), button.dataset.id); }
        catch (error) { log(error.message, true); }
      }));
      setInspector("現在可相信什麼", '<div class="' + (status.quant.available ? "nr-good" : "nr-error") + '">' +
        (status.quant.available ? "Quant 路徑可讀。" : "Quant 路徑不存在。") + '</div><hr class="nr-inspector-rule">' +
        "<p>" + tag("KNOWN") + " 可追溯證據</p><p>" + tag("COMPUTED") + " 資料計算</p><p>" + tag("GUESS") + " 待驗證</p>");
    } catch (error) { stage.innerHTML += errorCard(error); }
  }

  async function renderIndustries() {
  function evidenceLabel(row) {
    return esc(row.artifact || row.metric || row.url || row.source_id || row.kind || "unnamed");
  }
  function hotspotMarkup(claim) {
    const evidence = Array.isArray(claim.evidence) ? claim.evidence : [];
    const changeData = evidence.filter(row => row && (row.kind === "quant" || row.kind === "official"));
    const counter = evidence.filter(row => row && (row.stance === "counter" || row.contradicts === true));
    const source = claim.source_id || claim.source_url || "UNKNOWN";
    const cutoff = claim.as_of || claim.published_at || claim.observed_at || "UNKNOWN";
    return '<li>' + tag(claim.tag) + ' <strong>催化劑／主張</strong> ' + esc(claim.text) +
      '<small>變化數據 · ' + (changeData.length ? changeData.map(evidenceLabel).join(" · ") : "未附可驗證數據") + '</small>' +
      '<small>反證 · ' + (counter.length ? counter.map(evidenceLabel).join(" · ") : "未提供") + '</small>' +
      '<small>截止 · ' + esc(cutoff) + '　來源 · ' + esc(source) + '</small></li>';
  }
  function quantSummary(value) {
    const rows = Object.entries(value || {}).filter(([, item]) =>
      item == null || ["string", "number", "boolean"].includes(typeof item));
    return rows.slice(0, 4).map(([key, item]) => esc(key) + "=" + esc(item)).join(" · ") || "無可顯示欄位";
  }

    const stage = one("#nr-stage");
    stage.innerHTML = heading("INDUSTRY / HOTSPOTS", "熱點不是新聞數量，是可驗證的變化。",
      "只顯示 Quant 輪動資料與人工核准的主張；日期或來源不明就保留空白。");
    try {
      const data = await api("/api/narrative/dashboard");
      const sectors = [].concat(data.sectors, [data.macro, data.crypto]);
      stage.innerHTML += '<div class="nr-grid">' + sectors.map(sector =>
        '<article class="nr-card"><p class="nr-eyebrow">' + esc(sector.id) + '</p><h3>' + esc(sector.name) + "</h3><p>" +
        (sector.quant_available ? tag("COMPUTED") : tag("NO QUANT", "risk")) + " " +
        ((sector.hotspots || []).length ? tag((sector.hotspots || []).length + " HOTSPOTS") : "") + '</p><p><small>變化數據 · ' + quantSummary(sector.quant) + '</small></p><ul class="nr-list">' +
        ((sector.hotspots || []).slice(0,4).map(hotspotMarkup).join("") || "<li><small>等待人工核准來源。</small></li>") +
        "</ul></article>").join("") + "</div>";
      setInspector("資料時點", '<dl class="nr-kv"><dt>輪動 as-of</dt><dd>' + esc(data.as_of || "UNKNOWN") +
        '</dd><dt>證據更新</dt><dd>' + esc(data.evidence_updated_at || "尚無") + "</dd></dl>" +
        ((data.rotation_artifact.issues || []).length ? '<hr class="nr-inspector-rule"><div class="nr-warning">' +
          esc(data.rotation_artifact.issues.join(" · ")) + "</div>" : ""));
    } catch (error) { stage.innerHTML += errorCard(error); }
  }

  function companyMarkup(data) {
    const prices = data.quant.prices || {}, cards = data.decision_cards || [];
    const robust = data.robust_opportunities || [];
    const robustMarkup = '<section class="nr-section"><div class="nr-section-head"><h2>跨局面穩健機會</h2><span>只計入已校準且 p ≥ 50%</span></div>' +
      (robust.length ? '<div class="nr-grid">' + robust.map(row => '<article class="nr-card"><h3>' + esc(row.ticker) +
        '</h3><div class="nr-metric">' + num(row.robustness_score, 3) + '</div><p>' + row.scenario_count +
        ' 個局面 · 最低下界 ' + pct(row.min_lower_bound) + '</p></article>').join("") + '</div>' :
        empty("尚無跨局面、通過閘門的受益標的。")) + '</section>';
    return '<div class="nr-grid"><article class="nr-card"><p class="nr-eyebrow">LAST CLOSE</p><div class="nr-metric">' + num(prices.last_close) +
      "</div><p>" + esc(prices.as_of || "UNKNOWN") + '</p></article><article class="nr-card"><p class="nr-eyebrow">21D RETURN</p><div class="nr-metric">' +
      pct((prices.returns || {})["21d"]) + "</div><p>" + tag("COMPUTED") + '</p></article><article class="nr-card"><p class="nr-eyebrow">EVIDENCE GRADE</p><div class="nr-metric">' +
      esc(data.quant.evidence_grade || "—") + "</div><p>" + data.quant.issues.length + " 個資料警告</p></article></div>" + robustMarkup +
      '<section class="nr-section"><div class="nr-section-head"><h2>局面與決策卡</h2><span>可重疊，不加總 100%</span></div>' +
      (cards.length ? '<div class="nr-grid">' + cards.map(card => '<article class="nr-card wide"><p>' + tag(card.probability_status) +
        "</p><h3>" + esc(card.event) + '</h3><div class="nr-metric">' + (card.probability_status === "calibrated" ? pct(card.probability) : "資料不足") +
        "</div>" + (card.interval ? "<p>90% interval " + pct(card.interval[0]) + " — " + pct(card.interval[1]) + "</p>" : "") +
        '<dl class="nr-kv"><dt>期限</dt><dd>' + esc(card.horizon) + "</dd><dt>結算</dt><dd>" + esc(card.invalidation.resolution_date) +
        "</dd><dt>驗證支持</dt><dd>" + card.opportunity.verified_support.length + "</dd><dt>Quant 警告</dt><dd>" +
        card.risk.quant_issues.length + "</dd></dl></article>").join("") + "</div>" : empty("尚未建立事件契約。到「推演」定義局面。")) + "</section>" +
      '<section class="nr-section"><div class="nr-section-head"><h2>證據</h2><span>' + data.claims.length + " 項</span></div>" +
      (data.claims.length ? data.claims.map(claim => '<div class="nr-evidence">' + tag(claim.tag) + "<p>" + esc(claim.text) +
        "<small>" + esc(claim.verification_state) + " · " + esc(claim.observed_at) + "</small></p></div>").join("") : empty("尚無人工匯入主張。")) + "</section>";
  }

  async function loadCompany(ticker) {
    state.ticker = ticker.toUpperCase();
    try {
      const data = await api("/api/narrative/company/" + encodeURIComponent(state.ticker));
      one("#nr-company-result").innerHTML = companyMarkup(data);
      setInspector(state.ticker + " / 資料稽核", (data.quant.issues || []).length ?
        '<ul class="nr-list">' + data.quant.issues.slice(0,12).map(issue => "<li>" + esc(issue) + "</li>").join("") + "</ul>" :
        '<div class="nr-good">未偵測到資料契約警告。</div>');
    } catch (error) { one("#nr-company-result").innerHTML = errorCard(error); }
  }
  async function renderCompany() {
    const stage = one("#nr-stage");
    stage.innerHTML = heading("COMPANY / DOSSIER", "公司不是一條線，是一組等待結算的事件。",
      "價格、基本面、因子、驗證 artifact 與來源觀點在同一頁對時。") +
      '<form id="nr-company-form" class="nr-form-row"><label><span class="nr-label">Ticker</span><input class="nr-input" id="nr-ticker" value="' +
      esc(state.ticker) + '"></label><div class="nr-actions"><button class="nr-button" type="submit">載入 dossier</button></div></form><div id="nr-company-result"></div>';
    one("#nr-company-form").addEventListener("submit", event => { event.preventDefault(); loadCompany(one("#nr-ticker").value.trim() || "NVDA"); });
    loadCompany(state.ticker);
  }

  const researchViews = [
    ["themes", "Themes"], ["company", "Company"], ["briefs", "Briefs"],
    ["reports", "Reports"], ["watchlist", "Watchlist"], ["live", "Live"],
    ["monitor", "Monitor"]
  ];
  function researchWatchlist() {
    try { return JSON.parse(localStorage.getItem("serenity-research-watchlist") || "[]"); }
    catch (_) { return []; }
  }
  function saveResearchWatchlist(rows) {
    localStorage.setItem("serenity-research-watchlist", JSON.stringify(Array.from(new Set(rows))));
  }
  function researchNav() {
    return '<div class="nr-research-nav" role="navigation" aria-label="研究工作區">' +
      researchViews.map(row => '<button type="button" class="nr-research-navitem' +
        (state.researchView === row[0] ? " active" : "") + '" data-research-view="' + row[0] +
        '">' + row[1] + '</button>').join("") + '</div><div id="nr-research-body"></div>';
  }
  function researchGrade(value) {
    return '<span class="nr-grade grade-' + esc(String(value || "E").toLowerCase()) + '">' +
      esc(value || "E") + '</span>';
  }
  function researchChain(payload) {
    const nodes = ((payload.graph || {}).nodes || []);
    return '<div class="nr-chain" aria-label="價值鏈">' + nodes.map((node, index) =>
      '<article class="nr-chain-node"><small>' + esc(node.node_type) + '</small><strong>' +
      esc(node.label) + '</strong><p>' + tag(node.tag) + ' ' + esc(node.confidence) + '</p>' +
      '<div>' + (((node.metadata || {}).tickers || []).map(ticker =>
        '<button type="button" class="nr-chip nr-company-jump" data-ticker="' + esc(ticker) + '">' +
        esc(ticker) + '</button>').join("") || '<span class="nr-muted">system node</span>') + '</div></article>' +
      (index < nodes.length - 1 ? '<i class="nr-chain-arrow" aria-hidden="true">→</i>' : "")
    ).join("") + '</div>';
  }
  function researchGraph(payload) {
    const graph = payload.graph || {}, nodes = graph.nodes || [], edges = graph.edges || [];
    const byId = Object.fromEntries(nodes.map(node => [node.id, node]));
    return '<div class="nr-graph-flow">' + edges.map(edge => {
      const source = byId[edge.source_node_id] || {}, target = byId[edge.target_node_id] || {};
      const evidence = edge.evidence || [];
      return '<article class="nr-edge state-' + esc(edge.state) + '"><div class="nr-edge-route"><strong>' +
        esc(source.label || "UNKNOWN") + '</strong><span><i></i>' + esc(edge.edge_type) + '</span><strong>' +
        esc(target.label || "UNKNOWN") + '</strong></div><div class="nr-edge-meta">' + tag(edge.tag) +
        tag(edge.state) + '<span>支持 ' + evidence.filter(row => row.stance === "support").length +
        ' · 反駁 ' + evidence.filter(row => row.stance === "refute").length + '</span></div></article>';
    }).join("") + (edges.length ? "" : empty("尚無 typed edges。")) + '</div>';
  }
  function researchScenario(payload) {
    const bottleneck = payload.bottleneck_contract || {};
    return '<div class="nr-research-scenario"><article class="nr-card wide"><p class="nr-eyebrow">BOTTLENECK CONTRACT</p>' +
      '<h3>' + esc(bottleneck.title || payload.scarce_layer) + '</h3><p>' + tag(bottleneck.status || "candidate") +
      '</p><dl class="nr-kv"><dt>量測</dt><dd>' + esc((payload.measurement_contract || {}).supply || "未定義") +
      '</dd><dt>需求負載</dt><dd>' + esc((payload.measurement_contract || {}).load || "未定義") +
      '</dd><dt>解除門檻</dt><dd>' + esc(JSON.stringify(bottleneck.easing_threshold || {})) +
      '</dd><dt>結算</dt><dd>' + esc(bottleneck.resolution_date || "UNKNOWN") + '</dd></dl></article>' +
      '<article class="nr-card"><p class="nr-eyebrow">FAILURE CONDITIONS</p><ul class="nr-list">' +
      (payload.failure_conditions || []).map(row => '<li>' + esc(row) + '</li>').join("") +
      '</ul></article><article class="nr-card"><p class="nr-eyebrow">NEXT MOVE</p><p>' +
      esc(payload.next_move || "尚未定義") + '</p><div class="nr-warning">未通過關係／局面校準時不顯示數字機率。</div></article></div>';
  }
  function researchPackMarkup(pack, diff) {
    const payload = pack.payload || {}, coverage = payload.coverage || {};
    const display = state.researchDisplay === "graph" ? researchGraph(payload) :
      state.researchDisplay === "scenario" ? researchScenario(payload) : researchChain(payload);
    const companyCards = (payload.companies || []).map(company => {
      const computed = (company.valuation_snapshots || []).find(row => row.status === "computed_metric_range");
      return '<article class="nr-card"><p class="nr-eyebrow">' + esc(company.value_chain_role) + '</p><h3>' +
        esc(company.ticker) + '</h3><p>' + esc(company.value_capture) + '</p><dl class="nr-kv"><dt>TradingView</dt><dd>' +
        esc((((company.demand_evidence || {}).tradingview || {}).status) || "missing") + '</dd><dt>Finviz</dt><dd>' +
        esc((((company.demand_evidence || {}).finviz || {}).status) || "missing") + '</dd><dt>估值分歧</dt><dd>' +
        (computed ? esc((computed.assumptions || {}).metric) + ' ' + num(computed.low) + '–' + num(computed.high) : "資料不足") +
        '</dd></dl><button type="button" class="nr-button secondary nr-company-jump" data-ticker="' +
        esc(company.ticker) + '">公司卡</button></article>';
    }).join("");
    return '<section class="nr-research-hero"><div><p class="nr-eyebrow">RESEARCHPACK V' + esc(pack.version) +
      ' / ' + esc(payload.as_of) + '</p><h2>' + esc(payload.title || payload.slice) + '</h2><p>' +
      esc(payload.system_change) + '</p></div><dl><dt>證據</dt><dd>' + researchGrade(payload.evidence_grade) +
      '</dd><dt>稀缺層</dt><dd>' + esc(payload.scarce_layer) + '</dd><dt>Hash</dt><dd><code>' +
      esc(String(pack.content_hash || "").slice(0, 12)) + '</code></dd></dl></section>' +
      '<div class="nr-view-switch" role="group" aria-label="研究包視圖"><button type="button" data-research-display="chain" class="' +
      (state.researchDisplay === "chain" ? "active" : "") + '">Chain</button><button data-research-display="graph" class="' +
      (state.researchDisplay === "graph" ? "active" : "") + '" type="button">Graph</button><button type="button" data-research-display="scenario" class="' +
      (state.researchDisplay === "scenario" ? "active" : "") + '">Scenario</button></div>' + display +
      '<section class="nr-section"><div class="nr-section-head"><h2>公司研究卡</h2><span>' +
      (payload.companies || []).length + ' 家</span></div><div class="nr-grid">' + companyCards + '</div></section>' +
      '<section class="nr-dual-brief"><div><h2>政策曝險</h2>' + boardList(payload.policy_exposure, "尚無") +
      '</div><div><h2>版本差異</h2>' + ((diff || {}).changes || []).slice(0, 8).map(row =>
        '<div class="nr-brief-row"><strong>' + esc(row.kind) + '</strong><p>' + esc(row.field || JSON.stringify(row.value || "")) +
        '</p></div>').join("") + (((diff || {}).changes || []).length ? "" : empty("內容與前版相同或尚無前版。")) +
      '</div></section><section class="nr-section"><div class="nr-section-head"><h2>Coverage</h2><span>零不等於沒有貼文</span></div>' +
      '<pre>' + esc(JSON.stringify(coverage, null, 2)) + '</pre></section>';
  }

  async function renderResearchThemes() {
    const box = one("#nr-research-body");
    const data = await api("/api/narrative/research/themes");
    const selected = data.themes.find(row => row.id === state.researchSlice) || data.themes[0];
    if (selected) state.researchSlice = selected.id;
    box.innerHTML = '<section class="nr-research-theme-strip">' + data.themes.map(theme =>
      '<button type="button" data-research-slice="' + esc(theme.id) + '" class="' +
      (theme.id === state.researchSlice ? "active" : "") + '"><small>PHASE ' + esc(theme.phase) +
      '</small><strong>' + esc(theme.title) + '</strong><span>' + researchGrade((theme.latest_pack || {}).evidence_grade || "E") +
      '</span></button>').join("") + '</section><div class="nr-actions"><button class="nr-button" id="nr-run-research">重建此切片</button>' +
      '<button class="nr-button secondary" id="nr-weekly-freeze">凍結全部週報</button><button class="nr-button secondary" id="nr-serenity-backfill">回補 Serenity 90 天</button></div>' +
      '<div id="nr-research-pack"></div>';
    all("[data-research-slice]").forEach(button => button.addEventListener("click", () => {
      state.researchSlice = button.dataset.researchSlice; renderResearchThemes();
    }));
    one("#nr-run-research").addEventListener("click", async () => {
      try { followJob(await api("/api/narrative/research/runs", {method:"POST",headers:{"content-type":"application/json"},
        body:JSON.stringify({slice:state.researchSlice})}), "研究 " + state.researchSlice); }
      catch (error) { log(error.message, true); }
    });
    one("#nr-weekly-freeze").addEventListener("click", async () => {
      try { followJob(await api("/api/narrative/research/weekly-freeze", {method:"POST",headers:{"content-type":"application/json"},body:"{}"}), "weekly-freeze"); }
      catch (error) { log(error.message, true); }
    });
    one("#nr-serenity-backfill").addEventListener("click", async () => {
      try { followJob(await api("/api/narrative/research/serenity-backfill", {method:"POST",headers:{"content-type":"application/json"},
        body:JSON.stringify({days:90,count:2000})}), "Serenity backfill"); }
      catch (error) { log(error.message, true); }
    });
    if (!selected || !selected.latest_pack) {
      one("#nr-research-pack").innerHTML = empty("此切片尚未建立 ResearchPack。執行後才會讀取 Quant 並凍結證據快照。");
      setInspector("Blueprint", '<div class="nr-warning">' + tag("FRAME") + ' 靜態切片不是證據。</div>');
      return;
    }
    const pack = await api("/api/narrative/research/packs/" + encodeURIComponent(selected.latest_pack.id));
    const diff = await api("/api/narrative/research/packs/" + encodeURIComponent(pack.id) + "/diff");
    one("#nr-research-pack").innerHTML = researchPackMarkup(pack, diff);
    bindResearchPackLinks(pack, diff);
    setInspector("證據狀態流", '<dl class="nr-kv"><dt>proposed</dt><dd>藍圖／假設</dd><dt>supported</dt><dd>已有證據但不足驗證</dd>' +
      '<dt>verified</dt><dd>A/B 證據</dd><dt>refuted</dt><dd>反證成立</dd><dt>expired</dt><dd>超過有效期</dd></dl>');
  }
  function bindResearchPackLinks(pack, diff) {
    all("[data-research-display]").forEach(button => button.addEventListener("click", () => {
      state.researchDisplay = button.dataset.researchDisplay;
      one("#nr-research-pack").innerHTML = researchPackMarkup(pack, diff);
      bindResearchPackLinks(pack, diff);
    }));
    all(".nr-company-jump").forEach(button => button.addEventListener("click", () => {
      state.researchTicker = button.dataset.ticker;
      state.researchView = "company";
      renderResearch();
    }));
  }

  async function renderResearchCompany() {
    const box = one("#nr-research-body");
    box.innerHTML = '<form class="nr-form-row" id="nr-research-company-form"><label><span class="nr-label">Ticker</span>' +
      '<input class="nr-input" id="nr-research-ticker" value="' + esc(state.researchTicker) + '"></label>' +
      '<button class="nr-button" type="submit">載入研究卡</button></form><div id="nr-research-company-card"></div>';
    async function load(ticker) {
      state.researchTicker = String(ticker || "LITE").toUpperCase();
      const data = await api("/api/narrative/research/companies/" + encodeURIComponent(state.researchTicker));
      const watch = researchWatchlist(), watching = watch.includes(state.researchTicker);
      const cards = data.research_cards || [];
      one("#nr-research-company-card").innerHTML = '<section class="nr-research-hero"><div><p class="nr-eyebrow">COMPANY RESEARCH CARD</p><h2>' +
        esc(data.ticker) + '</h2><p>TradingView ' + esc((data.quant.coverage || {}).tradingview) + ' · Finviz ' +
        esc((data.quant.coverage || {}).finviz) + '</p></div><button class="nr-button secondary" id="nr-watch-toggle">' +
        (watching ? "移出 Watchlist" : "加入 Watchlist") + '</button></section>' +
        (cards.length ? cards.map(card => '<article class="nr-card full"><p class="nr-eyebrow">' + esc(card.value_chain_role) +
          '</p><h3>' + esc(card.constrains) + '</h3><dl class="nr-kv"><dt>價值捕獲</dt><dd>' + esc(card.value_capture) +
          '</dd><dt>替代性</dt><dd>' + esc(card.substitutability) + '</dd><dt>擴產</dt><dd>' + esc(card.capacity_lead_time) +
          '</dd><dt>認證</dt><dd>' + esc(card.qualification_lead_time) + '</dd></dl><h4>Watch metrics</h4>' +
          boardList(card.watch_metrics, "尚無") + '<h4>Failure conditions</h4>' + boardList(card.failure_conditions, "尚無") +
          '<div class="nr-valuation-row">' + (card.valuation_snapshots || []).map(row => '<div><small>' + esc(row.method) +
            '</small><strong>' + (row.status === "computed_metric_range" ? num(row.low) + '–' + num(row.high) : "資料不足") +
            '</strong><span>' + esc(row.status) + '</span></div>').join("") + '</div></article>').join("") :
          empty("尚無包含此公司的 ResearchPack。")) +
        '<section class="nr-section"><div class="nr-section-head"><h2>關係契約</h2><span>未校準不顯示 p_relation</span></div>' +
        ((data.relationships.contracts || []).map(row => '<div class="nr-evidence">' + tag("event_contract") + '<p>' +
          esc(row.statement) + '<small>' + esc(row.resolution_date) + '</small></p></div>').join("") ||
          empty("尚未建立具名官方揭露的關係契約。")) + '</section>';
      one("#nr-watch-toggle").addEventListener("click", () => {
        const current = researchWatchlist();
        saveResearchWatchlist(current.includes(state.researchTicker) ?
          current.filter(row => row !== state.researchTicker) : current.concat([state.researchTicker]));
        load(state.researchTicker);
      });
      setInspector(data.ticker + " / Coverage", (data.quant.issues || []).length ?
        '<ul class="nr-list">' + data.quant.issues.map(row => '<li>' + esc(row) + '</li>').join("") + '</ul>' :
        '<div class="nr-good">PIT adapters 未回報問題。</div>');
    }
    one("#nr-research-company-form").addEventListener("submit", event => {
      event.preventDefault(); load(one("#nr-research-ticker").value.trim() || "LITE");
    });
    await load(state.researchTicker);
  }

  async function renderResearchBriefs() {
    const data = await api("/api/narrative/research/packs?limit=100");
    const latest = {};
    (data.packs || []).forEach(pack => { if (!latest[pack.slice]) latest[pack.slice] = pack; });
    one("#nr-research-body").innerHTML = '<div class="nr-grid">' + Object.values(latest).map(pack => {
      const payload = pack.payload || {};
      return '<article class="nr-card wide"><p class="nr-eyebrow">' + esc(pack.slice) + ' · V' + pack.version +
        '</p><h3>' + esc(payload.scarce_layer) + '</h3><p>' + esc(payload.next_move) + '</p><h4>最強失效條件</h4><p>' +
        esc((payload.failure_conditions || ["未定義"])[0]) + '</p><div>' + researchGrade(payload.evidence_grade) +
        tag((payload.bottleneck_contract || {}).status || "candidate") + '</div></article>';
    }).join("") + (Object.keys(latest).length ? "" : empty("尚無 Briefs；先建立研究切片。")) + '</div>';
    setInspector("Brief 規則", "<p>每個 Brief 只摘要凍結 pack；不從即時 LLM 回覆建立證據。</p>");
  }

  async function renderResearchReports() {
    const data = await api("/api/narrative/research/packs?limit=200");
    one("#nr-research-body").innerHTML = (data.packs || []).length ?
      '<div class="nr-table-wrap"><table class="nr-table"><thead><tr><th>Pack</th><th>切片</th><th>As-of</th><th>Grade</th><th>Hash</th></tr></thead><tbody>' +
      data.packs.map(pack => '<tr><td>V' + pack.version + '<br><small>' + esc(pack.id) + '</small></td><td>' + esc(pack.slice) +
        '</td><td>' + esc(pack.as_of) + '</td><td>' + researchGrade(pack.evidence_grade) + '</td><td><code>' +
        esc(String(pack.content_hash).slice(0, 12)) + '</code></td></tr>').join("") + '</tbody></table></div>' :
      empty("尚無凍結報告。");
    setInspector("不可變週報", "<p>同一 content contract 只產生一個 hash；版本差異由 pack diff 重建。</p>");
  }

  async function renderResearchWatchlist() {
    const watch = researchWatchlist();
    one("#nr-research-body").innerHTML = '<form class="nr-form-row" id="nr-watch-add"><label><span class="nr-label">Ticker</span>' +
      '<input class="nr-input" id="nr-watch-input" placeholder="LITE"></label><button class="nr-button" type="submit">加入</button></form>' +
      '<div class="nr-grid">' + watch.map(ticker => '<article class="nr-card"><h3>' + esc(ticker) + '</h3>' +
        '<button class="nr-button secondary nr-watch-open" data-ticker="' + esc(ticker) + '">打開公司卡</button>' +
        '<button class="nr-text-button nr-watch-remove" data-ticker="' + esc(ticker) + '">移除</button></article>').join("") +
      (watch.length ? "" : empty("Watchlist 只保存 UI 偏好，不代表持倉。")) + '</div>';
    one("#nr-watch-add").addEventListener("submit", event => {
      event.preventDefault();
      const ticker = one("#nr-watch-input").value.trim().toUpperCase();
      if (ticker) { saveResearchWatchlist(watch.concat([ticker])); renderResearchWatchlist(); }
    });
    all(".nr-watch-open").forEach(button => button.addEventListener("click", () => {
      state.researchTicker = button.dataset.ticker; state.researchView = "company"; renderResearch();
    }));
    all(".nr-watch-remove").forEach(button => button.addEventListener("click", () => {
      saveResearchWatchlist(watch.filter(row => row !== button.dataset.ticker)); renderResearchWatchlist();
    }));
    setInspector("Watchlist", "<p>本機 UI 偏好；不建立部位、方向或下單。</p>");
  }

  async function renderResearchLive() {
    const data = await api("/api/narrative/research/live?limit=100");
    one("#nr-research-body").innerHTML = (data.events || []).length ?
      '<div class="nr-table-wrap"><table class="nr-table"><thead><tr><th>時間</th><th>切片</th><th>變化</th><th>內容</th></tr></thead><tbody>' +
      data.events.map(row => '<tr><td>' + esc(row.at) + '</td><td>' + esc(row.slice) + '</td><td>' +
        tag(row.kind) + '</td><td><code>' + esc(JSON.stringify(row.change)) + '</code></td></tr>').join("") +
      '</tbody></table></div>' : empty("尚無 snapshot 差異事件。");
    setInspector("Deterministic Live", "<p>只比較兩個凍結 PIT pack；不顯示手寫新聞事件。</p>");
  }

  async function renderResearchMonitor() {
    const data = await api("/api/narrative/research/monitor");
    const coverage = data.coverage || {};
    one("#nr-research-body").innerHTML = '<div class="nr-grid"><article class="nr-card"><p class="nr-eyebrow">RUNS</p><div class="nr-metric">' +
      num((data.runs || []).length, 0) + '</div></article><article class="nr-card"><p class="nr-eyebrow">PACKS</p><div class="nr-metric">' +
      num((data.packs || []).length, 0) + '</div></article><article class="nr-card"><p class="nr-eyebrow">SERENITY POSTS</p><div class="nr-metric">' +
      num((coverage.totals || {}).retrieved, 0) + '</div><p>' + (coverage.complete ? tag("complete") : tag("coverage_degraded", "risk")) +
      '</p></article></div><section class="nr-section"><div class="nr-section-head"><h2>最近 runs</h2><span>append-only</span></div>' +
      '<div class="nr-table-wrap"><table class="nr-table"><thead><tr><th>Slice</th><th>As-of</th><th>Status</th><th>Run</th></tr></thead><tbody>' +
      (data.runs || []).map(row => '<tr><td>' + esc(row.slice) + '</td><td>' + esc(row.as_of) + '</td><td>' + tag(row.status) +
        '</td><td><small>' + esc(row.id) + '</small></td></tr>').join("") + '</tbody></table></div></section>' +
      '<section class="nr-section"><div class="nr-section-head"><h2>Coverage ledger</h2><span>zero means unknown</span></div><pre>' +
      esc(JSON.stringify(coverage, null, 2)) + '</pre></section>';
    setInspector("守門", '<dl class="nr-kv"><dt>LLM 寫證據</dt><dd>false</dd><dt>LLM 寫機率</dt><dd>false</dd>' +
      '<dt>下單</dt><dd>false</dd><dt>Quant</dt><dd>read-only</dd></dl>');
  }

  async function renderResearch() {
    const stage = one("#nr-stage");
    stage.innerHTML = heading("RESEARCH / EVIDENCE GRAPH", "稀缺不是標籤，是一份會失效的契約。",
      "從 Serenity 原文、官方申報與 PIT Quant 建立可重建的產業研究包。") + researchNav();
    all("[data-research-view]").forEach(button => button.addEventListener("click", () => {
      state.researchView = button.dataset.researchView; renderResearch();
    }));
    const renderers = {
      themes: renderResearchThemes,
      company: renderResearchCompany,
      briefs: renderResearchBriefs,
      reports: renderResearchReports,
      watchlist: renderResearchWatchlist,
      live: renderResearchLive,
      monitor: renderResearchMonitor
    };
    try { await renderers[state.researchView](); }
    catch (error) { one("#nr-research-body").innerHTML = errorCard(error); log(error.message || error, true); }
  }

  async function renderSources() {
    const stage = one("#nr-stage");
    stage.innerHTML = heading("SOURCES / TRACK RECORD", "名氣不是權重，結算紀錄才是。",
      "同一作者按領域與期限分開計分；樣本少時向中性收縮，利益衝突不會被刪除。");
    try {
      const data = await api("/api/narrative/sources");
      stage.innerHTML += '<div class="nr-table-wrap"><table class="nr-table"><thead><tr><th>來源</th><th>領域</th><th>衝突</th><th>備註</th></tr></thead><tbody>' +
        data.sources.map(source => "<tr><td>" + esc(source.display_name) + "<br><small>" + esc(source.id) + "</small></td><td>" +
          (source.domains || []).map(value => tag(value)).join("") + "</td><td>" +
          ((source.conflict_flags || []).map(value => tag(value, "risk")).join("") || "—") + "</td><td>" + esc(source.notes) + "</td></tr>"
        ).join("") + '</tbody></table></div><section class="nr-section"><div class="nr-section-head"><h2>已結算實績</h2><span>domain + horizon</span></div>' +
        (data.track_record.length ? '<div class="nr-table-wrap"><table class="nr-table"><thead><tr><th>來源</th><th>有效樣本</th><th>Brier skill</th><th>收縮權重</th></tr></thead><tbody>' +
          data.track_record.map(row => "<tr><td>" + esc(row.display_name) + "</td><td>" + num(row.effective_n) + "</td><td>" + num(row.brier_skill,3) +
          "</td><td>" + num(row.weight,3) + "</td></tr>").join("") + "</tbody></table></div>" : empty("尚無足夠已結算預測。")) + "</section>";
      setInspector("身份分離", '<div class="nr-good">Serenity 與黃靖哲是兩個獨立來源。</div><hr class="nr-inspector-rule"><p>加密來源的交易所聯盟利益會直接顯示。</p>');
    } catch (error) { stage.innerHTML += errorCard(error); }
  }

  async function renderHistory() {
    const stage = one("#nr-stage");
    stage.innerHTML = heading("HISTORY / ANALOGS", "歷史可以教結構，不能偷帶答案。",
      "事後因果圖只用於提出問題；只有事件發生前已可觀測的特徵能進模型。");
    try {
      const data = await api("/api/narrative/history");
      stage.innerHTML += '<div class="nr-timeline">' + data.episodes.map(episode =>
        '<article class="nr-episode"><time>' + esc(episode.start_at) + " — " + esc(episode.end_at) + "</time><h3>" + esc(episode.title) +
        "</h3><p>" + (episode.archetypes || []).map(value => tag(value)).join("") + "</p><p>" +
        (episode.post_hoc ? tag("INFERRED, post-hoc", "guess") : tag("PIT ELIGIBLE")) + "</p></article>"
      ).join("") + "</div>";
      setInspector("訓練邊界", '<div class="nr-warning">' + esc(data.training_rule) + '</div><hr class="nr-inspector-rule"><p>Quant ledger: ' +
        esc(data.quant_regime_ledger.freshness) + "</p>");
    } catch (error) { stage.innerHTML += errorCard(error); }
  }

  function renderPendingClaims(claims) {
    const box = one("#nr-pending-claims");
    if (!box) return;
    box.innerHTML = claims.length ? claims.map(claim =>
      '<div class="nr-evidence">' + tag(claim.tag) + "<div><p>" + esc(claim.text) + "<small>" + esc(claim.source_id || "unknown source") +
      " · " + esc(claim.domain || "unclassified") + '</small></p><div class="nr-actions"><button class="nr-button secondary nr-claim-keep" data-id="' +
      claim.id + '">保留為假設</button><button class="nr-button danger nr-claim-reject" data-id="' + claim.id + '">拒絕</button></div></div></div>'
    ).join("") : empty("沒有待審主張。");
    all(".nr-claim-keep").forEach(button => button.addEventListener("click", () => reviewClaim(button.dataset.id, "reviewed_hypothesis")));
    all(".nr-claim-reject").forEach(button => button.addEventListener("click", () => reviewClaim(button.dataset.id, "rejected")));
  }
  async function loadPendingClaims() {
    const box = one("#nr-pending-claims");
    if (!box) return;
    try {
      const data = await api("/api/narrative/claims?state=pending&limit=100");
      renderPendingClaims(data.claims);
    } catch (error) { box.innerHTML = errorCard(error); }
  }
  async function reviewClaim(id, verificationState) {
    try {
      await api("/api/narrative/claims/" + id + "/review", {method:"POST", headers:{"content-type":"application/json"},
        body:JSON.stringify({verification_state:verificationState, tag:verificationState === "rejected" ? "GUESS" : "INFERRED",
          confidence:"LOW", reviewer:"local-user", reason:"manual " + verificationState, evidence:[]})});
      log("✔ 主張 " + id + " → " + verificationState); loadPendingClaims();
    } catch (error) { log(error.message, true); }
  }

  function boardValue(row) {
    if (row.value == null || Number.isNaN(Number(row.value))) return "—";
    if (row.format === "percent") return pct(row.value);
    if (row.format === "number") return num(row.value, 2);
    return num(row.value, 1);
  }

  function boardList(items, fallback) {
    return (items || []).length
      ? '<ul class="nr-list">' + items.map(item => "<li>" + esc(item) + "</li>").join("") + "</ul>"
      : '<p class="nr-muted-copy">' + esc(fallback) + "</p>";
  }

  function scenarioProbability(scenario) {
    if (scenario.probability_status === "calibrated") {
      return '<span class="nr-scenario-prob">' + pct(scenario.probability) + "</span>";
    }
    return '<span class="nr-scenario-prob insufficient">資料不足</span>';
  }

  function scenarioDetail(scenario) {
    return '<article class="nr-scenario-detail" data-active-scenario-detail>' +
      '<header><div><p class="nr-eyebrow">ACTIVE EVENT / ' + esc(scenario.horizon) + '</p><h3>' +
      esc(scenario.name) + '</h3></div><div class="nr-scenario-status">' + tag(scenario.probability_status) +
      scenarioProbability(scenario) + '</div></header><p class="nr-event-contract">' + esc(scenario.event) +
      '</p><p class="nr-scenario-copy">' + esc(scenario.narrative) + '</p><div class="nr-logic-grid">' +
      '<section><p class="nr-eyebrow">驅動</p>' + boardList(scenario.drivers, "尚無通過覆核的驅動。") + '</section>' +
      '<section><p class="nr-eyebrow risk">反證</p>' + boardList(scenario.counterevidence, "尚無反方證據。") + '</section>' +
      '<section><p class="nr-eyebrow">失效條件</p>' + boardList(scenario.invalidators, "尚未定義失效條件。") + '</section>' +
      '<section><p class="nr-eyebrow">事件契約</p><dl class="nr-kv"><dt>結算日</dt><dd>' +
      esc(scenario.resolution_date) + '</dd><dt>來源</dt><dd>' + esc(scenario.origin) +
      '</dd><dt>機率</dt><dd>' + esc(scenario.gate_reason) + '</dd></dl></section></div>' +
      '<div class="nr-outcomes"><div><span>受益</span>' + (scenario.beneficiaries || []).map(value =>
        '<b class="nr-chip opportunity">' + esc(value) + '</b>').join("") + '</div><div><span>受害</span>' +
      (scenario.victims || []).map(value => '<b class="nr-chip risk">' + esc(value) + '</b>').join("") +
      '</div></div></article>';
  }

  function boardMarkup(data) {
    const scenarios = data.scenarios || [];
    const active = scenarios.find(row => row.id === state.activeScenario) || scenarios[0];
    state.activeScenario = active ? active.id : "";
    const metricCards = (data.evidence || []).map(row =>
      '<article class="nr-tape-cell"><p>' + tag(row.tag) + esc(row.label) + '</p><strong>' + boardValue(row) +
      '</strong><small>' + esc(row.as_of) + ' · ' + esc(row.freshness) + '</small></article>'
    ).join("");
    const scenarioTabs = scenarios.map((scenario, index) =>
      '<button class="nr-scenario-tab' + (scenario.id === state.activeScenario ? " active" : "") +
      '" type="button" data-scenario-id="' + esc(scenario.id) + '" aria-pressed="' +
      (scenario.id === state.activeScenario ? "true" : "false") + '"><small>S' + String(index + 1).padStart(2, "0") +
      ' · ' + esc(scenario.horizon) + '</small><span>' + esc(scenario.name) + '</span>' +
      scenarioProbability(scenario) + '</button>'
    ).join("");
    const opportunityCards = (data.opportunities || []).map(row =>
      '<article class="nr-brief-row"><div>' + tag(row.support) + '<strong>' + esc(row.title) +
      '</strong></div><p>' + esc(row.why) + '</p></article>'
    ).join("");
    const riskCards = (data.risks || []).map(row =>
      '<article class="nr-brief-row risk"><div>' + tag(row.support, "risk") + '<strong>' + esc(row.title) +
      '</strong></div><p>' + esc(row.why) + '</p></article>'
    ).join("");
    return '<section class="nr-board-hero"><div><p class="nr-eyebrow">LIVE RESEARCH BOARD / ' +
      esc(data.as_of) + '</p><h2>' + esc(data.title) + '</h2><p>' + esc(data.regime.summary) +
      '</p><p>' + esc(data.regime.interpretation) + '</p></div><dl class="nr-board-meta"><dt>體制</dt><dd>' +
      esc(data.regime.label) + '</dd><dt>期限</dt><dd>' + esc(data.horizon) + '</dd><dt>結算日</dt><dd>' +
      esc(data.resolution_date) + '</dd><dt>證據等級</dt><dd>' + esc(data.calibration.status) +
      '</dd></dl></section><section class="nr-analogue"><div><p class="nr-eyebrow">此刻最像</p><h3>' +
      esc(data.analogue.name) + '</h3><p>' + esc(data.analogue.rhyme) + '</p></div><div><p class="nr-eyebrow">這次不一樣</p><p>' +
      esc(data.analogue.difference) + '</p></div></section><section class="nr-evidence-tape" aria-label="Quant 證據帶">' +
      metricCards + '</section><section class="nr-section"><div class="nr-section-head"><h2>可能局面</h2>' +
      '<span>可重疊，不強制加總 100%</span></div><div class="nr-scenario-rail" role="list">' + scenarioTabs +
      '</div><div id="nr-scenario-detail">' + (active ? scenarioDetail(active) : empty("沒有可顯示的局面。")) +
      '</div></section><section class="nr-dual-brief"><div><h2>機會</h2>' + opportunityCards +
      '</div><div><h2>風險</h2>' + riskCards + '</div></section><section class="nr-section nr-source-ledger">' +
      '<div class="nr-section-head"><h2>來源如何被使用</h2><span>原文 → 主張 → Quant → 契約</span></div>' +
      (data.source_synthesis || []).map(row => '<div><strong>' + esc(row.source) + '</strong><p>' +
        esc(row.use) + '</p></div>').join("") + '</section>';
  }

  function bindScenarioBoard(data) {
    all("[data-scenario-id]").forEach(button => button.addEventListener("click", () => {
      state.activeScenario = button.dataset.scenarioId;
      all("[data-scenario-id]").forEach(row => {
        const active = row.dataset.scenarioId === state.activeScenario;
        row.classList.toggle("active", active);
        row.setAttribute("aria-pressed", active ? "true" : "false");
      });
      const selected = (data.scenarios || []).find(row => row.id === state.activeScenario);
      if (selected) one("#nr-scenario-detail").innerHTML = scenarioDetail(selected);
    }));
  }

  async function loadScenarioBoard(ticker, horizon) {
    const box = one("#nr-board-result");
    if (!box) return;
    box.innerHTML = '<div class="nr-board-loading">正在對齊 Quant 截止日、歷史韻腳與事件契約…</div>';
    try {
      const data = await api("/api/narrative/board/" + encodeURIComponent(ticker) + "?horizon=" + encodeURIComponent(horizon));
      state.ticker = data.ticker;
      state.boardHorizon = data.horizon;
      state.activeScenario = "";
      box.innerHTML = boardMarkup(data);
      bindScenarioBoard(data);
      setInspector(data.ticker + " / 發布閘門", '<div class="nr-warning">' + esc(data.calibration.reason) +
        '</div><hr class="nr-inspector-rule"><dl class="nr-kv"><dt>成熟樣本</dt><dd>' +
        num(data.calibration.matured_forward_evaluations, 0) + ' / ' +
        num(data.calibration.minimum_forward_evaluations, 0) + '</dd><dt>規則</dt><dd>' +
        esc(data.calibration.rule) + '</dd><dt>下單</dt><dd>orders_generated = false</dd></dl>');
    } catch (error) {
      box.innerHTML = errorCard(error);
      log(error.message || error, true);
    }
  }

  async function renderInference() {
    const stage = one("#nr-stage");
    stage.innerHTML = heading("SIMULATION / RESULTS", "先看局面，再打開工作台。",
      "當前 Quant、歷史韻腳、支持／反證與失效條件在同一張盤；沒有通過校準就不顯示數字機率。") +
      '<form class="nr-board-controls" id="nr-board-form"><label><span class="nr-label">Ticker</span>' +
      '<input class="nr-input" id="nr-board-ticker" value="' + esc(state.ticker) + '"></label>' +
      '<label><span class="nr-label">視野</span><select class="nr-select" id="nr-board-horizon">' +
      ["quarter", "1y", "3y", "5y"].map(value => '<option' + (value === state.boardHorizon ? " selected" : "") + '>' + value + '</option>').join("") +
      '</select></label><button class="nr-button" type="submit">重新推演</button></form><div id="nr-board-result"></div>' +
      '<details class="nr-workbench" id="nr-workbench"><summary>打開證據匯入、事件契約與校準工具</summary><div class="nr-workbench-body">' +
      '<div class="nr-grid"><form class="nr-card wide" id="nr-import-form"><p class="nr-eyebrow">01 / IMPORT</p><h3>人工匯入原文</h3>' +
      '<div class="nr-form-row"><label><span class="nr-label">URL</span><input class="nr-input" id="nr-import-url" placeholder="https://..."></label>' +
      '<label><span class="nr-label">Domain</span><input class="nr-input" id="nr-import-domain" placeholder="semiconductors"></label>' +
      '<label><span class="nr-label">Ticker</span><input class="nr-input" id="nr-import-ticker" value="' + esc(state.ticker) + '"></label></div>' +
      '<label><span class="nr-label">或貼文字</span><textarea class="nr-textarea" id="nr-import-text"></textarea></label>' +
      '<label><span class="nr-label">或選檔案</span><input class="nr-input" id="nr-import-file" type="file"></label>' +
      '<button class="nr-button" type="submit">匯入並抽取待審主張</button></form>' +
      '<form class="nr-card" id="nr-discovery-form"><p class="nr-eyebrow">02 / DISCOVER</p><h3>手動探索相似來源</h3>' +
      '<label><span class="nr-label">Query</span><input class="nr-input" id="nr-discovery-query"></label>' +
      '<label><span class="nr-label">Domain</span><input class="nr-input" id="nr-discovery-domain"></label>' +
      '<button class="nr-button secondary" type="submit">搜尋待審候選</button></form></div>' +
      '<section class="nr-section"><div class="nr-section-head"><h2>待審主張</h2><span>GUESS 上限 LOW</span></div><div id="nr-pending-claims"></div></section>' +
      '<section class="nr-section"><div class="nr-section-head"><h2>事件契約</h2><span>二元、可重疊、可結算</span></div>' +
      '<form class="nr-card full" id="nr-contract-form"><div class="nr-form-row"><label><span class="nr-label">Scope</span><select class="nr-select" id="nr-scope-type"><option>ticker</option><option>sector</option><option>macro</option><option>crypto</option></select></label>' +
      '<label><span class="nr-label">Scope ID</span><input class="nr-input" id="nr-scope-id" value="NVDA"></label>' +
      '<label><span class="nr-label">Horizon</span><select class="nr-select" id="nr-horizon"><option>quarter</option><option selected>1y</option><option>3y</option><option>5y</option></select></label></div>' +
      '<label><span class="nr-label">事件敘述</span><input class="nr-input" id="nr-statement"></label><div class="nr-form-row">' +
      '<label><span class="nr-label">Resolution date</span><input class="nr-input" id="nr-resolution-date" type="date"></label>' +
      '<label><span class="nr-label">Resolution source</span><select class="nr-select" id="nr-resolution-source"><option value="quant_prices">Quant prices</option><option value="manual_official">Manual official data</option></select></label>' +
      '<label><span class="nr-label">Domain</span><input class="nr-input" id="nr-contract-domain" value="semiconductors"></label>' +
      '<label><span class="nr-label">Criteria JSON</span><input class="nr-input" id="nr-criteria" value=\'{"operator":"return_gte","threshold":0.2,"start_date":"2026-08-24"}\'></label></div>' +
      '<button class="nr-button" type="submit">建立事件契約</button></form></section>' +
      '<section class="nr-section"><div class="nr-section-head"><h2>校準推演</h2><span>samples 必須 point-in-time</span></div>' +
      '<form class="nr-card full" id="nr-forecast-form"><div class="nr-form-row"><label><span class="nr-label">Contract ID</span><input class="nr-input" id="nr-forecast-contract"></label>' +
      '<label><span class="nr-label">As-of</span><input class="nr-input" id="nr-forecast-asof" type="date"></label></div>' +
      '<label><span class="nr-label">Historical samples JSON</span><textarea class="nr-textarea" id="nr-samples">[]</textarea></label>' +
      '<button class="nr-button" type="submit">執行 walk-forward 校準</button></form></section></div></details>';
    one("#nr-board-form").addEventListener("submit", event => {
      event.preventDefault();
      const ticker = one("#nr-board-ticker").value.trim() || "NVDA";
      const horizon = one("#nr-board-horizon").value;
      loadScenarioBoard(ticker, horizon);
    });
    await Promise.all([loadPendingClaims(), loadScenarioBoard(state.ticker, state.boardHorizon)]);
    one("#nr-import-form").addEventListener("submit", async event => {
      event.preventDefault();
      const file = one("#nr-import-file").files[0];
      try {
        let result;
        if (file) {
          const path = "/api/narrative/imports/file?filename=" + encodeURIComponent(file.name) + "&domain=" +
            encodeURIComponent(one("#nr-import-domain").value) + "&ticker=" + encodeURIComponent(one("#nr-import-ticker").value);
          result = await api(path, {method:"POST", body:file});
        } else {
          result = await api("/api/narrative/imports", {method:"POST", headers:{"content-type":"application/json"},
            body:JSON.stringify({url:one("#nr-import-url").value.trim(), text:one("#nr-import-text").value,
              domain:one("#nr-import-domain").value.trim(), ticker:one("#nr-import-ticker").value.trim()})});
        }
        log("✔ 匯入 " + result.document.id + " · " + result.claims.length + " 個待審主張");
        await loadPendingClaims();
        if (result.claims.length && !one(".nr-claim-keep"))
          renderPendingClaims(result.claims);
      } catch (error) { log(error.message, true); }
    });
    one("#nr-discovery-form").addEventListener("submit", async event => {
      event.preventDefault();
      try { followJob(await api("/api/narrative/discovery", {method:"POST", headers:{"content-type":"application/json"},
        body:JSON.stringify({query:one("#nr-discovery-query").value,domain:one("#nr-discovery-domain").value})}), "來源探索"); }
      catch (error) { log(error.message, true); }
    });
    one("#nr-contract-form").addEventListener("submit", async event => {
      event.preventDefault();
      try {
        const result = await api("/api/narrative/contracts", {method:"POST", headers:{"content-type":"application/json"},
          body:JSON.stringify({scope_type:one("#nr-scope-type").value,scope_id:one("#nr-scope-id").value,
            domain:one("#nr-contract-domain").value,horizon:one("#nr-horizon").value,statement:one("#nr-statement").value,
            resolution_date:one("#nr-resolution-date").value,criteria:JSON.parse(one("#nr-criteria").value),
            resolution_source:one("#nr-resolution-source").value,
            source_ids:[],parent_archetypes:[],dependency_ids:[]})});
        one("#nr-forecast-contract").value = result.id; log("✔ 建立事件契約 " + result.id);
      } catch (error) { log(error.message, true); }
    });
    one("#nr-forecast-form").addEventListener("submit", async event => {
      event.preventDefault();
      try { followJob(await api("/api/narrative/forecasts", {method:"POST",headers:{"content-type":"application/json"},
        body:JSON.stringify({contract_id:one("#nr-forecast-contract").value,as_of:one("#nr-forecast-asof").value,
          samples:JSON.parse(one("#nr-samples").value)})}), "局面校準"); }
      catch (error) { log(error.message, true); }
    });
  }

  async function renderResolutions() {
    const stage = one("#nr-stage");
    stage.innerHTML = heading("RESOLUTION / LEDGER", "不改寫過去，只追加更正。",
      "自動結算保留原始判定；人工覆核另存理由、操作者與時間。");
    try {
      const rows = await Promise.all([api("/api/narrative/contracts"), api("/api/narrative/resolutions")]);
      const contracts = rows[0].contracts, resolutions = rows[1].resolutions;
      stage.innerHTML += '<div class="nr-table-wrap"><table class="nr-table"><thead><tr><th>契約</th><th>期限</th><th>結算日</th><th>動作</th></tr></thead><tbody>' +
        contracts.map(contract => "<tr><td>" + esc(contract.statement) + "<br><small>" + esc(contract.id) + "</small></td><td>" +
          esc(contract.horizon) + "</td><td>" + esc(contract.resolution_date) + '</td><td><button class="nr-button secondary nr-auto-resolve" data-id="' +
          contract.id + '">自動結算</button></td></tr>').join("") + '</tbody></table></div><section class="nr-section"><div class="nr-section-head"><h2>追加式帳本</h2><span>' +
          resolutions.length + " 筆</span></div>" + (resolutions.length ? resolutions.map(row => '<div class="nr-evidence">' + tag(row.kind) +
          "<p>outcome=" + esc(row.outcome) + " · " + esc(row.reason) + "<small>" + esc(row.actor) + " · " + esc(row.created_at) +
          "</small></p></div>").join("") : empty("尚無已結算事件。")) + "</section>";
      all(".nr-auto-resolve").forEach(button => button.addEventListener("click", async () => {
        try {
          const result = await api("/api/narrative/resolutions", {method:"POST",headers:{"content-type":"application/json"},
            body:JSON.stringify({contract_id:button.dataset.id,kind:"auto"})});
          log("✔ 結算 " + result.resolution.id); renderResolutions();
        } catch (error) { log(error.message, true); }
      }));
      setInspector("有效結果", "<p>最新人工覆核優先；若無人工覆核，採最新自動結算。</p>");
    } catch (error) { stage.innerHTML += errorCard(error); }
  }

  async function renderCalibration() {
    const stage = one("#nr-stage");
    stage.innerHTML = heading("CALIBRATION / RELIABILITY", "機率要接受結算，不接受文采。",
      "Brier skill、bootstrap 區間、正負控制與時間外樣本共同決定能否發布數字。") +
      '<form id="nr-calibration-form" class="nr-form-row"><label><span class="nr-label">Domain</span><input class="nr-input" id="nr-cal-domain" value="semiconductors"></label>' +
      '<label><span class="nr-label">Horizon</span><select class="nr-select" id="nr-cal-horizon"><option>quarter</option><option selected>1y</option><option>3y</option><option>5y</option></select></label>' +
      '<button class="nr-button" type="submit">重算校準</button></form><div id="nr-calibration-list"></div>';
    async function load() {
      try {
        const data = await api("/api/narrative/calibration");
        one("#nr-calibration-list").innerHTML = data.snapshots.length ? '<div class="nr-grid">' + data.snapshots.map(row => {
          const metrics = row.metrics || {};
          return '<article class="nr-card"><p>' + tag(row.eligible ? "calibrated" : "insufficient_data") + "</p><h3>" +
            esc(row.domain || "all") + " / " + esc(row.horizon) + '</h3><div class="nr-metric">' + num(metrics.brier_skill,3) +
            "</div><p>Brier skill · " + esc(row.as_of) + "</p></article>";
        }).join("") + "</div>" : empty("尚無校準快照。");
      } catch (error) { one("#nr-calibration-list").innerHTML = errorCard(error); }
    }
    one("#nr-calibration-form").addEventListener("submit", async event => {
      event.preventDefault();
      try { followJob(await api("/api/narrative/calibration", {method:"POST",headers:{"content-type":"application/json"},
        body:JSON.stringify({domain:one("#nr-cal-domain").value,horizon:one("#nr-cal-horizon").value})}), "校準回放"); }
      catch (error) { log(error.message, true); }
    });
    load();
    setInspector("平衡統計閘門", '<dl class="nr-kv"><dt>Skill CI</dt><dd>90% 下界 &gt; 0</dd><dt>機率區間</dt><dd>總寬 ≤ 40pp</dd><dt>控制</dt><dd>positive pass / negative near baseline</dd></dl>');
  }

  async function render() {
    drawChrome();
    const renderers = {overview:renderOverview,industries:renderIndustries,research:renderResearch,company:renderCompany,
      sources:renderSources,history:renderHistory,inference:renderInference,
      resolutions:renderResolutions,calibration:renderCalibration};
    try { await renderers[state.tab](); }
    catch (error) { one("#nr-stage").innerHTML = errorCard(error); log(error.message || error, true); }
    one("#nr-stage").focus({preventScroll:true});
  }

  document.addEventListener("keydown", event => {
    if (event.altKey && /^[1-9]$/.test(event.key)) {
      state.tab = tabs[Number(event.key) - 1][0]; render();
    }
  });
  render();
})();
