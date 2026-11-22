"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const workspace = $("workspace-tradingview");
  const outputPanel = workspace?.querySelector(".tv-job-panel");
  if (!outputPanel) return;

  const example = "최근 1년간 고점들을 추세선으로 연결해줘";
  const trend = {
    name: "최근 1년 고점 추세선",
    code: `//@version=6
indicator("Hyperpass · 1Y Pivot Highs", overlay = true, max_lines_count = 500)
pivotBars = input.int(5, "고점 좌우 확인 봉", minval = 1, maxval = 100)
lookbackDays = input.int(365, "조회 일수", minval = 1, maxval = 3650)
lineColor = input.color(color.orange, "추세선 색")
cutoff = last_bar_time - lookbackDays * 86400000
highPoint = ta.pivothigh(high, pivotBars, pivotBars)
pivotTime = time[pivotBars]
var int previousTime = na
var float previousHigh = na

if barstate.isconfirmed and not na(highPoint) and pivotTime >= cutoff
    if not na(previousTime) and previousTime >= cutoff
        line.new(previousTime, previousHigh, pivotTime, highPoint, xloc = xloc.bar_time, color = lineColor, width = 2)
    previousTime := pivotTime
    previousHigh := highPoint

if barstate.islast
    for segment in line.all
        if line.get_x1(segment) < cutoff
            line.delete(segment)
`
  };
  const panel = document.createElement("section");
  panel.className = "panel tv-personal-panel";
  panel.setAttribute("aria-labelledby", "tv-personal-heading");
  panel.innerHTML = `<div class="panel-heading"><div><h2 id="tv-personal-heading">개인 지표 · 추세선</h2></div></div>
    <div class="tv-panel-body">
      <label class="field-label" for="tv-personal-prompt">차트에 무엇을 표시할까요?</label>
      <textarea id="tv-personal-prompt" rows="2" maxlength="4000" placeholder="예: 최근 1년간 고점들을 추세선으로 연결해줘"></textarea>
      <div class="workspace-actions"><button type="button" class="button ghost compact" id="tv-personal-example">1년 고점 추세선 예시</button>
        <button type="button" class="button primary compact" id="tv-personal-generate">요청으로 코드 만들기</button></div>
      <p class="cost-note">예시는 AI 연결 없이 열 수 있습니다. 다른 요청은 분석 화면에서 선택한 AI와 모델을 사용합니다.</p>
      <div class="field-pair"><div><label class="field-label" for="tv-personal-list">내 지표</label>
        <select id="tv-personal-list"><option value="">새 지표</option></select></div><div>
        <label class="field-label" for="tv-personal-name">저장할 이름</label><input id="tv-personal-name" maxlength="120" placeholder="예: 나의 고점 추세선"></div></div>
      <label class="field-label" for="tv-personal-code">Pine 지표 코드</label>
      <textarea id="tv-personal-code" rows="10" maxlength="64000" spellcheck="false" placeholder='//@version=6&#10;indicator("나의 이동평균", overlay=true)&#10;plot(ta.sma(close, 20))'></textarea>
      <div class="workspace-actions"><button type="button" class="button ghost" id="tv-personal-save">내 지표에 저장</button>
        <button type="button" class="button primary" id="tv-personal-apply">선택한 차트에 지표 적용 ↗</button></div>
      <p id="tv-personal-feedback" class="feedback" role="status" aria-live="polite"></p>
    </div>`;
  workspace.insertBefore(panel, outputPanel);
  const prompt = $("tv-personal-prompt"), list = $("tv-personal-list"), name = $("tv-personal-name"), code = $("tv-personal-code");
  const setMessage = (message, error = false) => {
    const feedback = $("tv-personal-feedback");
    feedback.textContent = message;
    feedback.classList.toggle("error-text", error);
  };
  const api = (route, body) => window.HyperpassApp.api(route, body === undefined ? {} : {method:"POST", body});
  let records = [], selected = "", baseline = {name:"",code:""}, ready = false, loading = false, writing = false;
  function fill(record) {
    selected = record?.id || "";
    list.value = selected;
    name.value = record?.name || "";
    code.value = record?.code || "";
    baseline = {name:name.value, code:code.value};
  }
  function canReplace() {
    return name.value === baseline.name && code.value === baseline.code ||
      window.confirm("편집 중인 이름과 코드를 새 내용으로 바꿀까요?");
  }
  function showDraft(record) {
    fill(record);
    baseline = {name:"", code:""};
  }
  function redraw() {
    list.replaceChildren(new Option("새 지표", ""));
    for (const record of records) list.append(new Option(record.name, record.id));
    list.value = selected;
  }
  function markWriting(active) {
    writing = active;
    for (const id of ["tv-personal-generate","tv-personal-example","tv-personal-save","tv-personal-list","tv-personal-prompt","tv-personal-name","tv-personal-code"]) $(id).disabled = active;
  }
  async function load() {
    if (workspace.hidden || ready || loading) return;
    loading = true;
    try {
      const data = await api("/api/indicators");
      records = data.indicators;
      redraw();
      ready = true;
    } catch(error) {
      setMessage(error.message, true);
    } finally {
      loading = false;
    }
  }
  function useExample() {
    showDraft(trend);
    setMessage("지난 365일 동안 좌우 5개 봉으로 확정한 고점들을 연결합니다. 차트에 고점이 둘 이상 있어야 선이 보입니다. 일 년 전체를 보려면 일봉으로 적용하세요.");
  }
  $("tv-personal-example").addEventListener("click", () => {
    if (!canReplace()) return;
    prompt.value = example;
    useExample();
  });
  $("tv-personal-generate").addEventListener("click", async () => {
    const instruction = prompt.value.trim();
    if (!instruction) { setMessage("차트에 표시할 내용을 먼저 적어 주세요.", true); prompt.focus(); return; }
    if (!canReplace()) return;
    if (/^(?:최근|지난)?(?:1년|일년|한해|365일)(?:간|동안)?(?:의)?고점들?(?:을|를)?(?:추세선|선)(?:으로|로)?(?:연결|이어)(?:해|그려)?(?:줘|주세요|주세요요)?[.!?]?$/u.test(instruction.replace(/\s/g,""))) {
      useExample();
      return;
    }
    const settings = {provider:$("run-provider").value, model:$("run-model").value.trim(), reasoning:$("run-reasoning").value || "default"};
    if (!settings.provider || !settings.model) { setMessage("분석 화면에서 AI를 연결하고 모델을 선택하세요.", true); return; }
    markWriting(true);
    setMessage("선택한 모델이 Pine 지표 코드를 작성하고 있습니다.");
    try {
      const generated = await api("/api/indicators/generate", {prompt:instruction, ...settings});
      showDraft(generated);
      setMessage("AI가 작성한 코드를 검토하고 원하는 종목과 주기에 적용하세요.");
    } catch(error) {
      setMessage(error.message, true);
    } finally {
      markWriting(false);
    }
  });
  list.addEventListener("change", () => {
    if (!canReplace()) {list.value=selected;return;}
    fill(records.find(r=>r.id===list.value));
    setMessage("");
  });
  $("tv-personal-save").addEventListener("click", async () => {
    if (!name.value.trim() || !code.value.trim()) {setMessage("이름과 Pine 지표 코드를 입력하세요.",true);return;}
    markWriting(true);
    try {
      const saved = await api("/api/indicators", {name:name.value,code:code.value,...(selected ? {id:selected} : {})});
      records = [...records.filter(r=>r.id!==saved.id), saved].sort((a,b)=>a.name.localeCompare(b.name,"ko"));
      redraw();
      fill(saved);
      setMessage("내 지표에 저장했습니다.");
    } catch(error) {
      setMessage(error.message, true);
    } finally {
      markWriting(false);
    }
  });
  $("tv-personal-apply").addEventListener("click", async () => {
    if (writing) return;
    if (!code.value.trim()) {setMessage("차트에 적용할 지표 코드를 입력하세요.",true);return;}
    setMessage("");
    await window.HyperpassTradingView.applyIndicator(code.value);
    outputPanel.scrollIntoView({behavior:"smooth",block:"start"});
  });
  document.addEventListener("hyperpass:workspace-change", load);
  new MutationObserver(load).observe(workspace, {attributes:true,attributeFilter:["hidden"]});
  load();
})();
