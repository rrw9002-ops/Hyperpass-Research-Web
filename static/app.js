"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const state = {csrf: "", connected: false, model: "gpt-5-mini", roles: [], sources: [], aiProviders: [], category: "stock", roleOverrides: {}, runs: [], selected: null, run: null, timer: null, polling: false, submitting: false, alive: true, chart: null, tvJob:null};
  const DEFAULT_ROLES = [
    ["fundamental-analyst", "Fundamental Analyst", "기업 · 재무 · 회계 품질"], ["technical-analyst", "Technical Analyst", "가격 · 추세 · 거래량"], ["news-analyst", "News Analyst", "공시 · 사건 · 내러티브"],
    ["macro-analyst", "Macro Analyst", "금리 · 환율 · 전달 경로"], ["instrument-analyst", "Instrument Analyst", "ETF · 지수 · 상품 구조"], ["valuation-analyst", "Valuation Analyst", "가치 · 기대 · 민감도"],
    ["portfolio-manager", "Portfolio Manager", "편입 적합성 · 집중도"], ["risk-manager", "Risk Manager", "독립 위험 · 하방 · 한계"], ["judgment-reviewer", "Judgment Reviewer", "독립 검토 · 논리 · 반대 근거"]
  ].map(([id, name, description]) => ({id, name, description}));
  const CATEGORIES = {
    stock: {name:"종목", target:"종목·기업", placeholder:"예: 애플 (AAPL), 삼성전자 (005930)", help:"기업의 사업·실적·가치·위험을 살펴봅니다. 미래 수익이나 매매 체결을 보장하지 않습니다.", example:"애플(AAPL)의 향후 1년 사업 전망과 현재 주가에 반영된 기대를 검토해줘. 반대 근거와 판단을 바꿀 조건을 포함해줘."},
    market: {name:"시장·거시", target:"시장·거시 주제", placeholder:"예: 미국 금리, 한국 증시, 달러 강세", help:"금리·환율·경기·산업 변화가 시장에 전달되는 경로를 분석합니다. 종목 코드는 필수가 아닙니다.", example:"미국 금리 변화가 한국 수출 기업과 주식시장에 미치는 영향을 분석해줘. 확인된 사실과 가정을 구분해줘."},
    instrument: {name:"ETF·상품", target:"상품·비교 대상", placeholder:"예: SPY와 VOO, 반도체 ETF", help:"ETF·지수·상품 구조, 비용, 추적 방식과 고유 위험을 검토합니다. 주문이나 계좌 연결은 하지 않습니다.", example:"SPY와 VOO를 장기 보유 관점에서 비교해줘. 비용, 구조, 유동성과 자료 기준일을 포함해줘."},
    portfolio: {name:"포트폴리오", target:"보유 구성·가상 시나리오", placeholder:"예: 현금 40%, 주식 ETF 60%", help:"제공한 보유 맥락·기간·제약을 바탕으로 집중도와 위험을 검토합니다. 계좌번호 없이 비중·가상 구성만 입력하세요.", example:"가상 포트폴리오가 현금 40%, 미국 주식 ETF 60%일 때 1년 관점의 집중도와 유동성 위험을 검토해줘. 위험 담당자의 독립 검토를 포함해줘."},
    news: {name:"뉴스·이벤트", target:"뉴스·공시·사건", placeholder:"예: 기업 실적 발표, 규제 변화", help:"공시·사건의 사실관계, 시간 순서와 영향을 검토합니다. 기사 URL이나 원문을 참고 자료에 추가할 수 있습니다.", example:"최근 애플 실적 발표의 핵심 변화와 시장 기대의 차이를 분석해줘. 공시와 해석, 확인되지 않은 주장을 구분해줘."},
    free: {name:"자유질문", target:"분석 대상 (선택)", placeholder:"예: 궁금한 투자 연구 주제", help:"투자·시장 관련 사실 확인, 비교, 개념 설명과 연구 질문을 자유롭게 입력하세요. 계좌 조회·주문·수익 보장은 범위 밖입니다.", example:"기업의 매출 성장과 현금흐름이 엇갈릴 때 어떤 자료를 먼저 확인해야 하는지 설명해줘."}
  };
  const AI_NAMES = {openai:"OpenAI · GPT",anthropic:"Anthropic · Claude",gemini:"Google · Gemini"};
  const statusNames = {queued: "준비 중", running: "분석 중", planning: "팀 구성 중", researching: "근거 수집 중", reviewing: "독립 검토 중", completed: "완료", complete: "완료", accepted: "채택", cancelled: "중단됨", failed: "실패", error: "오류", blocked: "추가 확인 필요", budget_exhausted: "호출 상한 도달", interrupted: "중단됨", incomplete: "미완료", idle: "대기", pending: "대기", started: "작업 중", revising: "보완 중", revise: "보완 요청", waiting: "대기"};
  const terminal = new Set(["completed", "complete", "cancelled", "failed", "error", "blocked", "budget_exhausted", "interrupted", "incomplete"]);
  const el = (tag, cls, text) => { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = String(text); return node; };
  const asText = value => typeof value === "string" ? value : value == null ? "" : JSON.stringify(value, null, 2);
  const isActive = run => run && !terminal.has(run.status);
  const friendlyStatus = value => statusNames[value] || value || "대기";
  const roleName = id => id === "head-manager" || id === "head" || id === "coordinator" ? "Head Manager" : (state.roles.find(r => r.id === id)?.name || id || "시스템");
  const timeLabel = value => { if (!value) return ""; const date = new Date(value); return Number.isNaN(+date) ? "" : date.toLocaleString("ko-KR", {month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit"}); };
  function error(message) { $("global-error").textContent = message; $("global-error").hidden = !message; }
  async function api(path, options = {}) {
    const method = options.method || "GET";
    const headers = {"Accept": "application/json"};
    if (method !== "GET") { headers["Content-Type"] = "application/json"; headers["X-CSRF-Token"] = state.csrf; }
    let response;
    try { response = await fetch(path, {method, headers, body: options.body === undefined ? undefined : JSON.stringify(options.body), credentials:"same-origin", cache:"no-store"}); }
    catch { throw new Error("로컬 서버에 연결할 수 없습니다. 실행 창이 열려 있는지 확인한 뒤 다시 시도하세요."); }
    let data;
    try { data = await response.json(); } catch { throw new Error("서버 응답을 읽지 못했습니다. 페이지를 새로고침해 주세요."); }
    if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : data.error?.message || data.message || `요청 실패 (${response.status})`);
    return data;
  }
  function renderConnection() {
    const connected = state.aiProviders.filter(p => p.connected);
    state.connected = connected.length > 0 || state.connected;
    $("connection-button").classList.toggle("connected", state.connected);
    $("connection-label").textContent = connected.length ? `${connected.length}개 AI 연결됨` : state.connected ? `${state.model} 연결됨` : "AI 연결 필요";
    $("onboarding").hidden = state.connected;
  }
  const aiInfo = id => state.aiProviders.find(p => p.id === id);
  const modelId = model => typeof model === "string" ? model : model.id || model.name || "";
  const defaultModel = p => p?.model || p?.default_model || p?.suggested_model || (p?.id === "openai" ? "gpt-5-mini" : "");
  function modelList(id, target) {
    const list = $(target); list.replaceChildren();
    for (const item of aiInfo(id)?.models || []) { const option = el("option"); option.value = modelId(item); if (typeof item === "object" && item.name && item.name !== option.value) option.label = item.name; list.append(option); }
  }
  function renderConnectProvider(resetModel = false) {
    const id = $("connect-provider").value, provider = aiInfo(id);
    $("ai-provider-status").textContent = provider?.connected ? `${AI_NAMES[id]} · 실제 API 연결 확인됨` : `${AI_NAMES[id]} · 아직 연결하지 않았습니다.`;
    $("disconnect-button").hidden = !provider?.connected;
    $("refresh-models").disabled = false;
    if (resetModel) $("model").value = defaultModel(provider || {id});
    $("model").placeholder = id === "anthropic" ? "Claude 모델 ID" : id === "gemini" ? "Gemini 모델 ID" : "OpenAI 모델 ID";
    modelList(id,"connect-model-list");
  }
  function reasoningOptions(provider,model) {
    const entry=(aiInfo(provider)?.models || []).find(x=>modelId(x)===model);
    return entry?.reasoning_options || [{id:"default",label:"모델 기본값"}];
  }
  function fillReasoning(select,options,prior="default") {
    select.replaceChildren();
    const choices=[{id:"default",label:"모델 기본값"},...(options || []).filter(o=>(o.id || o.value || o)!=="default")];
    for(const choice of choices){const option=el("option","",typeof choice==="string"?choice:choice.label || choice.id);option.value=typeof choice==="string"?choice:choice.id || choice.value;select.append(option);}
    select.value=choices.some(o=>(o.id || o.value || o)===prior)?prior:"default";
  }
  let reasoningRequest=0;
  async function refreshReasoning() {
    const provider=$("run-provider").value,model=$("run-model").value.trim(),prior=$("run-reasoning").value;
    const revision=++reasoningRequest;fillReasoning($("run-reasoning"),reasoningOptions(provider,model),prior);
    if(!provider || !model)return;
    try{const data=await api(`/api/ai/${encodeURIComponent(provider)}/reasoning?model=${encodeURIComponent(model)}`);if(revision===reasoningRequest)fillReasoning($("run-reasoning"),data.options || [],prior);}catch{ /* The catalog/default remains valid; custom unsupported effort is never invented. */ }
  }
  function renderRoleAssignments() {
    const target = $("role-model-assignments"); target.replaceChildren();
    const roles = [{id:"head-manager",name:"Head Manager"},...(state.roles.length ? state.roles : DEFAULT_ROLES)];
    for (const role of roles) {
      const row = el("div","role-assignment"); row.append(el("strong","",role.name));
      const select = el("select"); select.setAttribute("aria-label",`${role.name} 담당 AI`);
      const inherit = el("option","","기본 AI 상속"); inherit.value=""; select.append(inherit);
      for (const p of state.aiProviders.filter(p=>p.connected)) { const o=el("option","",p.name || AI_NAMES[p.id] || p.id); o.value=p.id; select.append(o); }
      const input=el("input"); input.setAttribute("aria-label",`${role.name} 모델`); input.maxLength=150; input.placeholder="기본 모델 상속";
      const list=el("datalist"); list.id=`role-model-list-${role.id}`; input.setAttribute("list",list.id);
      const prior=state.roleOverrides[role.id]; select.value=prior?.provider || ""; input.value=prior?.model || ""; input.disabled=!select.value;
      const reasoning=el("select");reasoning.setAttribute("aria-label",`${role.name} 추론 강도`);reasoning.disabled=!select.value;fillReasoning(reasoning,reasoningOptions(select.value,input.value),prior?.reasoning || "default");
      function updateList() { list.replaceChildren(); for(const item of aiInfo(select.value)?.models || []) { const option=el("option"); option.value=modelId(item); list.append(option); } }
      updateList();
      select.addEventListener("change",()=>{ input.disabled=!select.value; reasoning.disabled=!select.value; input.value=select.value?defaultModel(aiInfo(select.value)):""; fillReasoning(reasoning,reasoningOptions(select.value,input.value)); if(select.value) state.roleOverrides[role.id]={provider:select.value,model:input.value,reasoning:"default"}; else delete state.roleOverrides[role.id]; updateList(); renderModelCapability(); });
      input.addEventListener("input",()=>{if(select.value)state.roleOverrides[role.id]={provider:select.value,model:input.value.trim(),reasoning:reasoning.value};});
      input.addEventListener("change",async()=>{const model=input.value.trim();fillReasoning(reasoning,reasoningOptions(select.value,model));if(select.value){try{const data=await api(`/api/ai/${encodeURIComponent(select.value)}/reasoning?model=${encodeURIComponent(model)}`);if(input.value.trim()===model)fillReasoning(reasoning,data.options || []);}catch{}state.roleOverrides[role.id]={provider:select.value,model,reasoning:reasoning.value};}});
      reasoning.addEventListener("change",()=>{if(select.value)state.roleOverrides[role.id]={provider:select.value,model:input.value.trim(),reasoning:reasoning.value};});
      row.append(select,input,reasoning,list); target.append(row);
    }
  }
  function renderModelCapability() {
    const p=aiInfo($("run-provider").value);
    const caps=p?.capabilities || {};
    const supports = typeof caps === "object" ? (caps.web_search ?? caps.native_web_search ?? caps.search) : undefined;
    $("model-capability").textContent = !p?.connected ? "사용할 AI를 먼저 등록하세요. 연결된 서비스만 선택할 수 있습니다." : `${p.name || AI_NAMES[p.id]}에 등록한 키로 이번 질문을 실행합니다. ${supports === false ? "이 연결은 모델의 직접 웹 검색을 제공하지 않습니다. 연결한 데이터·제공 자료를 사용하세요." : "웹 검색 지원은 선택한 서비스와 모델에 따라 달라집니다."} 역할별로 다른 AI를 지정하면 해당 AI에도 질문과 필요한 근거가 전달됩니다.`;
  }
  function renderAISelection() {
    const select=$("run-provider"), prior=select.value, priorModel=$("run-model").value;
    select.replaceChildren();
    const connected=state.aiProviders.filter(p=>p.connected);
    if(!connected.length){const empty=el("option","","연결한 AI가 없습니다"); empty.value=""; select.append(empty);}
    for(const p of connected){const option=el("option","",p.name || AI_NAMES[p.id] || p.id);option.value=p.id;select.append(option);}
    select.value=connected.some(p=>p.id===prior)?prior:(connected[0]?.id || "");
    $("run-model").value=select.value===prior && priorModel?priorModel:defaultModel(aiInfo(select.value));
    $("run-model").disabled=!connected.length; modelList(select.value,"run-model-list"); renderRoleAssignments(); renderModelCapability(); renderConnectProvider(); renderConnection(); refreshReasoning();
  }
  async function refreshAI() {
    const data=await api("/api/ai"); state.aiProviders=Array.isArray(data.providers)?data.providers:[];
    state.connected=state.aiProviders.some(p=>p.connected); renderAISelection();
  }
  function renderCategories() {
    $("question-categories").replaceChildren();
    for(const [id,category] of Object.entries(CATEGORIES)){const button=el("button",`category-button${id===state.category?" selected":""}`,category.name);button.type="button";button.setAttribute("aria-pressed",String(id===state.category));button.addEventListener("click",()=>{state.category=id;renderCategories();});$("question-categories").append(button);}
    const category=CATEGORIES[state.category];$("category-help").textContent=category.help;$("question").placeholder=category.example;
  }
  function modelConfiguration() {
    const config={default:{provider:$("run-provider").value,model:$("run-model").value.trim(),reasoning:$("run-reasoning").value || "default"},roles:{}};
    if(!aiInfo(config.default.provider)?.connected || !config.default.model) throw new Error("이번 질문에 사용할 연결된 AI와 모델을 선택해 주세요.");
    for(const [role,assignment] of Object.entries(state.roleOverrides)){if(!aiInfo(assignment.provider)?.connected || !assignment.model.trim())throw new Error(`${roleName(role)}의 AI 연결과 모델을 확인해 주세요.`);config.roles[role]={provider:assignment.provider,model:assignment.model.trim(),reasoning:assignment.reasoning || "default"};}
    return config;
  }
  function renderProgress(run) {
    $("run-banner").hidden=!run; if(!run)return;
    const completed=run.status==="completed" || run.status==="complete",active=!!isActive(run);
    const lastProgress=[...(run.events || [])].reverse().find(e=>e.progress)?.progress;
    const progress=run.progress || lastProgress || {};
    const known=Number.isFinite(Number(progress.percent)) && progress.percent!==null && progress.percent!==undefined;
    const percent=completed?100:known?Math.min(95,Math.max(0,Number(progress.percent))):0;
    $("run-banner").className=`run-banner ${completed?"success":active?"working":"stopped"}`;
    $("run-stage").textContent=run.mode==="demo"?"SAMPLE · 고정 예제":"LIVE RESEARCH · 실제 분석";
    const titles={blocked:"분석이 중단됐습니다 · 최종 보고서 없음",failed:"오류로 중단됐습니다 · 최종 보고서 없음",error:"오류로 중단됐습니다 · 최종 보고서 없음",cancelled:"사용자가 분석을 중단했습니다",budget_exhausted:"호출 한도에 도달했습니다 · 분석 미완료",interrupted:"앱 종료로 중단됐습니다 · 분석 미완료"};
    $("run-banner-title").textContent=completed?(run.mode==="demo"?"샘플 실행 완료 · 실제 AI 분석 아님":"최종 보고서가 완성됐습니다"):active?"분석 진행 중":titles[run.status] || "분석 미완료";
    $("progress-value").textContent=completed?"100%":known?`${Math.round(percent)}%`:"—";
    $("run-progress").value=percent;$("run-progress").setAttribute("aria-valuetext",completed?"완료":known?`단계 기준 추정 ${Math.round(percent)}퍼센트`:(active?"진행률 집계 중":"이전 실행의 진행률 기록 없음"));
    const latest=[...(run.events || [])].reverse().find(e=>e.message && (e.type==="finished"||e.type==="error"));
    const oldParts=typeof run.report==="string"?run.report.split(/\n\s*\n/):[];const statusPart=oldParts.findIndex(p=>p.trim().startsWith("상태:"));const legacyReason=statusPart>=0?(oldParts[statusPart+1] || "").trim():"";
    $("run-banner-detail").textContent=completed?"통합 보고서와 역할별 근거를 아래에서 확인하고 내려받을 수 있습니다.":active?`${progress.label || "팀이 자료와 근거를 검토하고 있습니다."}${progress.current_role?` · ${roleName(progress.current_role)}`:""}`:(run.reason || run.error || legacyReason || progress.label || latest?.message || "저장된 내용은 중간 기록입니다. 진행 기록에서 중단 원인을 확인하세요.");
    $("progress-caption").textContent=completed?(run.mode==="demo"?"고정 예제 재생과 저장 완료":"이번 질문의 분석 절차와 결과 저장 완료"):known?"단계 기준 추정치입니다. 보완·재검토가 추가되면 같은 비율에서 대기할 수 있습니다.":"이전 버전 실행에는 진행률이 기록되지 않았습니다. 현재 상태는 위에 표시됩니다.";
    const calls=run.usage?.calls ?? progress.calls_completed;const cap=run.max_calls || progress.call_limit;
    $("progress-calls").textContent=calls!==undefined?`모델 호출 ${calls}${cap?` / 상한 ${cap}`:""}회`:"";
  }
  function renderRoles(run = null) {
    const last = new Map();
    for (const event of run?.events || []) {
      const role = event.role || event.agent;
      if (role) last.set(role, event.status || (event.type === "artifact" ? "completed" : event.type === "error" ? "error" : "running"));
    }
    for (const artifact of run?.artifacts || []) if (artifact.role && !last.has(artifact.role)) last.set(artifact.role, artifact.status || "completed");
    const grid = $("role-grid"); grid.replaceChildren();
    (state.roles.length ? state.roles : DEFAULT_ROLES).forEach((role, index) => {
      const status = last.get(role.id) || "idle";
      const done = ["completed", "complete", "accepted"].includes(status);
      const failed = ["failed", "error", "blocked"].includes(status);
      const active = last.has(role.id) && !done && !failed && isActive(run);
      const card = el("div", `role-card${done ? " complete" : active ? " active" : failed ? " failed" : ""}`);
      card.append(el("span", "role-number", String(index + 1).padStart(2, "0")));
      const copy = el("div", "role-text"); copy.append(el("strong", "", role.name), el("small", "", role.description));
      const roleArtifact=[...(run?.artifacts || [])].reverse().find(a=>a.role===role.id);const assignment=run?.model_config?.roles?.[role.id] || run?.model_config?.default;
      if(roleArtifact?.model || assignment?.model)copy.append(el("small","role-model-label",run.mode==="demo"?"고정 샘플":`${AI_NAMES[roleArtifact?.provider || assignment?.provider] || roleArtifact?.provider || assignment?.provider || ""} · ${roleArtifact?.model || assignment?.model}`));
      card.append(copy);
      card.append(el("span", "role-state", friendlyStatus(status))); grid.append(card);
    });
    $("head-card").classList.toggle("active", !!isActive(run));
    $("head-status").textContent = run ? friendlyStatus(run.status) : "준비";
  }
  function renderHistory() {
    const history = $("history"); history.replaceChildren(); $("history-count").textContent = state.runs.length;
    if (!state.runs.length) { const empty = el("p", "muted history-empty", "첫 번째 질문을 시작하면\n리서치 기록이 여기에 쌓입니다."); empty.style.whiteSpace = "pre-line"; history.append(empty); return; }
    for (const run of state.runs) {
      const button = el("button", `history-item${state.selected === run.id ? " current" : ""}`);
      button.type = "button"; button.title = run.question || "리서치";
      button.append(el("strong", "", run.question || "리서치"), el("small", "", `${run.mode === "demo" ? "샘플 · " : ""}${friendlyStatus(run.status)} · ${timeLabel(run.created_at)}`));
      button.addEventListener("click", () => selectRun(run.id)); history.append(button);
    }
  }
  function inline(parent, text) {
    // Only explicit HTTP(S) markdown links become anchors; arbitrary HTML stays text.
    const pattern = /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([^*\n]+)\*\*|`([^`\n]+)`/g;
    let cursor = 0, match;
    while ((match = pattern.exec(text))) {
      parent.append(document.createTextNode(text.slice(cursor, match.index)));
      if (match[1]) {
        try { const url = new URL(match[2]); if (!["http:", "https:"].includes(url.protocol)) throw new Error(); const a = el("a", "", match[1]); a.href = url.href; a.target = "_blank"; a.rel = "noopener noreferrer"; parent.append(a); }
        catch { parent.append(document.createTextNode(match[0])); }
      } else if (match[3]) parent.append(el("strong", "", match[3]));
      else parent.append(el("code", "", match[4]));
      cursor = pattern.lastIndex;
    }
    parent.append(document.createTextNode(text.slice(cursor)));
  }
  function markdown(target, text) {
    target.replaceChildren(); const lines = asText(text).split(/\r?\n/); let code = null, list = null;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.startsWith("```")) { if (code) { target.append(code); code = null; } else code = el("pre"); list = null; continue; }
      if (code) { code.textContent += line + "\n"; continue; }
      if (!line.trim()) { list = null; continue; }
      if (/^\|/.test(line) && i + 1 < lines.length && /^\|?\s*:?-{3}/.test(lines[i+1])) {
        const table = el("table"), thead = el("thead"), tr = el("tr");
        const cells = row => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(x => x.trim());
        for (const value of cells(line)) { const th = el("th"); inline(th, value); tr.append(th); } thead.append(tr); table.append(thead); i++;
        const tbody = el("tbody"); while (i + 1 < lines.length && /^\|/.test(lines[i+1])) { i++; const row = el("tr"); for (const value of cells(lines[i])) { const td = el("td"); inline(td, value); row.append(td); } tbody.append(row); } table.append(tbody); target.append(table); list = null; continue;
      }
      const heading = /^(#{1,6})\s+(.*)$/.exec(line), bullet = /^\s*(?:[-*]|\d+\.)\s+(.*)$/.exec(line);
      if (heading) { const h = el(`h${Math.min(heading[1].length, 4)}`); inline(h, heading[2]); target.append(h); list = null; }
      else if (/^---+$/.test(line.trim())) { target.append(el("hr")); list = null; }
      else if (bullet) { if (!list) { list = el("ul"); target.append(list); } const li = el("li"); inline(li, bullet[1]); list.append(li); }
      else { list = null; const p = el(line.startsWith("> ") ? "blockquote" : "p"); inline(p, line.startsWith("> ") ? line.slice(2) : line); target.append(p); }
    }
    if (code) target.append(code);
  }
  function renderArtifacts(artifacts) {
    $("artifact-count").textContent = artifacts.length; $("artifacts").replaceChildren();
    if (!artifacts.length) { $("artifacts").append(el("p", "muted", "역할별 분석이 완료되면 근거와 보고서가 여기에 표시됩니다.")); return; }
    for (const artifact of artifacts) {
      const card = el("details", "artifact-card"), summary = el("summary");
      summary.append(el("strong", "", roleName(artifact.role)), el("small", "", `${artifact.version ? `v${artifact.version} · ` : ""}${friendlyStatus(artifact.state || artifact.status || artifact.handoff_state || "pending")}`));
      const body = el("div", "artifact-body"), meta = el("div", "artifact-meta", [artifact.id || artifact.artifact_id, artifact.created_at ? timeLabel(artifact.created_at) : "", artifact.evidence_readiness ? `근거 준비도: ${artifact.evidence_readiness}` : "", artifact.model ? (state.run?.mode==="demo"?"고정 샘플":`${AI_NAMES[artifact.provider] || artifact.provider || "AI"} · ${artifact.model}`) : "", artifact.reasoning && artifact.reasoning !== "default" ? `추론: ${artifact.reasoning}` : ""].filter(Boolean).join(" · "));
      body.append(meta); const content = el("div", "report-content"); markdown(content, artifact.report || artifact.content || artifact.text || artifact.markdown || artifact); body.append(content);
      const citations = artifact.citations || artifact.sources || [];
      if (Array.isArray(citations) && citations.length) { const sources = el("div", "sources"); sources.append(el("strong", "", "참고 출처")); for (const source of citations) { const url = typeof source === "string" ? source : source.url; try { const parsed = new URL(url); if (!["https:", "http:"].includes(parsed.protocol)) continue; const a = el("a", "", source.title || parsed.hostname); a.href = parsed.href; a.target = "_blank"; a.rel = "noopener noreferrer"; sources.append(a); } catch {} } body.append(sources); }
      if (artifact.search_suggestions_html && state.run?.id && artifact.id) {
        const suggestions=el("section","search-suggestions"), frame=el("iframe","search-suggestions-frame");
        suggestions.append(el("strong","","Google 검색 제안"));
        frame.title="Google 검색 제안"; frame.setAttribute("sandbox","allow-popups allow-popups-to-escape-sandbox");
        frame.referrerPolicy="no-referrer"; frame.loading="lazy";
        frame.src=`/api/runs/${encodeURIComponent(state.run.id)}/artifacts/${encodeURIComponent(artifact.id)}/search-suggestions`;
        suggestions.append(frame); body.append(suggestions);
      }
      card.append(summary, body); $("artifacts").append(card);
    }
  }
  function renderEvents(events) {
    $("event-count").textContent = events.length; const timeline = $("events"); const nearBottom = $("view-activity").scrollHeight - $("view-activity").scrollTop - $("view-activity").clientHeight < 100; timeline.replaceChildren();
    if (!events.length) { timeline.append(el("li", "", "분석을 시작하면 실제 실행 단계가 표시됩니다.")); return; }
    for (const event of events) { const li = el("li", event.type === "error" || event.status === "failed" ? "event-error" : ""); li.append(el("strong", "", `${roleName(event.role || event.agent)}${event.status ? ` · ${friendlyStatus(event.status)}` : ""}`), el("small", "", timeLabel(event.time || event.timestamp || event.created_at)), el("p", "", event.message || event.detail || event.type || "진행 상태 변경")); timeline.append(li); }
    if (nearBottom) $("view-activity").scrollTop = $("view-activity").scrollHeight;
  }
  function renderRun(run) {
    state.run = run; renderProgress(run); renderRoles(run); renderHistory(); $("run-meta").hidden = false;
    $("run-status").textContent = friendlyStatus(run.status); $("run-mode").textContent = run.mode === "demo" ? "화면 체험 · 고정 샘플" : "실제 API 분석";
    const usage = run.usage || {}; const tokens = usage.total_tokens ?? ((usage.input_tokens || 0) + (usage.output_tokens || 0));
    const selectedModel=run.model_config?.default;
    $("run-usage").textContent = `${usage.calls ?? usage.api_calls ?? "—"} 호출${tokens ? ` · ${Number(tokens).toLocaleString()} tokens` : ""}${selectedModel?.model?` · ${selectedModel.model} · 추론 ${selectedModel.reasoning || "default"}`:""}`;
    const active = !!isActive(run); $("cancel-button").hidden = !active; $("start-button").disabled = active || state.submitting;
    $("export-button").hidden = !run.report; $("export-button").textContent = run.status === "completed" ? "최종 보고서 저장 ↓" : "중간 기록 저장 ↓"; $("tab-report").textContent = run.status === "completed" ? "최종 보고서" : "중간 기록"; $("export-button").href = `/api/runs/${encodeURIComponent(run.id)}/export`;
    const content = $("report-content");
    if (run.report) markdown(content, run.report);
    else { content.replaceChildren(); const box = el("div", "progress-report"); const h = el("h3"); if (active) h.append(el("span", "pulse")); h.append(document.createTextNode(active ? "팀이 근거를 검토하고 있습니다." : friendlyStatus(run.status))); box.append(h, el("p", "", run.error || (active ? "역할별 근거와 진행 기록 탭에서 현재 작업을 확인할 수 있습니다. 이 창을 닫아도 서버가 실행 중이면 작업은 계속됩니다." : "완료된 통합 보고서가 없습니다. 진행 기록과 역할별 근거를 확인하세요."))); content.append(box); }
    if (run.status !== "completed" && run.report) content.prepend(el("p", "incomplete-notice", "최종 보고서가 아닙니다. 이 실행은 완료되지 않았으며 아래는 저장된 중간 기록입니다."));
    if (run.mode === "demo") { const note = el("p", "sample-notice", "화면 체험용 고정 샘플입니다. AI 분석이나 실시간 데이터 조회 결과가 아닙니다."); content.prepend(note); }
    if (run.error && run.report) content.prepend(el("p", "sample-notice", run.error));
    renderArtifacts(run.artifacts || []); renderEvents(run.events || []);
  }
  async function selectRun(id) {
    selectWorkspace('research');
    state.selected = id; clearTimeout(state.timer); error("");
    try { const run = await api(`/api/runs/${encodeURIComponent(id)}`); if (state.selected !== id) return; renderRun(run); if (isActive(run)) schedulePoll(); }
    catch (e) { error(e.message); }
  }
  function schedulePoll() { clearTimeout(state.timer); if (state.alive) state.timer = setTimeout(poll, 1500); }
  async function poll() {
    if (state.polling || !state.selected) return; state.polling = true; const id = state.selected;
    try { const run = await api(`/api/runs/${encodeURIComponent(id)}`); if (state.selected !== id) return; renderRun(run); if (isActive(run)) schedulePoll(); else await refreshStatus(false); }
    catch (e) { error(e.message); if (state.selected === id) state.timer = setTimeout(poll, 5000); }
    finally { state.polling = false; }
  }
  async function refreshStatus(restore = false) {
    const data = await api("/api/status"); state.csrf = data.csrf; state.connected = !!data.connected; state.model = data.model || "gpt-5-mini"; state.roles = Array.isArray(data.roles) && data.roles.length ? data.roles : DEFAULT_ROLES; state.runs = data.runs || [];
    renderConnection(); renderHistory(); renderRoles(state.run); window.HyperpassBrain?.refresh();
    if (restore) { const active = typeof data.active_run === "string" ? data.active_run : data.active_run?.id; if (active) await selectRun(active); else if (state.runs.length) await selectRun((state.runs.find(r => r.mode === "live") || state.runs[0]).id); }
  }
  async function start(mode) {
    if (state.submitting || isActive(state.run)) return;
    if (mode === "live" && !state.aiProviders.some(p => p.connected)) { openConnection(); return; }
    const question = $("question").value.trim(); if (mode === "live" && !question) { $("question").focus(); return; }
    state.submitting = true; $("start-button").disabled = true; $("demo-button").disabled = true; error(""); $("form-feedback").textContent = mode === "demo" ? "고정 샘플 흐름을 불러옵니다…" : "리서치 요청을 전달합니다…";
    try {
      const providers = Array.from(document.querySelectorAll("#provider-options input:checked")).map(input => input.value);
      if(mode==="live" && !providers.length && !state.chart && !state.tvJob && !$("evidence").value.trim() && !$("web-search").checked)throw new Error("분석 근거가 없습니다. 차트 결과·데이터·참고 자료를 선택하거나 공개 웹 자료 조회를 켜 주세요.");
      const brief={};
      const fullQuestion=question+"\n\n[질문 범주: "+CATEGORIES[state.category].name+"]";
      if(fullQuestion.length>12000)throw new Error("질문과 분석 범위가 너무 깁니다. 12,000자 이내로 줄여 주세요.");
      const models=mode==="live"?modelConfiguration():undefined;
      const data = await api("/api/runs", {method:"POST", body:{category:state.category,brief,target_role:mode==='live'?$("target-role").value:null,chart_id:mode==='live'?state.chart?.id:null,tv_job_id:mode==='live'?state.tvJob?.id:null,model_config:models,question: mode === "demo" ? "가상 기업의 사업 품질 개선 여부를 검토해줘." : fullQuestion, evidence:$("evidence").value, context:{investor_context:$("investor-context").value,brain:$("brain").value,strategy:$("strategy").value,memory:$("memory").value}, max_calls:Number($("max-calls").value),web_search:mode === "live" && $("web-search").checked, mode, symbol:$("symbol").value.trim(),providers:mode === "demo" ? [] : providers}});
      $("form-feedback").textContent = mode === "demo" ? "샘플 화면입니다. 실제 분석은 API 연결 후 리서치 시작을 눌러 주세요." : "작업이 시작되었습니다. 진행 기록에서 배정과 검토 과정을 확인할 수 있습니다.";
      await refreshStatus(); await selectRun(data.id); selectTab("activity");
    } catch (e) { error(e.message); $("form-feedback").textContent = "요청이 완료되지 않았습니다. 오류를 확인한 뒤 다시 시도하세요."; }
    finally { state.submitting = false; $("start-button").disabled = !!isActive(state.run); $("demo-button").disabled = false; }
  }
  function openConnection() { $("connect-error").textContent = ""; renderConnectProvider(true); $("connection-dialog").showModal(); }
  function selectTab(name) { for (const tab of document.querySelectorAll("[data-tab]")) { const selected = tab.dataset.tab === name; tab.setAttribute("aria-selected", selected); tab.tabIndex = selected ? 0 : -1; $("view-" + tab.dataset.tab).hidden = !selected; } }
  function newRun() {
    selectWorkspace('research');
    if (isActive(state.run)) { $("form-feedback").textContent = "현재 분석이 진행 중입니다. 완료될 때까지 기다리거나 중단한 뒤 새 분석을 시작하세요."; return; }
    state.chart=null; state.tvJob=null; renderChartAttachment();
    state.selected = null; state.run = null; renderProgress(null); $("tab-report").textContent="통합 보고서"; clearTimeout(state.timer); renderRoles(); renderHistory(); $("run-meta").hidden = true; $("export-button").hidden = true; $("cancel-button").hidden = true; $("start-button").disabled = false; $("form-feedback").textContent = ""; $("report-content").replaceChildren(el("div", "empty-output", "새로운 질문의 근거와 독립 검토 결과가 여기에 표시됩니다.")); renderArtifacts([]); renderEvents([]); $("question").value = ""; $("question").focus(); selectTab("report");
  }
  function renderProviderOptions() {
    const selected = new Set(Array.from(document.querySelectorAll("#provider-options input:checked")).map(x => x.value));
    $("provider-options").replaceChildren();
    for (const source of state.sources) { const label = el("label", `provider-chip${source.configured ? " available" : ""}`); const input = el("input"); input.type = "checkbox"; input.value = source.id; input.disabled = !source.configured; input.checked = source.configured && selected.has(source.id); label.append(input, document.createTextNode(`${source.name || source.id}${source.configured && source.symbol ? ` · ${source.symbol}` : ""}`)); label.title = source.configured ? `검증된 데이터 연결 · 실제 조회 심볼: ${source.symbol || $("symbol").value || "공통 심볼"}` : "데이터 설정에서 실제 연결을 확인하세요"; $("provider-options").append(label); }
  }
  async function refreshSources() { const data = await api("/api/sources"); state.sources = data.sources || []; renderProviderOptions(); }
  async function openSources() {
    $("sources-dialog").showModal(); $("source-cards").replaceChildren(el("p", "muted", "데이터 소스 확인 중…"));
    try { await refreshSources(); renderSourceCards(); } catch(e) { $("source-cards").replaceChildren(el("p", "error-text", e.message)); }
  }
  function renderSourceCards() {
    $("source-cards").replaceChildren();
    for (const source of state.sources) {
      const card = el("form", "source-card"); const head = el("div", "source-card-head"); head.append(el("strong", "", source.name || source.id), el("span", source.configured ? "source-connected" : "small-muted", source.configured ? "조회 확인됨" : "미연결")); card.append(head, el("p", "source-description", source.description || ""));
      if (source.warning) card.append(el("p", "source-warning", source.warning));
      const fields = [];
      for (const field of (source.fields || []).filter(field => field.name !== "symbol")) { const label = el("label", "field-label", field.label || field.name); const id = `source-${source.id}-${field.name}`; label.htmlFor = id; let input;
        if (field.options) { input = el("select"); for (const option of field.options) { const val = typeof option === "string" ? option : option.value; const opt = el("option", "", typeof option === "string" ? option : option.label); opt.value = val; input.append(opt); } }
        else if (field.type === "textarea") { input = el("textarea"); input.rows = 4; input.spellcheck = false; }
        else { input = el("input"); input.type = field.type === "password" || /secret|key|password/i.test(field.name) ? "password" : "text"; input.autocomplete = "off"; input.spellcheck = false; }
        input.id = id; input.name = field.name; input.value = field.default ?? ""; if (field.placeholder) input.placeholder = field.placeholder;
        if (field.name === "version" && !field.options && !input.value) { input.value = "v5"; input.placeholder = "v5 또는 v4"; }
        fields.push(input); card.append(label, input);
      }
      const symbolLabel = el("label", "field-label", "이 소스의 조회 심볼"); const symbol = el("input"); symbol.id = `source-${source.id}-symbol`; symbolLabel.htmlFor = symbol.id; symbol.type = "text"; symbol.autocomplete = "off"; symbol.value = source.symbol || (source.id === "kis" ? "005930" : source.id === "tradingview" ? "NASDAQ:AAPL" : "AAPL"); symbol.placeholder = "개별 심볼은 분석 화면보다 우선합니다"; card.append(symbolLabel, symbol);
      const actions = el("div", "source-actions"), submit = el("button", "button compact", source.configured ? "다시 연결 확인" : "실제 조회로 연결 확인"); submit.type = "submit"; const disconnect = el("button", "text-button", "연결 해제"); disconnect.type = "button"; disconnect.hidden = !source.configured; actions.append(submit, disconnect); const feedback = el("p", "feedback"); feedback.setAttribute("role", "status"); card.append(actions, feedback);
      card.addEventListener("submit", async event => { event.preventDefault(); submit.disabled = true; disconnect.disabled = true; feedback.className = "feedback"; feedback.textContent = "실제 데이터를 조회하고 있습니다…";
        try { const config = {}; for (const input of fields) config[input.name] = input.value; config.symbol = symbol.value.trim(); const result = await api(`/api/sources/${encodeURIComponent(source.id)}`, {method:"POST", body:{config, symbol:symbol.value.trim()}}); for (const input of fields) if (input.type === "password") input.value = ""; const info = result.result || {}; feedback.textContent = `실제 조회 성공${info.observed_at || info.retrieved_at ? ` · ${timeLabel(info.observed_at || info.retrieved_at)}` : ""}. 분석 화면에서 이 소스를 선택하세요.`; disconnect.hidden = false; head.lastChild.textContent = "조회 확인됨"; head.lastChild.className = "source-connected"; submit.textContent = "다시 연결 확인"; await refreshSources(); }
        catch(e) { feedback.className = "feedback error-text"; feedback.textContent = e.message; }
        finally { submit.disabled = false; disconnect.disabled = false; }
      });
      disconnect.addEventListener("click", async () => { disconnect.disabled = true; try { await api(`/api/sources/${encodeURIComponent(source.id)}/disconnect`, {method:"POST",body:{}}); for (const input of fields) if (input.type === "password") input.value = ""; await refreshSources(); renderSourceCards(); } catch(e) { feedback.className = "feedback error-text"; feedback.textContent = e.message; disconnect.disabled = false; } });
      $("source-cards").append(card);
    }
  }
  function selectWorkspace(name) {
    if(!['research','chart','brain','team','tradingview'].includes(name)) return;
    for(const id of ['research','chart','brain','team','tradingview']) { const section=$('workspace-'+id); if(section)section.hidden=id!==name; }
    for(const button of document.querySelectorAll('[data-workspace]')) {const active=button.dataset.workspace===name;button.classList.toggle('selected',active);button.setAttribute('aria-pressed',String(active));}
    if(name==='brain')window.HyperpassBrain?.refresh();
    document.dispatchEvent(new CustomEvent('hyperpass:workspace-change',{detail:{name}}));
    window.dispatchEvent(new Event('resize'));
  }
  function renderChartAttachment() {
    const target=$('attached-chart');if(!target)return;target.replaceChildren();target.hidden=!state.chart&&!state.tvJob;
    if(state.chart||state.tvJob){target.append(el('span','',state.tvJob?`${state.tvJob.symbol} · 실제 TradingView 백테스트를 근거로 사용`:`${state.chart.symbol} · 저장된 차트 실험을 근거로 사용`));const clear=el('button','text-button','연결 해제 ×');clear.type='button';clear.onclick=()=>{state.chart=null;state.tvJob=null;renderChartAttachment();};target.append(clear);}
  }
  function targetHint() {
    const target=$('target-role')?.value;const note=$('target-role-note');
    if(note)note.textContent=target?'선택한 에이전트가 분석합니다. Head 검수와 필요한 독립 검토는 유지됩니다.':'Head Manager가 질문에 필요한 최소 팀을 구성합니다.';
  }
  window.HyperpassApp={api,selectWorkspace,openRun:selectRun,
    useTradingView:(id,result)=>{if(isActive(state.run)){error('진행 중인 분석이 끝난 뒤 연결하세요.');return;}newRun();const symbol=result.chart?.symbol||'TradingView';state.tvJob={id,symbol};$('target-role').value='technical-analyst';targetHint();$('question').value=`${symbol}의 실제 TradingView 백테스트 결과를 기술 분석해줘. 전략 규칙, 거래 횟수, 비용과 낙폭, 데이터 범위와 과최적화 가능성을 구분하고 추가 검증이 필요한 점을 정리해줘.`;$('web-search').checked=false;renderChartAttachment();$('question').focus();},
    openChart:async id=>{selectWorkspace('chart');await window.HyperpassChart?.open(id);},
    useChart:chart=>{if(isActive(state.run)){error('진행 중인 분석이 끝난 뒤 차트 결과를 연결하세요.');return;}newRun();state.chart=chart;$('target-role').value='technical-analyst';targetHint();$('question').value=`${chart.symbol}의 저장된 차트·백테스트를 기술 분석해줘. 지표와 진입·청산 규칙, 비용, 미실현 손익, 표본 밖 검증 결과와 데이터 한계를 구분하고 과최적화 가능성을 검토해줘. 수익 보장이나 매매 지시는 하지 마.`;$('web-search').checked=false;renderChartAttachment();$('question').focus();},
    useMemory:async id=>{if(isActive(state.run)){error('분석 완료 후 이전 기록을 연결하세요.');return;}const run=await api('/api/runs/'+encodeURIComponent(id));if(run.mode==='demo'||run.status!=='completed'){error('완료된 실제 연구만 이전 판단으로 연결할 수 있습니다.');return;}selectWorkspace('research');$('memory').value=`이전 연구 ${run.id} (${run.created_at})\n${run.question}\n${run.report}`.slice(0,10000);$('memory').closest('details').open=true;$('form-feedback').textContent='이전 연구를 참고할 기억으로 연결했습니다. 현재 자료와 구분해 검토합니다.';}
  };
  for(const button of document.querySelectorAll('[data-workspace]'))button.addEventListener('click',()=>selectWorkspace(button.dataset.workspace));
  $('target-role')?.addEventListener('change',targetHint);targetHint();
  $("research-form").addEventListener("submit", event => { event.preventDefault(); start("live"); });
  $("demo-button").addEventListener("click", () => start("demo"));
  for (const id of ["connection-button", "onboarding-connect", "settings-side", "models-connect"]) $(id).addEventListener("click", openConnection);
  $("close-dialog").addEventListener("click", () => $("connection-dialog").close());
  $("connection-dialog").addEventListener("close", () => { $("api-key").value = ""; });
  for (const id of ["sources-button", "sources-inline"]) $(id).addEventListener("click", openSources);
  $("close-sources").addEventListener("click", () => $("sources-dialog").close());
  $("sources-dialog").addEventListener("close", () => { for (const input of $("source-cards").querySelectorAll('input[type="password"]')) input.value = ""; });
  $("connection-form").addEventListener("submit", async event => { event.preventDefault(); const key = $("api-key").value.trim(), model = $("model").value.trim(); if (!key) { $("connect-error").textContent = "선택한 AI의 API 키를 입력해 주세요."; return; } $("connect-submit").disabled = true; $("connect-submit").textContent = "실제 API 연결 확인 중…"; $("connect-error").textContent = "";
    try { await api("/api/connect", {method:"POST",body:{provider:$("connect-provider").value,api_key:key,model}}); $("api-key").value = ""; await refreshStatus(); await refreshAI(); $("connection-dialog").close(); $("form-feedback").textContent = "API 연결을 확인했습니다. 질문을 입력하고 리서치를 시작하세요."; }
    catch(e) { $("connect-error").textContent = e.message; }
    finally { $("connect-submit").disabled = false; $("connect-submit").textContent = "연결 확인 후 시작"; }
  });
  $("disconnect-button").addEventListener("click", async () => { $("disconnect-button").disabled = true; try { await api("/api/disconnect", {method:"POST", body:{provider:$("connect-provider").value}}); await refreshStatus(); await refreshAI(); $("api-key").value = ""; $("connection-dialog").close(); } catch(e) { $("connect-error").textContent = e.message; } finally { $("disconnect-button").disabled = false; } });
  $("cancel-button").addEventListener("click", async () => { if (!state.selected) return; $("cancel-button").disabled = true; try { await api(`/api/runs/${encodeURIComponent(state.selected)}/cancel`, {method:"POST",body:{}}); $("form-feedback").textContent = "중단을 요청했습니다. 이미 전송된 API 호출은 응답이 돌아온 뒤 멈출 수 있습니다."; await selectRun(state.selected); } catch(e) { error(e.message); } finally { $("cancel-button").disabled = false; } });
  $("new-run").addEventListener("click", newRun);
  for (const button of document.querySelectorAll("[data-prompt]")) button.addEventListener("click", () => { $("question").value = button.dataset.prompt; $("question").focus(); });
  const tabs = Array.from(document.querySelectorAll("[data-tab]")); for (const [index, tab] of tabs.entries()) { tab.addEventListener("click", () => selectTab(tab.dataset.tab)); tab.addEventListener("keydown", event => { let next; if (event.key === "ArrowRight") next = (index + 1) % tabs.length; else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length; else if (event.key === "Home") next = 0; else if (event.key === "End") next = tabs.length - 1; if (next !== undefined) { event.preventDefault(); selectTab(tabs[next].dataset.tab); tabs[next].focus(); } }); }
  window.addEventListener("pagehide", () => { state.alive = false; clearTimeout(state.timer); });
  $("connect-provider").addEventListener("change",()=>{$("api-key").value="";$("connect-error").textContent="";renderConnectProvider(true);});
  $("run-provider").addEventListener("change",()=>{$("run-model").value=defaultModel(aiInfo($("run-provider").value));modelList($("run-provider").value,"run-model-list");renderModelCapability();refreshReasoning();});
  $("run-model").addEventListener("change",refreshReasoning);
  $("refresh-models").addEventListener("click",async()=>{
    const id=$("connect-provider").value,key=$("api-key").value.trim();
    if(!key && !aiInfo(id)?.connected){$("connect-error").textContent="먼저 선택한 AI의 API 키를 입력해 주세요. 키는 모델 목록 조회에만 사용하며 아직 연결 등록하지 않습니다.";return;}
    $("refresh-models").disabled=true;$("connect-error").textContent="사용 가능한 모델 목록을 불러오는 중…";
    try{const data=await api(`/api/ai/${id}/models`,{method:"POST",body:key?{api_key:key}:{}});let p=aiInfo(id);if(!p){p={id,name:AI_NAMES[id],connected:false};state.aiProviders.push(p);}p.models=data.models || [];modelList(id,"connect-model-list");if(p.models.length && (!$("model").value.trim() || !p.models.some(m=>modelId(m)===$("model").value.trim())))$("model").value=data.default_model || modelId(p.models[0]);$("connect-error").textContent=p.models.length?`${p.models.length}개 모델을 조회했습니다. 사용할 모델을 선택하고 연결 확인을 누르세요.`:"조회된 모델이 없습니다. 서비스의 모델 권한을 확인해 주세요.";renderAISelection();}
    catch(e){$("connect-error").textContent=e.message;}finally{$("refresh-models").disabled=false;}
  });
  $("category-example").addEventListener("click",()=>{$("question").value=CATEGORIES[state.category].example;$("question").focus();});
  renderCategories(); renderRoles(); renderArtifacts([]); renderEvents([]);
  refreshStatus(true).then(()=>Promise.all([refreshSources(),refreshAI()])).catch(e => { error(e.message); $("connection-label").textContent = "서버 연결 확인 필요"; });
})();
