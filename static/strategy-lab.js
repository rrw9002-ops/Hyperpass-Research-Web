"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const host = $("workspace-tradingview");
  if (!host || !$("chart-form") || !$("tv-code")) return;
  const api = (route, body) => window.HyperpassApp.api(route, body === undefined ? {} : {method:"POST",body});
  const node = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text != null) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  const message = (id, text, error = false) => {
    $(id).textContent = text;
    $(id).classList.toggle("error-text", error);
  };
  const setBusy = async (button, feedback, action) => {
    button.disabled = true;
    try { await action(); } catch (error) { message(feedback, error.message, true); }
    finally { button.disabled = false; }
  };
  const rules = {
    trend_breakout: {title:"추세 돌파", source:"강의 기반 예제 · docs/CHART-LAB.md", detail:s =>
      "종가 > SMA " + s.fast_period + " > SMA " + s.slow_period + "이고 종가가 직전 " + s.breakout_period + "봉 최고가를 넘으면 진입합니다. 종가가 단기 SMA를 하향 돌파하면 청산합니다."},
    mean_reversion: {title:"평균 회귀", source:"강의 기반 예제 · docs/CHART-LAB.md", detail:s =>
      "종가가 볼린저 하단(" + s.bb_period + "봉, " + s.bb_std + "배) 아래이고 RSI(" + s.rsi_period + ")가 " + s.rsi_entry + " 미만이면 진입합니다. 종가가 볼린저 중심선을 상향 돌파하면 청산합니다."},
    sma_cross: {title:"이동평균 교차", source:"앱 내장 추가 예제 · hyperpass/chart_lab.py", detail:s =>
      "SMA " + s.fast_period + "이 SMA " + s.slow_period + "을 상향 돌파하면 진입하고 하향 돌파하면 청산합니다."}
  };
  const modeNames = {market:"시장 전체", single:"단일 종목", custom:"종목 묶음", pine:"TradingView · Pine"};
  const kindNames = {market:"포트폴리오",chart:"단일 차트",pine:"Pine 코드"};
  const statuses = {queued:"대기",running:"진행 중",completed:"완료",failed:"실패",cancelled:"취소",interrupted:"중단",partial:"부분 완료"};
  const running = job => job && ["queued","running"].includes(job.status);
  const defaults = {
    strategy:"trend_breakout", fast_period:20, slow_period:60, breakout_period:20, bb_period:20,
    bb_std:2, rsi_period:14, rsi_entry:30, initial_capital:100000000, fee_bps:5, slippage_bps:5
  };
  const numericField = {
    fast_period:["단기 SMA (봉)",2,299,1],slow_period:["장기 SMA (봉)",3,300,1],
    breakout_period:["돌파 기준 (봉)",2,300,1], bb_period:["볼린저 기간 (봉)",2,300,1],
    bb_std:["볼린저 표준편차 배수",0.1,10,"any"],rsi_period:["RSI 기간 (봉)",2,300,1],
    rsi_entry:["RSI 진입 기준",1,49,"any"],initial_capital:["초기 자본",1,1e15,"any"],
    fee_bps:["편도 수수료 (bp)",0,1000,"any"],slippage_bps:["편도 슬리피지 (bp)",0,1000,"any"]
  };
  let engine = "pine", mode = "single", records = [], currentJob = null, pollTimer = null, requestVersion = 0;
  let resultJob = null, pineRun = null, initialLoad = false, strategyLoad = 0, historyLoad = 0;
  let historyRows = [], pendingRequest = false, retainedSettings = {};
  const money = value => Number.isFinite(value) ? value.toLocaleString("ko-KR",{maximumFractionDigits:2}) : "—";
  const pct = value => Number.isFinite(value) ? money(value) + "%" : "—";
  const localDate = date => [date.getFullYear(),String(date.getMonth()+1).padStart(2,"0"),String(date.getDate()).padStart(2,"0")].join("-");
  const currency = market => market === "KR" ? "KRW" : "USD";
  const labelOf = job => job.name || job.request?.name || rules[job.request?.settings?.strategy]?.title || "전략 검증";
  const recordOption = record => new Option(record.name + " · " + (kindNames[record.kind] || record.kind),record.id);

  const pinePane = node("div");
  pinePane.id = "studio-pine";
  while (host.firstChild) pinePane.append(host.firstChild);
  const heading = pinePane.querySelector(".workspace-heading");
  heading.querySelector("h1").textContent = "TradingView Desktop";
  heading.querySelector(".eyebrow")?.remove();
  const panel = node("div");
  panel.id = "strategy-studio";
  panel.innerHTML = `
    <div class="workspace-heading"><div><span class="eyebrow">STRATEGY RESEARCH</span><h1>백테스트 연구실</h1>
    <p>Pine 전략 파일을 불러오거나 코드를 붙여넣고 원하는 투자 대상에서 성과를 확인하세요.</p></div></div>
    <div class="bt-engine-picker"><label for="bt-engine" class="field-label">검증 방식</label><select id="bt-engine">
      <option value="pine">TradingView · Pine 전략</option><option value="portfolio">포트폴리오 · 조건 전략</option></select></div>
    <div id="bt-library" class="panel studio-library" hidden><div><label for="bt-saved" class="field-label">내 전략</label>
    <select id="bt-saved"><option value="">저장한 전략 선택</option></select></div>
    <button type="button" class="button ghost" id="bt-load">불러오기</button><p class="feedback" id="bt-library-feedback" role="status"></p></div>
    <section class="panel studio-settings bt-target-panel" id="bt-target-panel"><h2>투자 대상</h2>
          <div class="bt-target-row"><div><label class="field-label" for="bt-scope">검증 범위</label>
          <select id="bt-scope"><option value="single">단일 종목</option><option value="custom">종목 묶음</option><option value="market">시장 전체</option></select></div><div>
            <label class="field-label" for="bt-market">국가 · 기준 통화</label>
            <select id="bt-market"><option value="KR">국내 · KRW</option><option value="US">미국 · USD</option></select></div></div>
            <div id="bt-single-field" hidden><label class="field-label" for="bt-symbol">종목명 또는 티커</label>
              <input id="bt-symbol" maxlength="100" placeholder="예: 삼성전자 또는 005930" autocomplete="off" aria-describedby="bt-symbol-status">
              <div id="bt-symbol-matches" class="tv-symbol-matches"></div><p id="bt-symbol-status" class="cost-note" role="status"></p></div>
            <div id="bt-custom-field" hidden><label class="field-label" for="bt-symbols">검증할 종목</label>
              <textarea id="bt-symbols" rows="3" placeholder="삼성전자, SK하이닉스, 현대차"></textarea>
              <p class="cost-note">종목명이나 티커를 쉼표 또는 줄바꿈으로 구분하세요.</p></div>
            <p id="bt-universe" class="cost-note"></p>
            <div id="bt-universe-options"></div></section>
    <div id="studio-local" class="studio-grid">
      <form id="bt-form" class="portfolio-form">
        <div class="portfolio-columns">
          <section class="panel studio-settings bt-setup"><h2>기간과 자금</h2>
            <button type="button" class="button ghost compact bt-example-load" id="bt-example-load">국내 PER 실습 불러오기</button>
            <div id="bt-example-info" class="cost-note" hidden></div>
            <div class="field-pair"><div><label class="field-label" for="bt-start">시작일</label><input id="bt-start" type="date" required></div>
              <div><label class="field-label" for="bt-end">종료일</label><input id="bt-end" type="date" required></div></div>
            <h3>운용 자금과 비용</h3>
            <div id="bt-costs" class="studio-fields"></div><p class="cost-note">수수료와 슬리피지는 매수·매도에 각각 적용합니다. 1bp = 0.01%.</p>
            <div id="bt-schedule"></div>
            <div id="bt-sizing"><label class="field-label" for="bt-positions">최대 보유 종목 수</label>
              <input type="number" id="bt-positions" min="1" max="100" step="1" value="10" required></div>
          </section>
          <section class="panel studio-settings bt-selection">
            <h2>종목 선정과 매매 규칙</h2>
            <div id="bt-condition-rules"></div>
            <div id="bt-technical-fields"><label class="field-label" for="bt-rule">기술 신호</label><select id="bt-rule"></select>
              <div class="studio-rule"><p id="bt-rule-copy"></p><small id="bt-rule-source"></small></div>
              <details class="studio-params"><summary>기술 신호 계산 기준</summary><div id="bt-params" class="studio-fields"></div></details></div>
            <div class="field-pair"><div id="bt-legacy-ranking" hidden><label class="field-label" for="bt-ranking">후보 순위</label>
              <select id="bt-ranking"><option value="momentum_high">최근 수익률 높은 순</option><option value="momentum_low">최근 수익률 낮은 순</option></select></div>
              <div id="bt-lookback-field"><label class="field-label" for="bt-lookback">모멘텀 산정 기간 (거래일)</label>
              <input type="number" id="bt-lookback" min="2" max="252" step="1" value="20" required></div></div>
            <div id="bt-fundamental-data"></div>
            <div id="bt-code-editor"></div>
          </section>
        </div>
        <section class="panel studio-settings bt-execution"><div class="bt-name-block"><label class="field-label" for="bt-name">전략 이름</label><input id="bt-name" required maxlength="120"></div>
          <div class="studio-actions">
            <button type="button" class="button ghost" id="bt-save">내 전략에 추가</button>
            <button type="button" class="button ghost" id="bt-preview">실행 조건 확인</button>
            <button type="submit" class="button primary" id="bt-run" disabled>백테스트 실행</button>
          </div><p id="bt-preview-summary" class="portfolio-summary" hidden></p>
          <p class="feedback" id="bt-feedback" role="status"></p>
        </section>
      </form>
      <div class="studio-output">
        <section class="panel studio-result"><div class="studio-result-head"><h2 id="bt-result-title">검증 결과</h2>
          <span id="bt-status" class="workspace-state">실행 전</span></div>
          <p id="bt-job-message" role="status" class="studio-summary">실행하면 비용 차감 수익률, 최대 낙폭과 실제 가상 거래 내역을 확인할 수 있습니다.</p>
          <progress id="bt-progress" max="100" value="0" hidden></progress>
          <div class="studio-actions"><button type="button" class="button ghost compact" id="bt-cancel" hidden>실행 취소</button>
            <button type="button" class="button ghost compact" id="bt-retry" hidden>상태 다시 확인</button></div>
          <div id="bt-result" hidden><div class="studio-metrics" id="bt-metrics"></div>
            <div id="bt-curves" class="studio-curves"><div><h3>누적 자산</h3><canvas id="bt-equity-plot" aria-label="시간순 누적 자산"></canvas></div>
              <div><h3>고점 대비 낙폭</h3><canvas id="bt-dd-plot" aria-label="시간순 고점 대비 낙폭"></canvas></div></div>
            <p class="cost-note" id="bt-equity-range"></p>
            <div id="bt-orders-block" hidden><h3>매매 신호와 체결</h3><div id="bt-orders"></div></div>
            <h3>완결 거래</h3><div id="bt-trades"></div>
            <h3>마지막 날 보유 종목</h3><div id="bt-holdings"></div>
            <details class="studio-details" open><summary>데이터 범위와 해석 조건</summary><p id="bt-coverage"></p>
              <ul id="bt-warnings"></ul><details id="bt-exclusions"><summary>제외 종목과 사유</summary><div id="bt-excluded-list"></div></details></details>
            <div class="studio-actions"><button type="button" class="button ghost compact" id="bt-save-tested">이 실행의 전략 저장</button>
              <button type="button" class="button ghost compact" id="bt-download">전체 결과 JSON ↓</button></div>
            <p id="bt-result-feedback" class="feedback" role="status"></p></div>
        </section>
        <section class="panel studio-history"><div class="studio-result-head"><h2>실행 기록</h2><button id="bt-history-refresh" type="button" class="text-button">새로고침</button></div>
          <p id="bt-history-feedback" class="feedback" role="status"></p><div id="bt-history"></div></section>
      </div>
    </div>`;
  host.append(panel,pinePane);
  const sharedOutput=panel.querySelector(".studio-output");
  host.append(sharedOutput);
  // The shared scope controls specify the instrument. The old single-chart results remain reopenable.
  pinePane.querySelector(".tv-chart-controls").hidden=true;
  pinePane.querySelector(".tv-workbench").classList.add("bt-pine-workbench");
  const legacyLog=node("details",null,"bt-disclosure bt-legacy-history");
  legacyLog.innerHTML="<summary>이전 버전의 TradingView 단일 차트 기록</summary>";
  for(const item of pinePane.querySelectorAll(".tv-job-panel,.tv-history-panel"))legacyLog.append(item);
  pinePane.append(legacyLog);
  pinePane.querySelector(".tv-pine-footer").hidden=true;
  $("tv-backtest").hidden=true;
  pinePane.querySelector(".workspace-heading h1").textContent="Pine 전략 실행";
  pinePane.querySelector(".workspace-heading p").textContent="각 종목의 TradingView Strategy Tester 보고서를 개별 확인합니다.";
  $("tv-pine-title").textContent="전략 코드";
  pinePane.querySelector(".tv-pine-panel label[for='tv-code-file']").textContent="전략 파일 불러오기 ↑";
  window.HyperpassSymbols.attach("bt-symbol","bt-symbol");
  const pineActions = node("div",null,"studio-pine-save");
  pineActions.innerHTML = `<div class="bt-target-row"><div><label class="field-label" for="bt-pine-name">전략 이름</label><input id="bt-pine-name" maxlength="120" value="내 Pine 전략"></div><div id="bt-pine-period"></div></div>
    <div class="studio-actions"><button type="button" id="bt-pine-preview" class="button ghost">실행 조건 확인</button>
    <button type="button" id="bt-pine-run" class="button primary" disabled>Pine 백테스트 실행</button></div>
    <p id="bt-pine-preview-summary" class="portfolio-summary" hidden></p>
    <p id="bt-pine-feedback" class="feedback" role="status"></p>`;
  $("tv-code").after(pineActions);
  $("bt-pine-period").append(pinePane.querySelector("label[for='tv-timeframe']"),$("tv-timeframe"));
  window.HyperpassPortfolioConditions.pineTemplate({api,message,setBusy,rules,defaults});
  const chartActions = node("div",null,"studio-chart-tools");
  chartActions.innerHTML = `<p class="cost-note" id="bt-chart-source"></p><label class="field-label" for="bt-chart-saved">내 전략으로 이 종목 검증</label>
    <select id="bt-chart-saved"><option value="">저장한 전략 선택</option></select>
    <button type="button" class="button ghost compact" id="bt-chart-apply">선택한 전략으로 검증</button>
    <button type="button" class="text-button" id="bt-chart-compare" hidden>포트폴리오 엔진으로 단일 종목 비교 ↗</button>
    <details class="studio-details"><summary>현재 차트 전략 저장</summary>
      <label class="field-label" for="bt-chart-name">전략 이름</label><input id="bt-chart-name" maxlength="120" placeholder="예: 내 일봉 돌파 전략">
      <button type="button" class="button ghost compact" id="bt-chart-save">내 전략에 추가</button></details>
    <p id="bt-chart-feedback" class="feedback" role="status"></p>`;
  $("chart-rule").after(chartActions);

  for (const [key,rule] of Object.entries(rules)) $("bt-rule").add(new Option(rule.title,key));
  for (const [key,[label,min,max,step]] of Object.entries(numericField)) {
    const box = node("div"), title = node("label",label,"field-label"), input = node("input");
    input.id = "bt-param-"+key; input.type = "number"; input.min = min; input.max = max; input.step = step;
    input.required = true; input.value = defaults[key]; title.htmlFor = input.id;
    box.dataset.setting = key; box.append(title,input);
    ($(key === "initial_capital" || key === "fee_bps" || key === "slippage_bps" ? "bt-costs" : "bt-params")).append(box);
  }
  const today = new Date(); today.setDate(today.getDate()-1);
  const start = new Date(today);
  start.setFullYear(start.getFullYear()-1);
  $("bt-start").value = localDate(start); $("bt-end").value = localDate(today);
  $("bt-name").value = "모멘텀 순위 전략";
  let revision = 0, previewed = null;
  function invalidate() {
    revision++; previewed = null;
    $("bt-run").disabled = true; $("bt-pine-run").disabled=true;
    $("bt-pine-preview-summary").hidden=true;
    $("bt-preview-summary").hidden = true;
  }
  const conditions = window.HyperpassPortfolioConditions.mount({api, invalidate, message, labelMode:next=>modeNames[next]});

  function settings() {
    const values = {...retainedSettings,strategy:$("bt-rule").value,start_date:$("bt-start").value,end_date:$("bt-end").value};
    for (const key of Object.keys(numericField)) values[key] = Number($("bt-param-"+key).value);
    return values;
  }
  function sourceLinks(host, rule) {
    host.replaceChildren();
    if (!rule) return;
    host.append(document.createTextNode(rule.source + " · "));
    const base = "https://github.com/rrw9002-ops/Hyperpass-Research-Web/blob/v0.6.1-preview/";
    for (const [label,path] of [["강의 예제 설명","docs/CHART-LAB.md"],["진입·청산 코드","hyperpass/chart_lab.py#L226"]]) {
      const link=node("a",label,"text-button");
      link.href=base+path; link.target="_blank"; link.rel="noopener noreferrer";
      host.append(link,document.createTextNode(" "));
    }
  }
  function showRule() {
    const values = settings(), rule = rules[values.strategy];
    $("bt-rule-copy").textContent = rule.detail(values);
    sourceLinks($("bt-rule-source"), rule);
    const visible = values.strategy === "mean_reversion" ? ["bb_period","bb_std","rsi_period","rsi_entry"] :
      values.strategy === "sma_cross" ? ["fast_period","slow_period"] : ["fast_period","slow_period","breakout_period"];
    for (const field of $("bt-params").children) {
      field.hidden = !visible.includes(field.dataset.setting);
      field.querySelector("input").disabled=field.hidden;
    }
  }
  function scopeCopy() {
    const kr = $("bt-market").value === "KR";
    $("bt-example-load").textContent=(kr?"국내":"미국")+" PER 실습 불러오기";
    $("bt-universe").textContent = engine==="pine" ?
      (mode==="market"?"선택한 시장·업종의 현재 상장 종목을 TradingView에서 차례대로 검증합니다. 전체 시장 실행은 오래 걸릴 수 있고 상장폐지 종목은 누락될 수 있습니다.":
       mode==="custom"?"입력한 각 종목에 같은 Pine 코드를 적용합니다. 결과는 종목별로 저장됩니다.":"한 종목의 차트에서 전략을 실행하고 Strategy Tester 보고서를 확인합니다.") : mode === "market"
      ? (kr ? "현재 국내 상장 종목 목록" : "현재 미국 상장 종목 목록") + "을 조회해 후보를 찾습니다. 전체 시장은 수집에 시간이 걸리며 과거 상장폐지 종목이 누락될 수 있습니다."
      : mode === "single" ? "한 종목에 가용 자본을 배분해 진입·청산 규칙을 검증합니다." : "입력한 종목끼리 매수 후보를 비교하고 동시 보유 한도를 적용합니다.";
    $("bt-symbol").placeholder = kr ? "삼성전자 또는 005930" : "애플 또는 AAPL";
    $("bt-symbols").placeholder = kr ? "삼성전자, SK하이닉스, 현대차" : "애플, MSFT, 엔비디아";
    document.querySelector("label[for='bt-param-initial_capital']").textContent = "초기 자본 (" + currency($("bt-market").value) + ")";
  }
  function setMode(next) {
    if (["single","market","custom"].includes(next)) mode=next;
    invalidate(); $("bt-scope").value=mode; $("bt-engine").value=engine;
    const pine = engine === "pine";
    $("studio-local").hidden = pine; pinePane.hidden = !pine;
    $("bt-single-field").hidden = mode !== "single"; $("bt-symbol").required = mode === "single";
    $("bt-custom-field").hidden = mode !== "custom"; $("bt-symbols").required = mode === "custom";
    $("bt-sizing").hidden = mode === "single";
    for (const input of $("bt-sizing").querySelectorAll("input,select")) input.disabled = mode === "single";
    scopeCopy(); conditions.setScope(mode,$("bt-market").value,engine);
    if ($("bt-pine-market").value!==$("bt-market").value) {
      $("bt-pine-market").value=$("bt-market").value; $("bt-pine-market").dispatchEvent(new Event("change",{bubbles:true}));
    }
  }
  function selectedRecord(selectId) {
    const record = records.find(item=>item.id === $(selectId).value);
    if (!record) throw new Error("먼저 저장한 전략을 선택하세요.");
    return record;
  }
  async function refreshStrategies(selectId) {
    const version = ++strategyLoad, data = await api("/api/strategies");
    if (version !== strategyLoad) return;
    if (!Array.isArray(data.items)) throw new Error("저장한 전략 목록을 읽을 수 없습니다.");
    records = data.items; $("bt-library").hidden=!records.length;
    for (const id of ["bt-saved","bt-chart-saved"]) {
      const select=$(id), prior=selectId || select.value;
      select.replaceChildren(new Option(records.length ? "저장한 전략 선택" : "저장한 전략 없음",""),...records.map(recordOption));
      select.value = records.some(item=>item.id===prior) ? prior : "";
    }
    chartSelection();
  }
  function portableDefinition(body) {
    const {mode,market,symbols,settings,max_positions,ranking,lookback} = body;
    const definition = {mode,market,symbols:[...(symbols || [])],settings:{...settings},max_positions,ranking,lookback};
    for (const field of ["strategy_code","universe","rebalance","monthly_contribution","dividends","fundamentals"]) {
      if (body[field] !== undefined) definition[field] = body[field];
    }
    return definition;
  }
  async function save(name,kind,definition,source) {
    if (!name.trim()) throw new Error("저장할 전략 이름을 입력하세요.");
    const record = await api("/api/strategies",{name:name.trim(),kind,definition,source});
    await refreshStrategies(record.id);
    return record;
  }
  function checkMarketSymbol(symbol,market) {
    const korean = /\.(?:KS|KQ)$/i.test(symbol);
    if ((market === "KR") !== korean) throw new Error(symbol + "의 거래소와 선택한 시장이 다릅니다. 같은 시장의 종목을 입력하세요.");
    return symbol;
  }
  async function yahooSymbol(query,market) {
    const raw = query.trim();
    if (/^[0-9A-Z]+[.](?:KS|KQ)$/i.test(raw)) return checkMarketSymbol(raw.toUpperCase(),market);
    const match = await window.HyperpassSymbols.resolve(raw,"yahoo");
    if (!match?.yahoo) throw new Error(raw+"의 과거 시세 종목을 찾지 못했습니다.");
    return checkMarketSymbol(match.yahoo,market);
  }
  async function scopeBody() {
    const market=$("bt-market").value, selectedMode=mode;
    const parts=selectedMode==="single"?[$("bt-symbol").value.trim()]:selectedMode==="custom"?$("bt-symbols").value.split(/[,;\n]+/).map(x=>x.trim()).filter(Boolean):[];
    const unique=[...new Set(parts)];
    if(selectedMode!=="market" && (!unique.length || !unique[0]))throw new Error("검증할 종목명이나 티커를 입력하세요.");
    if(unique.length>300)throw new Error("직접 지정하는 종목은 최대 300개입니다.");
    const symbols=[];
    if (selectedMode==="single") {
      if(/^[0-9A-Z]+[.](?:KS|KQ)$/i.test(unique[0])) symbols.push(checkMarketSymbol(unique[0].toUpperCase(),market));
      else symbols.push(checkMarketSymbol((await window.HyperpassSymbols.field("bt-symbol","yahoo")).yahoo,market));
    }else for(let i=0;i<unique.length;i+=4)symbols.push(...await Promise.all(unique.slice(i,i+4).map(q=>yahooSymbol(q,market))));
    return {market,mode:selectedMode,symbols:[...new Set(symbols)],universe:conditions.readScope()};
  }
  const batch = window.HyperpassPineBatch.mount({api,scopeBody,startJob,save,setBusy,message,revision:()=>revision,invalidate});
  async function requestBody() {
    if (!$("bt-form").reportValidity()) throw new Error("검증 조건을 확인하세요.");
    const values = settings(), market = $("bt-market").value, selectedMode = mode;
    if (values.start_date > values.end_date) throw new Error("시작일이 종료일보다 늦습니다.");
    if (!$("bt-technical-fields").hidden && values.strategy!=="mean_reversion" && values.fast_period >= values.slow_period) throw new Error("단기 SMA는 장기 SMA보다 작아야 합니다.");
    const target=await scopeBody();
    const req = {name:$("bt-name").value.trim(),market:target.market,mode:target.mode,symbols:target.symbols,settings:values,
      max_positions:selectedMode === "single" ? 1 : Number($("bt-positions").value),
      ranking:$("bt-ranking").value,lookback:Number($("bt-lookback").value)};
    return {...req,...conditions.read()};
  }
  function fillLocal(record) {
    $("bt-example-info").hidden=true;
    const d = record.definition, s = d.settings;
    if (!rules[s?.strategy] || !["market","single","custom"].includes(d.mode) || !["US","KR"].includes(d.market)) throw new Error("이 전략의 실행 조건을 읽을 수 없습니다.");
    if (s.slippage_mode==="ticks") throw new Error("이 전략은 틱 단위 슬리피지를 사용합니다. 차트 연구실에서 저장한 조건으로 검증하세요.");
    retainedSettings={...s};
    engine="portfolio"; $("bt-market").value=d.market; setMode(d.mode); $("bt-rule").value=s.strategy;
    for (const key of Object.keys(numericField)) {
      if (!Number.isFinite(s[key])) throw new Error("저장한 전략에서 " + numericField[key][0] + " 값을 찾지 못했습니다.");
      $("bt-param-"+key).value = s[key];
    }
    $("bt-start").value=s.start_date; $("bt-end").value=s.end_date;
    $("bt-positions").value=d.max_positions; $("bt-name").value=record.name;
    $("bt-ranking").value=d.ranking || "momentum_high"; $("bt-lookback").value=d.lookback ?? 20;
    $("bt-symbol").value=d.mode==="single" ? (d.symbols?.[0] || "") : "";
    $("bt-symbol").dispatchEvent(new Event("input",{bubbles:true}));
    $("bt-symbols").value=d.mode==="custom" ? (d.symbols||[]).join(", ") : "";
    conditions.restore(d); showRule(); scopeCopy(); invalidate(); message("bt-feedback",record.name+"의 저장 조건을 불러왔습니다.");
  }
  function loadPine(record, target) {
    const d = record.definition;
    if (!d.code || !$("tv-timeframe").querySelector("option[value='"+CSS.escape(d.timeframe)+"']")) throw new Error("저장한 Pine 코드 또는 주기를 읽을 수 없습니다.");
    engine="pine";
    const detected=target ? (/^(?:KRX|KOSPI|KOSDAQ)/i.test(target)?"KR":"US") : null;
    if(target && d.market && d.market!==detected) throw new Error("선택한 차트 종목과 저장 전략의 시장이 다릅니다.");
    $("bt-market").value=d.market || detected || $("bt-market").value;
    setMode(target?"single":d.mode||"single");
    window.HyperpassApp.selectWorkspace("tradingview");
    $("tv-code").value=d.code; $("tv-timeframe").value=d.timeframe; $("bt-pine-name").value=record.name;
    conditions.restoreScope(d.universe);
    $("bt-symbol").value=target || d.symbol || (d.mode==="single"?d.symbols?.[0]:"") || "";
    $("bt-symbol").dispatchEvent(new Event("input",{bubbles:true}));
    $("bt-symbols").value=(d.symbols||[]).join(", ");
    message("bt-pine-feedback",record.name+" 코드를 불러왔습니다. 투자 대상과 주기를 확인하세요.");
    $("tv-code").focus();
  }
  function intervalKey(value) {
    const text=String(value||"").trim();
    return ({D:"1d","1D":"1d",W:"1wk","1W":"1wk",M:"1mo","1M":"1mo"})[text] || text;
  }
  async function currentInterval() {
    if ($("chart-source").value!=="tradingview") return intervalKey($("chart-interval").value);
    const query=new URLSearchParams({port:$("chart-port").value}), target=$("chart-target")?.value;
    if(target) query.set("target_id",target);
    const status=await api("/api/tradingview/status?"+query);
    if(!status.chart?.timeframe || (!status.connected && !status.success)) throw new Error(status.error || "TradingView Desktop의 열린 차트와 주기를 확인하세요.");
    return intervalKey(status.chart.timeframe);
  }
  async function loadChart(record) {
    if (!rules[record.definition?.settings?.strategy]) throw new Error("차트 전략의 규칙을 읽을 수 없습니다.");
    window.HyperpassApp.selectWorkspace("chart");
    const required=record.kind==="market" ? "1d" : record.definition.interval;
    if (required) {
      if($("chart-source").value==="yahoo") {
        if(![...$("chart-interval").options].some(option=>option.value===required)) throw new Error("저장한 주기는 "+required+"입니다. 해당 주기의 TradingView Desktop 차트를 선택하세요.");
        $("chart-interval").value=required;
      } else if(await currentInterval()!==required) throw new Error("저장한 전략 주기는 "+required+"입니다. 해당 주기의 원본 데이터와 차트 주기를 선택하세요.");
    }
    window.HyperpassChart.applySettings(record.definition.settings);
    $("bt-chart-name").value=record.name;
    message("bt-chart-feedback",record.name+" 조건을 적용했습니다. "+(required ? "저장 주기 "+required : "이전 기록에 주기가 없어 현재 차트 주기를 사용합니다."));
  }
  function table(parent, headers, rows, empty) {
    parent.replaceChildren();
    if (!rows.length) { parent.append(node("p",empty,"cost-note")); return; }
    const viewport=node("div",null,"studio-scroll"), t=node("table"), head=t.createTHead().insertRow(), body=t.createTBody();
    viewport.tabIndex=0; viewport.setAttribute("role","region"); viewport.setAttribute("aria-label",headers.join(" · "));
    for (const title of headers) { const th=node("th",title); th.scope="col"; head.append(th); }
    const more=node("button","","text-button"); more.type="button";
    let index=0;
    function next() {
      for (const values of rows.slice(index,index+75)) {
        const tr=body.insertRow();
        for (const v of values) tr.append(node("td",v ?? "—"));
      }
      index+=75; more.hidden = index>=rows.length;
      more.textContent = "다음 " + Math.min(75,Math.max(0,rows.length-index)) + "건 보기 · 전체 " + rows.length + "건";
    }
    more.addEventListener("click",next); viewport.append(t); parent.append(viewport,more); next();
  }
  function drawCurve(canvas, series, key, color) {
    if (!canvas.clientWidth || !series.length) return;
    const w=Math.round(canvas.clientWidth), h=104, dpr=Math.min(window.devicePixelRatio||1,2);
    canvas.width=w*dpr; canvas.height=h*dpr; const ctx=canvas.getContext("2d");
    ctx.scale(dpr,dpr); ctx.clearRect(0,0,w,h);
    const values=series.map(p=>p[key]).filter(Number.isFinite);
    if (!values.length) return;
    const low=Math.min(...values),high=Math.max(...values), span=high-low;
    const y=v=>span ? 9+(1-(v-low)/span)*(h-23) : h/2;
    ctx.strokeStyle="#504b3e"; ctx.beginPath(); ctx.moveTo(0,h-10); ctx.lineTo(w,h-10); ctx.stroke();
    ctx.strokeStyle=color; ctx.lineWidth=2; ctx.beginPath();
    values.forEach((v,i)=>{const x = 2+(w-4)*i/Math.max(values.length-1,1); if (i) ctx.lineTo(x,y(v)); else ctx.moveTo(x,y(v));});
    ctx.stroke();
  }
  function drawCurves() {
    const rows=resultJob?.result?.equity_curve || [];
    drawCurve($("bt-equity-plot"),rows,"equity","#fa9152");
    drawCurve($("bt-dd-plot"),rows,"drawdown_pct","#d8b974");
  }
  new ResizeObserver(drawCurves).observe($("bt-curves"));
  function renderResult(job) {
    resultJob=job;
    const r=job.result, m=r.metrics, unit=currency(r.market || job.request.market), coverage=r.coverage;
    const metricData=[
      ["비용 차감 수익률",pct(m.total_return_pct)],["최대 낙폭 (MDD)",pct(m.max_drawdown_pct)],
      ["벤치마크 " + (r.benchmark?.name || r.benchmark?.symbol || ""),pct(m.benchmark_return_pct)],["초과 수익률",Number.isFinite(m.excess_return_pct) ? money(m.excess_return_pct)+"%p" : "—"],
      ["종료 자산 ("+unit+")",money(m.ending_equity)],["연환산 변동성",pct(m.annualized_volatility_pct)],
      ["샤프 지수",money(m.sharpe)],["완결 거래 / 승률",money(m.closed_trades)+"건 / "+pct(m.win_rate_pct)],
      ["누적 수수료 ("+unit+")",money(m.fees)],["누적 슬리피지 ("+unit+")",money(m.slippage)],["회전율",pct(m.turnover_pct)],
      ["거래비용 2배 수익률",pct(r.cost_stress?.metrics?.total_return_pct)],["후반 별도 검증 수익률",pct(r.holdout?.metrics?.total_return_pct)],
      ["최장 낙폭 기간",money(m.longest_drawdown_sessions)+"거래일"],["평균 주식 비중",pct(m.average_exposure_pct)]
    ];
    if (Number.isFinite(m.contributions)) metricData.push(["누적 추가 납입 ("+unit+")",money(m.contributions)]);
    if (Number.isFinite(m.dividend_income)) metricData.push(["배당 수입 ("+unit+")",money(m.dividend_income)]);
    const metrics=$("bt-metrics"); metrics.replaceChildren();
    for (const [label,value] of metricData) {
      const el=node("div",null,"chart-metric"); el.append(node("span",label),node("strong",value)); metrics.append(el);
    }
    const curve=r.equity_curve || [];
    $("bt-curves").hidden = !curve.length;
    $("bt-equity-range").textContent = curve.length ? curve[0].date+" ~ "+curve.at(-1).date+" · "+curve.length+"거래일 · "+unit : "";
    $("bt-orders-block").hidden=!Array.isArray(r.orders);
    if (Array.isArray(r.orders)) {
      const factorNames={per:"PER",momentum:"모멘텀(%)",close:"종가",volume:"거래량"};
      table($("bt-orders"),["종목","방향","신호일","체결일","수량","체결가 ("+unit+")","선정 지표"],
        r.orders.map(o=>[o.symbol,o.side==="buy"?"매수":"매도",o.signal_date,o.date,money(o.quantity),money(o.price),
          Object.entries(o.factors||{}).map(([field,value])=>(factorNames[field]||field)+" "+money(value)).join(" · ")||"—"]),
        "선택한 조건과 기간에 체결된 주문이 없습니다.");
    }
    table($("bt-trades"),["종목","매수일","매도일","수량","매수가","매도가","순손익 ("+unit+")","수익률"],
      (r.trades || []).map(t=>[t.name && t.name!==t.symbol ? t.name+" · "+t.symbol : t.symbol,t.entry_date,t.exit_date,money(t.quantity),money(t.entry_price),money(t.exit_price),money(t.net_pnl),pct(t.return_pct)]),"이 기간에 청산까지 마친 거래는 없습니다.");
    table($("bt-holdings"),["종목","매수일","수량","매수가","최종 평가가","평가액 ("+unit+")"],
      (r.open_positions || []).map(t=>[t.name && t.name!==t.symbol ? t.name+" · "+t.symbol : t.symbol,t.entry_date,money(t.quantity),money(t.entry_price),money(t.last_price),money(t.market_value)]),"마지막 날 보유한 종목이 없습니다.");
    $("bt-coverage").textContent=[coverage?.source,coverage?.as_of && "목록 기준 "+coverage.as_of,coverage?.price_source,
      Number.isFinite(coverage?.used) && "분석 "+money(coverage.used)+" / 요청 "+money(coverage.requested)+"종목",
      Number.isFinite(coverage?.traded) && "실제 편입 "+money(coverage.traded)+"종목",
      coverage?.factor_data && "순위 산정 가능 "+money(coverage.factor_data.scored_observations)+"건 · 지표 누락 "+money(coverage.factor_data.missing_observations)+"건",
      "편도 수수료 "+money(r.settings.fee_bps)+"bp", r.settings.slippage_mode==="ticks" ? "슬리피지 "+money(r.settings.slippage_ticks)+"틱" : "편도 슬리피지 "+money(r.settings.slippage_bps)+"bp"].filter(Boolean).join(" · ");
    const notes=[r.method,r.risk_basis,r.benchmark?.basis && "벤치마크 · "+r.benchmark.basis,
      r.holdout && "후반 검증 "+r.holdout.start+" ~ "+r.holdout.end+" · "+r.holdout.basis,...(r.warnings || [])].filter(Boolean);
    $("bt-warnings").replaceChildren(...notes.map(w=>node("li",w)));
    const excluded=coverage?.excluded || [];
    $("bt-exclusions").hidden=!excluded.length;
    if (excluded.length) table($("bt-excluded-list"),["종목","제외 사유"],excluded.map(t=>[t.symbol,t.reason]),"제외한 종목이 없습니다.");
    $("bt-result").hidden=false; message("bt-result-feedback",""); drawCurves();
  }
  function displayJob(job) {
    currentJob=job; clearTimeout(pollTimer);
    $("bt-cancel").hidden=!running(job); $("bt-retry").hidden=true;
    $("bt-result-title").textContent=labelOf(job);
    $("bt-status").textContent=statuses[job.status] || job.status;
    const percent=Number.isFinite(job.progress?.percent) ? Math.max(0,Math.min(100,job.progress.percent)) : null;
    $("bt-progress").hidden=!running(job);
    if(percent===null) $("bt-progress").removeAttribute("value"); else $("bt-progress").value=percent;
    const text=[modeNames[job.request?.mode], job.request?.market, job.progress?.label, running(job) && percent!=null && (Math.round(percent)+"%"),job.error].filter(Boolean).join(" · ");
    message("bt-job-message",text || statuses[job.status],["failed","interrupted"].includes(job.status));
    $("bt-result").hidden=true; resultJob=null;
    batch.hide();
    if(job.result && (job.result.engine==="pine" || job.request?.engine==="pine")) batch.display(job);
    else if(job.status==="completed" && job.result) renderResult(job);
    if(running(job)) {
      const version=requestVersion;
      pollTimer=setTimeout(()=>pollJob(job.id,version),1600);
    }
  }
  async function pollJob(id,version) {
    if(version!==requestVersion) return;
    try {
      const job=await api("/api/backtests/"+encodeURIComponent(id));
      if(version!==requestVersion) return;
      displayJob(job);
      if(!running(job)) refreshHistory().catch(error=>message("bt-history-feedback",error.message,true));
    } catch(error) {
      if(version!==requestVersion)return;
      message("bt-job-message","상태를 확인하지 못했습니다. "+error.message,true); $("bt-retry").hidden=false;
    }
  }
  async function refreshHistory(resume=false) {
    const version=++historyLoad, data=await api("/api/backtests");
    if(version!==historyLoad) return;
    if(!Array.isArray(data.items)) throw new Error("실행 기록을 읽을 수 없습니다.");
    historyRows=data.items;
    const target=$("bt-history"); target.replaceChildren(); message("bt-history-feedback","");
    if (!historyRows.length) target.append(node("p","저장된 실행이 없습니다.","cost-note"));
    for(const job of historyRows) {
      const button=node("button",null,"tv-history-item"); button.type="button";
      button.append(node("strong",labelOf(job)),node("span",[modeNames[job.mode],statuses[job.status]].filter(Boolean).join(" · ")),node("small",job.created_at?new Date(job.created_at).toLocaleString("ko-KR"):""));
      button.addEventListener("click",()=>openHistory(job.id)); target.append(button);
    }
    if(resume && !currentJob && !pendingRequest) {
      const active=historyRows.find(running);
      if(active) await openHistory(active.id);
    }
  }
  async function openHistory(id) {
    clearTimeout(pollTimer);
    const version=++requestVersion;
    try {
      const job=await api("/api/backtests/"+encodeURIComponent(id)); if(version!==requestVersion)return;
      displayJob(job);
    } catch(error){if(version===requestVersion) message("bt-job-message",error.message,true);}
  }
  async function startJob(body) {
    if(pendingRequest) throw new Error("앞선 실행 요청을 확인하고 있습니다.");
    if(running(currentJob)) throw new Error("진행 중인 실행이 끝난 뒤 다시 실행하세요.");
    pendingRequest=true; clearTimeout(pollTimer);
    const version=++requestVersion;
    try {
      const job=await api("/api/backtests",body);
      if (version!==requestVersion)return;
      displayJob(job); await refreshHistory();
      message(engine==="pine"?"bt-pine-feedback":"bt-feedback","실행 기록에 저장했습니다.");
    } finally {pendingRequest=false;}
  }
  function chartSelection() {
    const record=records.find(item=>item.id===$("bt-chart-saved").value);
    $("bt-chart-compare").hidden=record?.kind!=="market" || !!record?.definition?.strategy_code;
    $("bt-chart-apply").textContent = record?.kind==="pine" ? "TradingView에서 이 종목 검증 ↗" : record?.definition?.strategy_code ? "이 종목의 실행 조건 확인 ↗" : "선택한 전략으로 검증";
  }
  async function openOnChart(record, compare=false) {
    const target=$("chart-symbol").value.trim();
    if (!target) throw new Error("차트에 조회할 종목을 먼저 입력하세요.");
    if(record.kind==="chart" || (record.kind==="market" && !record.definition.strategy_code && !compare)) {
      if(record.kind==="market" && $("chart-source").value==="yahoo")
        checkMarketSymbol((await window.HyperpassSymbols.field("chart-symbol","yahoo")).yahoo,record.definition.market);
      await loadChart(record); updateChartSource();
      if(record.kind==="market")message("bt-chart-feedback","저장한 진입·청산·비용 규칙을 이 종목의 일봉에 적용합니다. 시장 내 순위와 분산 효과는 시장 전체 검증에서 확인하세요.");
      $("chart-form").requestSubmit(); return;
    }
    if(record.kind==="pine") {
      const match=await window.HyperpassSymbols.resolve(target,"tradingview");
      if(!match?.id) throw new Error("TradingView 종목을 확인하지 못했습니다.");
      loadPine(record,match.id); return;
    }
    const d=portableDefinition(record.definition);
    const symbol=checkMarketSymbol((await window.HyperpassSymbols.field("chart-symbol","yahoo")).yahoo,d.market);
    d.mode="single"; d.symbols=[symbol]; d.max_positions=1;
    window.HyperpassApp.selectWorkspace("tradingview");
    fillLocal({name:record.name,definition:d});
    message("bt-feedback","이 종목의 일봉으로 저장한 규칙·기간·비용을 검증합니다.");
    $("bt-name").value=record.name+" · "+symbol;
    await previewConditions(); $("bt-run").focus();
  }
  function updateChartSource() {
    const r=rules[$("chart-strategy").value];
    sourceLinks($("bt-chart-source"),r);
  }
  function onOpen() {
    if(host.hidden && $("workspace-chart").hidden) return;
    if(!initialLoad) {
      initialLoad=true;
      refreshStrategies().catch(error=>{initialLoad=false;message(host.hidden?"bt-chart-feedback":"bt-library-feedback",error.message,true);});
    }
    if(!host.hidden) refreshHistory(true).catch(error=>message("bt-history-feedback",error.message,true));
  }
  $("bt-engine").addEventListener("change",()=>{engine=$("bt-engine").value;setMode(mode);});
  $("bt-scope").addEventListener("change",()=>setMode($("bt-scope").value));
  for(const id of ["bt-target-panel","studio-pine"]) {
    $(id).addEventListener("input",invalidate); $(id).addEventListener("change",invalidate);
  }
  document.addEventListener("hyperpass:symbol-picked",event=>{if(event.target.id==="bt-symbol")invalidate();});
  let editedDraft=false;
  for (const event of ["input","change"]) $("bt-form").addEventListener(event,()=>{editedDraft=true;});
  $("bt-form").addEventListener("click",event=>{
    if(event.target.closest("#bt-builder button,#bt-scope-details button,#bt-upgrade")) editedDraft=true;
  });
  $("bt-example-load").addEventListener("click",()=>setBusy($("bt-example-load"),"bt-feedback",async()=>{
    if (editedDraft && !window.confirm("현재 입력한 조건을 선택한 시장의 PER 실습으로 바꿀까요?")) return;
    const market=$("bt-market").value, version=revision;
    const example=await api("/api/backtests/example?market="+market);
    if (version!==revision || market!==$("bt-market").value) throw new Error("입력이 바뀌었습니다. 실습 불러오기를 다시 눌러 주세요.");
    fillLocal({name:example.name,definition:example});
    const info=$("bt-example-info"); info.replaceChildren(node("p",example.description || "공시 시점을 포함한 과거 EPS를 함께 불러왔습니다."));
    for (const source of example.sources || []) {
      if (typeof source.url!=="string" || !source.url.startsWith("https://")) continue;
      const link=node("a",source.name,"text-button"); link.href=source.url;link.target="_blank";link.rel="noopener noreferrer";
      info.append(link,document.createTextNode(" "));
    }
    info.hidden=false; editedDraft=false;
    message("bt-feedback","PER 실습을 불러왔습니다. 조건과 공시 자료를 살펴본 뒤 실행 조건 확인을 누르세요.");
  }));
  $("bt-market").addEventListener("change",()=>{
    if ($("bt-pine-market").value!==$("bt-market").value) {
      $("bt-pine-market").value=$("bt-market").value; $("bt-pine-market").dispatchEvent(new Event("change",{bubbles:true}));
    }
    $("bt-example-info").hidden=true;
    const input=$("bt-param-initial_capital");
    if ([100000000,100000].includes(Number(input.value))) input.value=$("bt-market").value==="KR" ? 100000000 : 100000;
    scopeCopy(); conditions.setScope(mode,$("bt-market").value,engine);
  });
  $("bt-rule").addEventListener("change",()=>{
    if(Object.values(rules).some(rule=>rule.title===$("bt-name").value) || !$("bt-name").value.trim()) $("bt-name").value=rules[$("bt-rule").value].title;
    showRule();
  });
  $("bt-params").addEventListener("input",showRule);
  async function previewConditions() {
    invalidate();
    const current=revision;
    const body=await requestBody();
    if(current!==revision) throw new Error("입력이 바뀌었습니다. 실행 조건을 다시 확인하세요.");
    const data=await api("/api/backtests/preview",body);
    if(current!==revision) throw new Error("입력이 바뀌었습니다. 실행 조건을 다시 확인하세요.");
    if(!data.request?.settings) throw new Error("서버에서 실행 조건을 확인하지 못했습니다.");
    previewed={...data.request,name:body.name};
    const summary = $("bt-preview-summary");
    summary.textContent=conditions.summary(previewed);
    summary.hidden=false; $("bt-run").disabled=false;
    message("bt-feedback","확인한 조건으로 백테스트를 시작할 수 있습니다.");
  }
  $("bt-preview").addEventListener("click",()=>setBusy($("bt-preview"),"bt-feedback",previewConditions));
  $("bt-form").addEventListener("input",invalidate);
  $("bt-form").addEventListener("change",invalidate);
  $("bt-form").addEventListener("submit",async event=>{
    event.preventDefault();
    try {
      if(!previewed) throw new Error("실행 조건 확인을 먼저 눌러 주세요.");
      const body=previewed; invalidate(); await startJob(body);
    } catch(error) { message("bt-feedback",error.message,true); }
  });
  $("bt-save").addEventListener("click",()=>setBusy($("bt-save"),"bt-feedback",async()=>{
    const body=await requestBody(); await save(body.name,"market",portableDefinition(body),body.strategy_code ? "포트폴리오 조건 코드 v1" : rules[body.settings.strategy].source);
    message("bt-feedback","현재 검증 조건을 내 전략에 추가했습니다.");
  }));
  $("bt-save-tested").addEventListener("click",()=>setBusy($("bt-save-tested"),"bt-result-feedback",async()=>{
    const job=resultJob;
    if (!job?.request?.settings) throw new Error("저장할 완료된 실행을 선택하세요.");
    const request=job.request;
    await save(labelOf(job),"market",portableDefinition(request),request.strategy_code ? "포트폴리오 조건 코드 v1" : rules[request.settings.strategy].source);
    message("bt-result-feedback","이 실행에서 사용한 조건을 내 전략에 추가했습니다.");
  }));
  $("bt-download").addEventListener("click",()=>{
    if(!resultJob) return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(resultJob,null,2)],{type:"application/json"})),link=node("a");
    link.href=url; link.download="backtest-"+resultJob.id+".json"; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $("bt-load").addEventListener("click",()=>setBusy($("bt-load"),"bt-library-feedback",async()=>{
    const record=selectedRecord("bt-saved");
    if(record.kind==="market") fillLocal(record);
    else if(record.kind==="chart") await loadChart(record);
    else if(record.kind==="pine") loadPine(record);
    message("bt-library-feedback",record.name+"을 불러왔습니다.");
  }));
  $("bt-chart-apply").addEventListener("click",()=>setBusy($("bt-chart-apply"),"bt-chart-feedback",async()=>{
    const record=selectedRecord("bt-chart-saved");
    try { await openOnChart(record); }
    catch(error) {if(!host.hidden)message("bt-feedback",error.message,true);throw error;}
  }));
  $("bt-chart-saved").addEventListener("change",chartSelection);
  $("bt-chart-compare").addEventListener("click",()=>setBusy($("bt-chart-compare"),"bt-chart-feedback",async()=>{
    try { await openOnChart(selectedRecord("bt-chart-saved"),true); }
    catch(error){if(!host.hidden)message("bt-feedback",error.message,true);throw error;}
  }));
  $("bt-chart-save").addEventListener("click",()=>setBusy($("bt-chart-save"),"bt-chart-feedback",async()=>{
    const s=window.HyperpassChart.settings(), rule=rules[s.strategy];
    if(!rule) throw new Error("저장할 매매 규칙을 선택하세요.");
    await save($("bt-chart-name").value,"chart",{settings:s,interval:await currentInterval()},rule.source);
    message("bt-chart-feedback","이 차트의 매매 규칙과 비용·검증 조건을 저장했습니다.");
  }));
  $("bt-cancel").addEventListener("click",()=>setBusy($("bt-cancel"),"bt-job-message",async()=>{
    const id=currentJob.id, version=++requestVersion; clearTimeout(pollTimer);
    try {
      const updated=await api("/api/backtests/"+encodeURIComponent(id)+"/cancel",{});
      if(version===requestVersion){
        if(updated.cancelling)await pollJob(id,version);
        else displayJob(updated);
      }
    } catch(error){if(version===requestVersion)$("bt-retry").hidden=false;throw error;}
  }));
  $("bt-retry").addEventListener("click",()=>currentJob && pollJob(currentJob.id,++requestVersion));
  $("bt-history-refresh").addEventListener("click",()=>setBusy($("bt-history-refresh"),"bt-history-feedback",()=>refreshHistory(true)));
  $("chart-strategy").addEventListener("change",updateChartSource);
  document.addEventListener("hyperpass:chart-result",updateChartSource);
  const testedPine=node("button","이 실행의 Pine 전략 저장","button ghost compact");
  testedPine.type="button"; testedPine.hidden=true;
  $("tv-result-actions").append(testedPine);
  const testedFeedback=node("p",null,"feedback"); testedFeedback.id="bt-tested-pine-feedback"; testedFeedback.setAttribute("role","status");
  $("tv-result-actions").after(testedFeedback);
  document.addEventListener("hyperpass:tradingview-result",event=>{
    const job=event.detail?.job;
    pineRun=job?.status==="completed" && job.request?.action==="backtest" && job.request.code && event.detail.result?.report ? job : null;
    testedPine.hidden=!pineRun; testedFeedback.textContent="";
  });
  testedPine.addEventListener("click",()=>setBusy(testedPine,"bt-tested-pine-feedback",async()=>{
    if(!pineRun) throw new Error("완료된 Pine 백테스트를 선택하세요.");
    const input=pineRun.request, name=$("bt-pine-name").value.trim();
    if(!name){$("bt-pine-name").focus(); throw new Error("Pine 편집기 아래에 저장할 이름을 입력하세요.");}
    await save(name,"pine",{code:input.code,timeframe:input.timeframe},"TradingView 실행 "+pineRun.id);
    message("bt-tested-pine-feedback","이 실행에서 검증한 전체 Pine 코드와 주기를 저장했습니다.");
  }));
  document.addEventListener("hyperpass:workspace-change",onOpen);
  document.addEventListener("hyperpass:show-pine-backtest", () => {engine="pine"; setMode("single"); legacyLog.open=true;});
  window.HyperpassBacktest={openSymbols({market,symbols,name}) {
    if(!["US","KR"].includes(market)||!Array.isArray(symbols)||!symbols.length||symbols.length>300)throw new Error("검증할 시장과 1~300개 종목을 선택하세요.");
    engine="pine"; $("bt-market").value=market;setMode(symbols.length===1?"single":"custom");
    if(mode==="single") {$("bt-symbol").value=symbols[0];$("bt-symbol").dispatchEvent(new Event("input",{bubbles:true}));}
    else $("bt-symbols").value=symbols.join(", ");
    conditions.restoreScope({});if(name)$("bt-pine-name").value=name;
    $("bt-market").dispatchEvent(new Event("change",{bubbles:true}));
    window.HyperpassApp.selectWorkspace("tradingview");
    $("bt-target-panel").scrollIntoView({block:"start"});
  }};
  showRule(); setMode("single"); updateChartSource(); onOpen();
})();
