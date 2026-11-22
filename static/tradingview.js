"use strict";
(() => {
  const host=document.getElementById("workspace-tradingview");
  if(!host)return;
  const $=id=>document.getElementById(id);
  const state={indicators:[],job:null,timer:null,busy:false,checking:false,result:null,lastStatus:null};
  const indicatorGroups = [
    ["추세 · 이동평균", [
      ["Moving Average","단순 이동평균 SMA",20],["Exponential moving average","지수 이동평균 EMA",20],
      ["Weighted moving average","가중 이동평균 WMA",20],["Hull moving average","헐 이동평균 HMA",16],
      ["Ichimoku cloud","일목균형표"],["Parabolic SAR","파라볼릭 SAR"],["Directional Movement","방향성 지수 DMI"],
      ["Pivot points high low","고점·저점 피벗"]]],
    ["모멘텀", [
      ["Relative Strength Index","상대강도지수 RSI",14],["MACD","MACD"],["Stochastic","스토캐스틱"],
      ["Stochastic RSI","스토캐스틱 RSI"],["Commodity channel index","상품채널지수 CCI",20],
      ["Momentum","모멘텀",10],["Rate of change","변화율 ROC",9],["Williams %R","윌리엄스 %R"]]],
    ["변동성 · 채널", [
      ["Bollinger Bands","볼린저 밴드",20],["Average True Range","평균 실질 범위 ATR",14],
      ["Donchian channels","돈치안 채널",20],["Keltner channels","켈트너 채널"],["Historical volatility","역사적 변동성"]]],
    ["거래량", [
      ["Volume","거래량"],["VWAP","거래량 가중 평균가격 VWAP"],["VWMA","거래량 가중 이동평균 VWMA"],
      ["On-balance volume","누적 거래량 OBV"],["Chaikin money flow","차이킨 자금 흐름 CMF"]]]
  ];
  const indicatorNames = Object.fromEntries(indicatorGroups.flatMap(([,items]) => items.map(([name,label]) => [name,label])));
  const indicatorLengths = new Map(indicatorGroups.flatMap(([,items]) => items.map(([name,,length]) => [name,length])));
  host.innerHTML=`<div class="workspace-heading"><div><span class="eyebrow">TRADINGVIEW / CONNECTED RESEARCH</span><h1>차트에 적용하고, 실제 결과를 확인하세요.</h1><p>TradingView Desktop의 차트와 Pine 편집기를 연결합니다. 매매·계좌·주문 기능은 사용하지 않습니다.</p></div><span class="workspace-state" id="tv-connection-badge">연결 확인 필요</span></div>
    <section class="panel tv-connection-panel" aria-labelledby="tv-connection-title"><div><span class="section-kicker">01 / CONNECT DESKTOP</span><h2 id="tv-connection-title">TradingView Desktop 연결</h2><p>TradingView에 로그인하고 차트를 열어 두세요. 로컬 디버그 연결이 필요하며, TradingView API 키를 입력하는 방식은 아닙니다.</p></div><div class="tv-connect-controls"><div><label class="field-label" for="tv-port">로컬 연결 포트</label><input id="tv-port" type="number" min="1024" max="65535" value="9222"></div><button id="tv-check" class="button ghost" type="button">연결 확인 ↻</button><button id="tv-launch" class="button ghost" type="button">Desktop 연결 실행 ↗</button></div><p id="tv-connect-feedback" class="feedback" aria-live="polite"></p><div id="tv-target-control" class="tv-target-control" hidden><label class="field-label" for="tv-target">작업할 TradingView 차트 창</label><select id="tv-target"><option value="">열린 차트 자동 선택</option></select></div><div id="tv-current-chart" class="tv-current-chart" hidden></div></section>
    <div class="tv-workbench"><section class="panel tv-chart-controls"><div class="panel-heading"><div><span class="section-kicker">02 / CHART SETTINGS</span><h2>종목·주기·지표</h2></div></div><div class="tv-panel-body"><label class="field-label" for="tv-symbol">TradingView 종목</label><input id="tv-symbol" maxlength="80" placeholder="삼성전자, 애플, AAPL" autocomplete="off" spellcheck="false" aria-describedby="tv-symbol-status"><div id="tv-symbol-matches" class="tv-symbol-matches"></div><p id="tv-symbol-status" class="small-muted" aria-live="polite"></p><label class="field-label" for="tv-timeframe">차트 주기</label><select id="tv-timeframe"><option value="1D">일봉</option><option value="1W">주봉</option><option value="1M">월봉</option><option value="60">1시간</option><option value="15">15분</option><option value="5">5분</option></select>
    <div class="tv-indicator-builder"><label class="field-label" for="tv-indicator">반영할 지표</label><select id="tv-indicator"></select><label class="field-label" for="tv-indicator-length">기간</label><input id="tv-indicator-length" type="number" min="1" max="10000" value="20"><details class="tv-advanced-inputs"><summary>고급 입력값 선택</summary><p>TradingView의 입력 ID와 값을 JSON으로 지정할 수 있습니다. 아래 값은 기간보다 우선합니다. 예: <code>{"in_0": 20}</code></p><label class="sr-only" for="tv-indicator-inputs">지표 고급 입력값 JSON</label><textarea id="tv-indicator-inputs" rows="3" spellcheck="false" placeholder='{"in_0": 20}'></textarea></details><button id="tv-queue-indicator" type="button" class="button ghost">지표 목록에 추가 ＋</button></div><div id="tv-indicators" class="tv-indicator-list"></div><p class="cost-note">기존 차트를 실제로 변경합니다. 선택하지 않은 지표나 드로잉은 임의로 지우지 않습니다.</p><button id="tv-configure" type="button" class="button primary">차트 설정 적용 ↗</button></div></section>
    <section class="panel tv-pine-panel" aria-labelledby="tv-pine-title"><div class="panel-heading"><div><span class="section-kicker">03 / PINE STRATEGY</span><h2 id="tv-pine-title">전략 코드로 백테스트</h2></div><label for="tv-code-file" class="button ghost compact">Pine 파일 읽기 ↑</label><input id="tv-code-file" type="file" accept=".pine,.txt" class="sr-only"></div><div class="tv-panel-body"><label class="sr-only" for="tv-code">Pine 전략 코드</label><textarea id="tv-code" rows="22" maxlength="200000" spellcheck="false" placeholder="//@version=6&#10;// strategy(...)로 시작하는 Pine 전략 코드를 붙여넣으세요.&#10;// 차트 연구실에서 내보낸 Pine Script도 사용할 수 있습니다."></textarea><div class="tv-pine-footer"><p>선택한 종목·주기에 코드를 적용하고 컴파일과 Strategy Tester 결과를 확인합니다. 기존 편집기 코드의 보관 여부와 실행 결과는 아래 기록에 표시됩니다.</p><button id="tv-backtest" type="button" class="button primary">전략 적용 · 백테스트 ↗</button></div><p id="tv-input-feedback" class="feedback" aria-live="polite"></p></div></section></div>
    <section class="panel tv-job-panel" aria-labelledby="tv-job-title"><div class="panel-heading"><div><span class="section-kicker">04 / VERIFIED OUTPUT</span><h2 id="tv-job-title">실행 결과</h2></div><span id="tv-job-badge" class="workspace-state">실행 전</span></div><div class="tv-panel-body"><p id="tv-job-message" aria-live="polite">차트 설정이나 백테스트를 실행하면 현재 단계와 TradingView에서 확인한 결과가 여기에 표시됩니다.</p><p id="tv-job-time" class="small-muted"></p><button id="tv-job-retry" type="button" class="button ghost compact" hidden>실행 상태 다시 확인 ↻</button><div id="tv-job-progress" class="tv-job-progress" hidden><span></span></div><div id="tv-result-summary" hidden></div><div id="tv-metrics" class="tv-metrics"></div><ul id="tv-result-warnings" class="tv-result-warnings"></ul><pre id="tv-compile-errors" class="tv-compile-errors" hidden></pre><div id="tv-result-actions" class="workspace-actions" hidden><button id="tv-result-download" type="button" class="button ghost">실행 결과 JSON ↓</button><button id="tv-result-research" type="button" class="button primary" hidden>기술 분석 에이전트에게 질문 ↗</button></div><details id="tv-raw-result" class="tv-raw-result" hidden><summary>원본 결과와 실행 조건</summary><pre id="tv-result-json"></pre></details></div></section>
    <section class="panel tv-history-panel" aria-labelledby="tv-history-title"><div class="panel-heading"><div><span class="section-kicker">RESEARCH LOG</span><h2 id="tv-history-title">저장된 TradingView 실행</h2></div><button id="tv-history-refresh" type="button" class="text-button">새로고침 ↻</button></div><p id="tv-history-feedback" class="feedback" aria-live="polite"></p><div id="tv-history" class="tv-history"></div></section>`;
  const make=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=String(text);return node;};
  for (const [title,items] of indicatorGroups) {
    const group=document.createElement("optgroup"); group.label=title;
    for (const [name,label] of items) { const option=make("option","",label); option.value=name; group.append(option); }
    $("tv-indicator").append(group);
  }
  const backupButton=make("button","button ghost","실행 전 Pine 코드 ↓");backupButton.id="tv-backup-download";backupButton.type="button";backupButton.hidden=true;$("tv-result-actions").append(backupButton);
  function feedback(id,message,isError=false){$(id).textContent=message;$(id).classList.toggle("error-text",isError);}
  function port(){const value=Number($("tv-port").value);if(!Number.isInteger(value)||value<1024||value>65535)throw new Error("로컬 포트는 1024~65535 사이의 정수로 입력하세요.");return value;}
  function sync(){
    const locked=state.busy||state.checking;
    for(const id of ["tv-check","tv-launch","tv-configure","tv-backtest","tv-port","tv-target","tv-symbol","tv-timeframe","tv-queue-indicator","tv-code-file"])$(id).disabled=locked;
    const apply=$("tv-personal-apply");if(apply)apply.disabled=locked;
    for(const button of $("tv-indicators").querySelectorAll("button"))button.disabled=locked;
  }
  function renderChart(chart){
    const box=$("tv-current-chart");box.replaceChildren();box.hidden=!chart;if(!chart)return;
    box.append(make("strong","",chart.symbol||"종목 확인 전"),make("span","",chart.timeframe?"주기 "+chart.timeframe:"주기 확인 전"));
    const studies=chart.studies||chart.indicators||[];
    if(Array.isArray(studies))box.append(make("span","",studies.length?studies.map(item=>typeof item==="string"?item:item.name||item.description||"지표").join(" · "):"추가 지표 없음"));
    if(studies.length){const details=make("details","tv-study-inputs"),summary=make("summary","","현재 지표의 입력값 보기"),pre=make("pre","",JSON.stringify(studies,null,2));details.append(summary,pre);box.append(details);}
  }
  async function check(){
    if(state.busy||state.checking)return;state.checking=true;sync();feedback("tv-connect-feedback","TradingView Desktop 연결과 현재 차트를 확인하고 있습니다.");
    try{
      const selected=$("tv-target").value;const result=await window.HyperpassApp.api("/api/tradingview/status?port="+port()+(selected?"&target_id="+encodeURIComponent(selected):""));state.lastStatus=result;
      if(Array.isArray(result.targets)){const target=$("tv-target");target.replaceChildren();const automatic=make("option","","열린 차트 자동 선택");automatic.value="";target.append(automatic);for(const item of result.targets){if(typeof item.id!=="string")continue;const option=make("option","",item.title||"TradingView 차트 "+(target.options.length));option.value=item.id;target.append(option);}if([...target.options].some(option=>option.value===selected))target.value=selected;$("tv-target-control").hidden=result.targets.length<2&&!selected;}
      const connected=result.connected===true||result.success===true;
      $("tv-connection-badge").textContent=connected?"Desktop 연결됨":"연결되지 않음";$("tv-connection-badge").classList.toggle("success",connected);
      renderChart(result.chart);feedback("tv-connect-feedback",connected?"열린 차트를 확인했습니다. 설정과 전략을 선택해 실행하세요.":result.error||result.message||"TradingView Desktop을 디버그 연결로 실행하고, 로그인한 차트를 열어 주세요.",!connected);
      if(result.capabilities?.launch===true)$("tv-launch").hidden=false;
    }catch(error){$("tv-connection-badge").textContent="연결 확인 실패";$("tv-connection-badge").classList.remove("success");feedback("tv-connect-feedback",error.message,true);}
    finally{state.checking=false;sync();}
  }
  function renderIndicators(){const list=$("tv-indicators");list.replaceChildren();if(!state.indicators.length){list.append(make("p","small-muted","반영할 지표가 없습니다. 종목과 주기만 변경할 수도 있습니다."));return;}state.indicators.forEach((item,index)=>{const row=make("div","tv-indicator-row"),copy=make("div");copy.append(make("strong","",indicatorNames[item.name]||item.name),make("small","",Object.keys(item.inputs).length?JSON.stringify(item.inputs):"기본 설정"));const remove=make("button","text-button","제외 ×");remove.type="button";remove.setAttribute("aria-label",(indicatorNames[item.name]||item.name)+" 목록에서 제외");remove.addEventListener("click",()=>{state.indicators.splice(index,1);renderIndicators();});row.append(copy,remove);list.append(row);});sync();}
  function queueIndicator(){
    try{
      if(state.indicators.length>=8)throw new Error("한 번에 지표 8개까지 설정할 수 있습니다.");
      const name=$("tv-indicator").value,raw=$("tv-indicator-inputs").value.trim();let inputs={};
      if(raw){try{inputs=JSON.parse(raw);}catch{throw new Error("고급 입력값은 JSON 객체로 입력하세요. 예: {\"in_0\": 20}");}if(!inputs||Array.isArray(inputs)||typeof inputs!=="object")throw new Error("고급 입력값은 입력 ID와 값으로 이루어진 객체여야 합니다.");}
      else if(indicatorLengths.get(name)){const length=Number($("tv-indicator-length").value);if(!Number.isInteger(length)||length<1||length>10000)throw new Error("지표 기간은 1~10000 사이의 정수로 입력하세요.");inputs={length};}
      state.indicators.push({name,inputs});renderIndicators();feedback("tv-input-feedback","지표를 목록에 추가했습니다. 차트 설정 적용을 누르면 TradingView에 반영합니다.");
    }catch(error){feedback("tv-input-feedback",error.message,true);}
  }
  const labels={net_profit:"순손익",netProfit:"순손익",net_profit_percent:"순수익률",netProfitPercent:"순수익률",total_return_pct:"총수익률",max_drawdown:"최대 낙폭",maxDrawdown:"최대 낙폭",max_drawdown_percent:"최대 낙폭률",max_drawdown_pct:"최대 낙폭률",total_trades:"거래 수",totalTrades:"거래 수",closed_trades:"완결 거래",winning_trades:"수익 거래",losing_trades:"손실 거래",percent_profitable:"수익 거래 비율",percentProfitable:"수익 거래 비율",win_rate:"승률",win_rate_pct:"승률",profit_factor:"수익지수",profitFactor:"수익지수",commission_paid:"수수료",sharpe_ratio:"샤프 비율",sortino_ratio:"소르티노 비율",buy_hold_return:"단순 보유 수익",buy_hold_return_percent:"단순 보유 수익률",buy_and_hold_return:"단순 보유 수익",buyAndHoldReturn:"단순 보유 수익",open_pl:"미실현 손익"};
  function completedLabel(job){const action=job.action||job.request?.action;if(action==="indicator")return "개인 지표 적용 완료";if(action==="configure"||job.result?.status==="configured")return "차트 적용 완료";if(action==="backtest"||job.result?.report)return "백테스트 완료";return "실행 완료";}
  function backtestPeriod(report){const range=report.settings?.dateRange?.backtest;const date=value=>{if(value===null||value===undefined)return null;const parsed=new Date(value);return Number.isNaN(parsed.getTime())?null:parsed.toISOString().slice(0,10);};const start=date(range?.from),end=date(range?.to);return start&&end?`백테스트 검증 기간: ${start} ~ ${end} (TradingView 제공 · UTC 날짜)`:"백테스트 검증 기간: TradingView에서 제공하지 않았습니다.";}
  function metricEntries(report){
    if(!report||typeof report!=="object")return [];
    const metrics=report.metrics||report.performance||report.summary||report;
    if(Array.isArray(metrics))return metrics.filter(row=>row&&typeof row==="object"&&(row.label||row.name)&&row.value!==undefined).slice(0,16).map(row=>[row.label||row.name,row.value]);
    return Object.entries(metrics).filter(([key,value])=>labels[key]&&(value===null||typeof value==="string"||typeof value==="number")).slice(0,16).map(([key,value])=>[labels[key],value===null?"미제공":typeof value==="number"&&Number.isFinite(value)?value.toLocaleString("ko-KR",{maximumFractionDigits:2})+(/percent|_pct$/.test(key)?"%":""):value]);
  }
  function renderResult(result){
    state.result=result;$("tv-result-summary").replaceChildren();$("tv-result-summary").hidden=false;$("tv-metrics").replaceChildren();$("tv-result-warnings").replaceChildren();
    const report=result.report||result.strategy_results||result.reports?.[0]||null;
    const failure=["compile_error","no_report","unverified_indicator","failed","error"].includes(result.status)||result.success===false;
    const indicatorJob=state.job?.request?.action==="indicator" || result.verification==="new_indicator_title_id_runtime_required";
    const summary=indicatorJob?(result.status==="applied"?`차트에 ${result.indicator.title} 지표를 추가하고 계산 상태를 확인했습니다.`:"개인 지표의 계산을 확인하지 못했습니다. 아래 오류와 TradingView 편집기를 확인하세요."):failure?(result.status==="compile_error"?"컴파일 오류가 있어 백테스트를 완료하지 못했습니다.":"TradingView에서 완료된 전략 보고서를 확인하지 못했습니다."):result.status==="configured"?"TradingView 차트 설정을 확인했습니다.":result.status==="partial"?"일부 설정만 반영됐습니다. 아래 경고를 확인하세요.":report?"TradingView에서 반환한 전략 결과입니다. 아래 지표의 기간과 실행 조건을 함께 확인하세요.":"TradingView의 실행 응답을 받았습니다. 원본 결과에서 적용 상태를 확인하세요.";
    $("tv-result-summary").append(make("p",failure?"error-text":"",summary));
    const entries=metricEntries(report);for(const[label,value]of entries){const card=make("div","tv-metric");card.append(make("span","",label),make("strong","",value));$("tv-metrics").append(card);}
    if(report){const identity=[report.strategy,report.currency?"통화: "+report.currency:""].filter(Boolean).join(" · ");if(identity)$("tv-result-summary").append(make("p","small-muted",identity));$("tv-result-summary").append(make("p","",backtestPeriod(report)));if(!entries.length)$("tv-result-summary").append(make("p","small-muted","요약 지표 형식을 자동 변환하지 않았습니다. 아래 원본 결과에서 TradingView가 반환한 값을 확인하세요."));}
    const warnings=Array.isArray(result.warnings)?[...result.warnings]:result.warnings?[result.warnings]:[];if(Array.isArray(report?.notes))warnings.push(...report.notes);for(const warning of warnings)$("tv-result-warnings").append(make("li","",typeof warning==="string"?warning:JSON.stringify(warning)));
    const errors=result.compile_errors||result.errors;$("tv-compile-errors").hidden=!errors||(Array.isArray(errors)&&!errors.length);$("tv-compile-errors").textContent=typeof errors==="string"?errors:errors?JSON.stringify(errors,null,2):"";
    if(result.previous_source!==undefined||result.source_backup||result.backup_path)$("tv-result-summary").append(make("p","small-muted","실행 전 편집기 코드가 결과 또는 백업 기록에 보관됐습니다."));
    if(result.chart)renderChart(result.chart);$("tv-result-json").textContent=JSON.stringify(result,null,2);$("tv-raw-result").hidden=false;$("tv-result-actions").hidden=false;
    $("tv-result-research").hidden=failure||!report||typeof window.HyperpassApp.useTradingView!=="function";
    document.dispatchEvent(new CustomEvent("hyperpass:tradingview-result",{detail:{job:state.job,result}}));
    return failure;
  }
  function displayJob(job){
    state.job=job;const terminal=["completed","failed","cancelled"].includes(job.status),failed=job.status==="failed";
    state.busy=!terminal;$("tv-job-progress").hidden=terminal;$("tv-job-retry").hidden=true;
    $("tv-job-badge").textContent=failed?"실행 실패":job.status==="completed"?completedLabel(job):job.status==="cancelled"?"중단됨":job.stage||"실행 중";
    $("tv-job-badge").classList.toggle("success",job.status==="completed");$("tv-job-badge").classList.toggle("changed",failed);
    feedback("tv-job-message",job.error||job.message||(terminal?"실행 기록을 확인하세요.":"TradingView의 응답을 기다리고 있습니다."),failed);
    $("tv-job-time").textContent=job.created_at?"시작: "+new Date(job.created_at).toLocaleString("ko-KR")+(job.finished_at?" · 종료: "+new Date(job.finished_at).toLocaleString("ko-KR"):""):"";
    if(terminal&&job.result){const incomplete=renderResult(job.result);if(incomplete){$("tv-job-badge").textContent=job.request?.action==="indicator"?"지표 적용 미확인":"백테스트 미완료";$("tv-job-badge").classList.remove("success");}}
    if(terminal){$("tv-raw-result").hidden=false;$("tv-result-json").textContent=JSON.stringify(job,null,2);$("tv-result-actions").hidden=false;const previous=job.previous_source??job.result?.previous_source;backupButton.hidden=typeof previous!=="string";if(typeof previous==="string"&&job.result?.previous_source===undefined){$("tv-result-summary").hidden=false;$("tv-result-summary").append(make("p","small-muted","실행 전 Pine 편집기 코드를 보관했습니다. 아래에서 원본 코드를 내려받을 수 있습니다."));}}
    if(terminal)refreshHistory();sync();return terminal;
  }
  async function poll(){
    if(!state.job)return;
    try{const job=await window.HyperpassApp.api("/api/tradingview/jobs/"+encodeURIComponent(state.job.id));if(!displayJob(job))state.timer=setTimeout(poll,1500);}
    catch(error){state.busy=false;$("tv-job-progress").hidden=true;$("tv-job-retry").hidden=false;$("tv-job-badge").textContent="상태 확인 중단";feedback("tv-job-message",error.message+" 실행이 끝났는지는 확인되지 않았습니다.",true);sync();}
  }
  async function run(action,indicatorCode){
    if(state.busy||state.checking)return;
    try{
      const symbol=window.HyperpassSymbols.selected(),code=action==="indicator"?indicatorCode:$("tv-code").value;
      if(!symbol)throw new Error("TradingView 종목을 입력하세요.");if(action==="backtest"&&!code.trim())throw new Error("실행할 Pine 전략 코드를 입력하세요.");
      const payload={action,port:port(),symbol,timeframe:$("tv-timeframe").value,indicators:action==="indicator"?[]:state.indicators.map(item=>({name:item.name,inputs:{...item.inputs}}))};if($("tv-target").value)payload.target_id=$("tv-target").value;if(action==="backtest"||action==="indicator")payload.code=code;
      state.busy=true;sync();feedback("tv-input-feedback","");$("tv-job-progress").hidden=false;$("tv-job-badge").textContent="요청 중";feedback("tv-job-message","TradingView 작업을 시작하고 있습니다.");
      $("tv-result-summary").hidden=true;$("tv-metrics").replaceChildren();$("tv-result-warnings").replaceChildren();$("tv-compile-errors").hidden=true;$("tv-result-actions").hidden=true;$("tv-raw-result").hidden=true;state.result=null;
      const job=await window.HyperpassApp.api("/api/tradingview/jobs",{method:"POST",body:payload});if(typeof job.id!=="string")throw new Error("실행 기록 번호를 확인하지 못했습니다.");
      if(!displayJob(job))state.timer=setTimeout(poll,1000);
    }catch(error){state.busy=false;sync();$("tv-job-progress").hidden=true;$("tv-job-badge").textContent="시작하지 못함";feedback("tv-input-feedback",error.message,true);feedback("tv-job-message",error.message,true);}
  }
  let historyLoading=false,historyReady=false;
  async function refreshHistory(){
    if(historyLoading)return;historyLoading=true;$("tv-history-refresh").disabled=true;
    try{const data=await window.HyperpassApp.api("/api/tradingview/jobs");if(!Array.isArray(data.jobs))throw new Error("저장된 실행 목록을 읽지 못했습니다.");const list=$("tv-history");list.replaceChildren();historyReady=true;const statusLabels={queued:"대기",running:"진행 중",failed:"실패",cancelled:"중단"};for(const job of data.jobs){if(typeof job.id!=="string")continue;const button=make("button","tv-history-item");button.type="button";button.append(make("strong","",(job.action==="configure"?"차트 설정":job.action==="indicator"?"개인 지표":"전략 백테스트")+(job.symbol?" · "+job.symbol:"")),make("span","",job.status==="completed"?completedLabel(job):statusLabels[job.status]||job.status||"상태 미확인"),make("small","",job.created_at?new Date(job.created_at).toLocaleString("ko-KR"):""));button.addEventListener("click",()=>openJob(job.id));list.append(button);}if(!data.jobs.length)list.append(make("p","small-muted","아직 저장된 TradingView 실행이 없습니다."));feedback("tv-history-feedback","");}catch(error){feedback("tv-history-feedback",error.message,true);}finally{historyLoading=false;$("tv-history-refresh").disabled=false;}
  }
  async function openJob(id){
    if(state.busy&&state.job?.id!==id){feedback("tv-history-feedback","현재 작업이 끝난 뒤 다른 실행 기록을 열어 주세요.",true);return;}
    clearTimeout(state.timer);window.HyperpassApp.selectWorkspace("tradingview");
    try{const job=await window.HyperpassApp.api("/api/tradingview/jobs/"+encodeURIComponent(id));$("tv-result-summary").hidden=true;$("tv-metrics").replaceChildren();$("tv-result-warnings").replaceChildren();$("tv-compile-errors").hidden=true;$("tv-result-actions").hidden=true;$("tv-raw-result").hidden=true;state.result=null;if(!displayJob(job))state.timer=setTimeout(poll,1000);}catch(error){feedback("tv-job-message",error.message,true);}
  }
  $("tv-check").addEventListener("click",check);$("tv-target").addEventListener("change",check);$("tv-configure").addEventListener("click",()=>run("configure"));$("tv-backtest").addEventListener("click",()=>run("backtest"));$("tv-queue-indicator").addEventListener("click",queueIndicator);$("tv-history-refresh").addEventListener("click",refreshHistory);$("tv-job-retry").addEventListener("click",()=>{if(state.job){state.busy=true;sync();poll();}});
  $("tv-indicator").addEventListener("change",()=>{
    const input=$("tv-indicator-length"), length=indicatorLengths.get($("tv-indicator").value);
    input.disabled=!length; input.value=length||""; input.placeholder=length?"":"TradingView 기본값";
    $("tv-indicator-inputs").value="";
  });
  $("tv-code-file").addEventListener("change",async()=>{const file=$("tv-code-file").files[0];if(!file)return;if(file.size>200000){feedback("tv-input-feedback","Pine 파일은 200KB 이하로 선택하세요.",true);return;}try{$("tv-code").value=await file.text();feedback("tv-input-feedback","파일을 읽었습니다. 전략을 확인하고 실행해 주세요.");}catch{feedback("tv-input-feedback","파일을 읽지 못했습니다.",true);}});
  function downloadFile(content,name,mime){const blob=new Blob([content],{type:mime}),url=URL.createObjectURL(blob),link=make("a");link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $("tv-result-download").addEventListener("click",()=>{if(state.job)downloadFile(JSON.stringify(state.job,null,2),"hyperpass-tradingview-result.json","application/json");else if(state.result)downloadFile(JSON.stringify(state.result,null,2),"hyperpass-tradingview-result.json","application/json");});
  backupButton.addEventListener("click",()=>{const previous=state.job?.previous_source??state.result?.previous_source;if(typeof previous==="string")downloadFile(previous,"hyperpass-tradingview-before-run.pine","text/plain;charset=utf-8");});
  $("tv-result-research").addEventListener("click",()=>{if(state.result&&typeof window.HyperpassApp.useTradingView==="function")window.HyperpassApp.useTradingView(state.job.id,state.result);});
  $("tv-launch").addEventListener("click",async()=>{if(state.busy||state.checking)return;state.checking=true;sync();try{feedback("tv-connect-feedback","TradingView Desktop의 연결 실행을 요청하고 있습니다.");const result=await window.HyperpassApp.api("/api/tradingview/launch",{method:"POST",body:{port:port()}});feedback("tv-connect-feedback",result.message||"Desktop 실행을 요청했습니다. 로그인한 차트를 열고 연결 확인을 눌러 주세요.");}catch(error){feedback("tv-connect-feedback",error.message,true);}finally{state.checking=false;sync();}});
  const loadWhenVisible=()=>{if(!host.hidden&&!historyReady&&!historyLoading)refreshHistory();};new MutationObserver(loadWhenVisible).observe(host,{attributes:true,attributeFilter:["hidden"]});document.addEventListener("hyperpass:workspace-change",loadWhenVisible);
  window.HyperpassTradingView={applyIndicator:code=>run("indicator",code),check,open:openJob,refreshHistory,openResult:result=>renderResult(result),enableLaunch:()=>{$("tv-launch").hidden=false;}};renderIndicators();sync();loadWhenVisible();
})();
