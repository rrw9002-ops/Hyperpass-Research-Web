"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const api = (path, data) => window.HyperpassApp.api(path, data === undefined ? {} : {method:"POST", body:data});
  const make = (tag, value) => Object.assign(document.createElement(tag), {textContent:value});
  function button(label, action, style="text-button") {
    const b=make("button",label);
    b.type="button"; b.className=style; b.addEventListener("click",action); return b;
  }
  let records=[], context={}, optionsVersion=0, optionsTimer, submitted=false, currentReport, currentChart;
  let refreshing=false, inBrain=false;
  const lastAttempt=new Map(), problems=new Map();
  function openDialog(symbol="", links={}, options=[]) {
    context=links; ++optionsVersion; clearTimeout(optionsTimer);
    $("watch-symbol").value=symbol; $("watch-message").textContent=""; $("watch-matches").replaceChildren();
    for(const pick of options) $("watch-matches").append(button(pick.name+" · "+pick.symbol,()=>{
      $("watch-symbol").value=pick.symbol; $("watch-matches").replaceChildren();
    }));
    $("watch-dialog").showModal(); $("watch-symbol").focus(); $("watch-symbol").select();
  }
  function openList() {
    window.HyperpassApp.selectWorkspace("brain");
    $("watch-title").scrollIntoView({block:"start"});
  }
  function actionBar(host, symbol, links, options=[]) {
    if (!host) return;
    host.hidden=false;
    host.replaceChildren(button("☆ 관심종목에 추가",()=>openDialog(symbol,links,options),"button ghost compact"),
                         button("내 관심종목 보기",openList));
  }
  function reportActions() {
    const host=$("report-watch-actions"), r=currentReport;
    host.hidden=!r || r.status!=="completed" || r.mode==="demo";
    if(host.hidden) return;
    const inputs=(r.data || []).map(item=>item.symbol).filter(Boolean);
    const parenthesis=(r.question || "").match(/\(([A-Z]{1,6}(?:\.[AB])?|[0-9]{6}(?:\.K[SQ])?)\)/);
    const symbol=r.symbol || (new Set(inputs).size===1 ? inputs[0] : "") || parenthesis?.[1] || "";
    const options=r.watch_candidates || [];
    const displayed=symbol || (options.length===1 ? options[0].symbol : "");
    actionBar(host,displayed,{run_id:r.id},options);
  }
  function chartActions() {
    if(!currentChart) return;
    let host=$("chart-watch-actions");
    if(!host) {
      const anchor=$("chart-ask"); if(!anchor) return;
      host=document.createElement("div"); host.id="chart-watch-actions";host.className="watch-actions";anchor.after(host);
    }
    actionBar(host,currentChart.symbol || currentChart.source_packet?.symbol || "",{chart_id:currentChart.id});
  }
  function displayQuote(item,host) {
    host.replaceChildren();
    const q=item.quote;
    if(q) {
      const price=Number(q.price).toLocaleString("ko-KR",{maximumFractionDigits:4});
      const change=q.change_pct==null ? "" : " · "+(q.change_pct>0?"+":"")+q.change_pct.toFixed(2)+"%";
      host.append(make("strong",price+" "+(q.currency || "")+change),document.createElement("br"),
                  make("small","Yahoo 일봉 · "+q.as_of.slice(0,10)+" 기준"));
    } else host.append(make("small","저장된 시세가 없습니다."));
    if(problems.has(item.symbol)) host.append(document.createElement("br"),make("small",problems.get(item.symbol)));
  }
  function timeLabel(value) {
    if(!value)return "미제공";
    if(value.length===10)return value;
    return new Date(value).toLocaleString("ko-KR",{timeZone:"Asia/Seoul",hour12:false})+" KST";
  }
  function marketDay(value,region) {
    if(!value||value.length===10)return value||"";
    return new Intl.DateTimeFormat("en-CA",{timeZone:region==="KR"?"Asia/Seoul":"America/New_York",
      year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date(value));
  }
  function priceText(price,currency) {
    return Number.isFinite(price)?price.toLocaleString("ko-KR",{maximumFractionDigits:4})+" "+(currency||""):"미제공";
  }
  function reviewLines(item) {
    const snapshot=item.selection_snapshot,q=item.quote,member=snapshot?.members[0];
    const earlier=[],recent=[],decision=[];
    if(member){
      earlier.push("선정 "+timeLabel(snapshot.selected_at)+" · "+snapshot.provider,
        member.price_label+" "+priceText(member.price,member.currency)+" · "+member.price_source,
        "가격 관측 "+timeLabel(member.price_as_of)+" · 스크리너 수신 "+timeLabel(snapshot.data_as_of));
      if(member.price_received_at)earlier.push("종목 시세 수신 "+timeLabel(member.price_received_at));
      if(member.master_at)earlier.push("상장 마스터 게시 "+timeLabel(member.master_at));
      earlier.push("적용 조건 · "+window.HyperpassScreenFilters.format(snapshot.filters));
      for(const [field,value] of Object.entries(member.metrics||{}))
        earlier.push(window.HyperpassScreenFilters.labels[field]+" "+value+" · "+member.metric_sources[field]);
      if(snapshot.filters.ranges.length)earlier.push("재무 기준일 "+timeLabel(member.fiscal_date)+(member.supplement_fiscal_date?" · 보강 재무 기준일 "+timeLabel(member.supplement_fiscal_date):""));
    }else earlier.push("스크리너 선정 기록 없음 · 관심 등록 "+timeLabel(item.added_at));
    if(q){
      recent.push("Yahoo Finance 일봉 종가 "+priceText(q.price,q.currency)+" · 봉 기준 "+timeLabel(q.as_of)+" · 수신 "+timeLabel(q.retrieved_at));
      if(member && q.currency===member.currency && ["KRW","USD"].includes(q.currency) && member.price>0 && q.price>0){
        if(marketDay(q.as_of,snapshot.market)>marketDay(snapshot.selected_at,snapshot.market)){
          const pct=(q.price/member.price-1)*100;
          recent.push("선정 가격 대비 "+(pct>0?"+":"")+pct.toFixed(2)+"% · 가격 차이만 계산 (배당·비용 제외)");
        }else recent.push("선정일 이후의 새 일봉을 기다리는 중");
      }else if(member)recent.push("동일 통화의 유효한 선정 가격이 필요합니다.");
    }else recent.push("최근 가격 미수신");
    recent.push("선정 이후 공시 · 미확인");
    if(item.first_note && (item.first_note.thesis!==item.thesis||item.first_note.invalidation!==item.invalidation)){
      decision.push("최초 판단 "+timeLabel(item.first_note.updated_at)+" · "+(item.first_note.thesis||"미작성"),
                    "최초 반증 조건 · "+(item.first_note.invalidation||"미작성"));
    }
    decision.push("선정 가설 · "+(item.thesis||"미작성"),"반증 조건 · "+(item.invalidation||"미작성"));
    if(item.decision_updated_at)decision.push("판단 기록 "+timeLabel(item.decision_updated_at));
    return {earlier,recent,decision};
  }
  function decisionPanel(item,lines){
    const area=make("details","");area.className="watch-history";
    area.append(make("summary","선정 근거와 최근 관측 비교"));
    for(const [label,group] of [["선정 시점",lines.earlier],["최근 관측",lines.recent],["내 판단",lines.decision]]){
      const section=make("section","");section.append(make("strong",label));
      for(const line of group)section.append(make("p",line));
      area.append(section);
    }
    return area;
  }
  let editing=null;
  function editNote(item){
    editing=item.symbol;$("watch-note-symbol").textContent=item.name+" · "+item.symbol;
    $("watch-thesis").value=item.thesis||"";$("watch-invalidation").value=item.invalidation||"";
    $("watch-note-message").textContent="";$("watch-note-dialog").showModal();$("watch-thesis").focus();
  }
  $("watch-note-close").onclick=()=>$("watch-note-dialog").close();
  $("watch-note-form").onsubmit=async event=>{
    event.preventDefault();const submit=event.submitter||$("watch-note-form").querySelector("[type=submit]");
    if(submit.disabled)return;submit.disabled=true;
    try{await api("/api/watchlist/decision",{symbol:editing,thesis:$("watch-thesis").value,invalidation:$("watch-invalidation").value});
      $("watch-note-dialog").close();await load();}
    catch(e){$("watch-note-message").textContent=e.message;}
    finally{submit.disabled=false;}
  };
  function render() {
    $("watch-count").textContent=String(records.length);
    const host=$("watch-items"); host.replaceChildren();
    if(!records.length) {host.append(make("small","보고서나 차트에서 관심종목을 추가하면 이곳에서 시세와 이전 분석을 다시 볼 수 있습니다."));return;}
    for(const item of records) {
      const card=document.createElement("article");card.className="watch-card";
      const price=document.createElement("p");displayQuote(item,price);
      const actions=document.createElement("div");actions.className="watch-controls";
      actions.append(button("현재 차트",async()=>{
        window.HyperpassApp.selectWorkspace("chart"); await window.HyperpassChart.openSymbol(item.yahoo || item.symbol);
      }));
      if(item.run_id) actions.append(button("분석 보고서",()=>window.HyperpassApp.openRun(item.run_id)));
      if(item.chart_id) actions.append(button("저장한 차트",()=>window.HyperpassApp.openChart(item.chart_id)));
      const lines=reviewLines(item);
      actions.append(button("판단 기록",()=>editNote(item)),button("이전 판단 다시 검토",async()=>{
        const evidence=["관심종목 "+item.name+" · "+item.symbol,"[선정 시점]",...lines.earlier,"[최근 관측]",...lines.recent].join("\n");
        try{await window.HyperpassApp.reviewWatch(item,evidence,lines.decision.join("\n"));}
        catch(e){$("watch-feedback").textContent=e.message;}
      }));
      actions.append(button("목록에서 빼기",async()=>{
        try{await api("/api/watchlist/remove",{symbol:item.symbol});records=records.filter(r=>r.symbol!==item.symbol);render();}
        catch(e){$("watch-feedback").textContent=e.message;}
      }));
      card.append(make("h3",item.name),make("small",item.symbol),price,decisionPanel(item,lines),actions);host.append(card);
    }
  }
  async function load() {
    const data=await api("/api/watchlist"); records=data.items; render();
  }
  async function quotes(force=false) {
    if(refreshing) return;
    refreshing=true;$("watch-refresh").disabled=true;
    try {
      await load();const now=Date.now();
      const pending=records.filter(item=>item.yahoo && (force || now-Math.max(Date.parse(item.quote?.retrieved_at)||0,lastAttempt.get(item.symbol)||0)>600000));
      if(pending.length) $("watch-feedback").textContent="관심종목의 최근 일봉을 조회하고 있습니다…";
      let failures=0;
      async function worker() {
        while(pending.length && inBrain) {
          const item=pending.shift();lastAttempt.set(item.symbol,Date.now());
          try{item.quote=await api("/api/watchlist/quote",{symbol:item.symbol});problems.delete(item.symbol);}
          catch(e){failures++;problems.set(item.symbol,e.message);}
        }
      }
      await Promise.all(Array.from({length:Math.min(3,pending.length)},worker));
      render();$("watch-feedback").textContent=failures ? "시세 조회 실패 "+failures+"건 · 각 종목의 기준일을 확인하세요." : "";
    } catch(e){$("watch-feedback").textContent=e.message;}
    finally{refreshing=false;$("watch-refresh").disabled=false;}
  }
  $("watch-symbol").addEventListener("input",()=>{
    const field=$("watch-symbol"), query=field.value.trim(), version=++optionsVersion;
    clearTimeout(optionsTimer);$("watch-matches").replaceChildren();
    if(!query)return;
    optionsTimer=setTimeout(async()=>{
      try {
        const data=await api("/api/tradingview/symbols?q="+encodeURIComponent(query));
        if(version!==optionsVersion || !$("watch-dialog").open) return;
        for(const r of data.results.slice(0,6)) $("watch-matches").append(button(r.name+" · "+r.id,()=>{
          ++optionsVersion;field.value=r.id;$("watch-matches").replaceChildren();
        }));
      }catch(e){if(version===optionsVersion)$("watch-message").textContent=e.message;}
    },350);
  });
  $("watch-form").addEventListener("submit",async event=>{
    event.preventDefault();if(submitted)return;submitted=true;
    const submit=event.submitter || $("watch-form").querySelector("button[type=submit]");
    submit.disabled=true;$("watch-message").textContent="종목을 확인하고 있습니다…";
    try {
      const saved=await api("/api/watchlist",{symbol:$("watch-symbol").value.trim(),...context});
      ++optionsVersion;$("watch-dialog").close();await load();
      const host=context.run_id ? $("report-watch-actions") : context.chart_id ? $("chart-watch-actions") : $("watch-feedback");
      host?.append(make("span",saved.name+" 저장됨"));
      if(inBrain) await quotes();
    }catch(e){$("watch-message").textContent=e.message;}
    finally{submitted=false;submit.disabled=false;}
  });
  $("watch-add").addEventListener("click",()=>openDialog());
  $("watch-close").addEventListener("click",()=>$("watch-dialog").close());
  $("watch-refresh").addEventListener("click",()=>quotes(true));
  document.addEventListener("hyperpass:workspace-change",e=>{inBrain=e.detail.name==="brain";if(inBrain)quotes();});
  document.addEventListener("hyperpass:chart-result",e=>{currentChart=e.detail;chartActions();});
  document.addEventListener("hyperpass:report",e=>{currentReport=e.detail;reportActions();});
  currentReport=window.HyperpassApp.currentRun(); reportActions();
  setInterval(()=>{if(inBrain && !document.hidden)quotes();},600000);
})();
