"use strict";
(() => {
  const el=(tag,text,cls)=>{
    const item=document.createElement(tag);
    if(text!=null)item.textContent=text;
    if(cls)item.className=cls;
    return item;
  };
  const $=id=>document.getElementById(id);
  const number=value=>typeof value==="number"&&Number.isFinite(value)?value.toLocaleString("ko-KR",{maximumFractionDigits:2}):"—";
  const download=(obj,name,mime="application/json")=>{
    const url=URL.createObjectURL(new Blob([typeof obj==="string"?obj:JSON.stringify(obj,null,2)],{type:mime}));
    const link=el("a");link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  const scopes={single:"단일 종목",custom:"종목 묶음",market:"시장 전체"};
  function mount({api,scopeBody,startJob,save,setBusy,message,revision,invalidate,basisText}) {
    let approved=null, selected=null;
    const box=el("div");box.id="bt-pine-results";box.hidden=true;
    box.innerHTML=`<p id="bt-batch-basis" class="studio-summary"></p><p id="bt-batch-count" class="portfolio-summary"></p>
      <div class="studio-scroll"><table><thead><tr><th>종목</th><th>상태</th><th>순수익률</th><th>최대 낙폭</th><th>매수 후 보유</th><th>수수료</th><th>거래 수</th><th>통화</th><th>보고서 · 사유</th></tr></thead><tbody id="bt-batch-rows"></tbody></table></div>
      <button type="button" id="bt-pine-more" class="text-button" hidden></button>
      <p id="bt-batch-restore" class="cost-note"></p>
      <div class="bt-tested-strategy"><label class="field-label" for="bt-pine-tested-name">저장할 전략 이름</label><input id="bt-pine-tested-name" maxlength="120">
      <div class="studio-actions"><button type="button" id="bt-save-tested-pine" class="button primary">검증한 코드·조건을 내 전략에 저장</button>
      <button type="button" id="bt-pine-export" class="button ghost compact">실행 결과 JSON ↓</button>
      <button type="button" id="bt-pine-backup" class="button ghost compact" hidden>실행 전 Pine 원문 ↓</button></div>
      <p id="bt-pine-result-feedback" class="feedback" role="status"></p></div>`;
    $("bt-result").before(box);
    const label=code=>({completed:"완료",failed:"실패",partial:"부분 완료",cancelled:"중단",skipped:"건너뜀"}[code]||code||"—");
    const request=async()=>{
      const code=$("tv-code").value;
      if(!code.trim())throw new Error("Pine 전략 파일을 읽거나 strategy() 코드를 붙여넣으세요.");
      const scope=await scopeBody();
      return {...scope, engine:"pine",name:$("bt-pine-name").value.trim()||"내 Pine 전략",code,timeframe:$("tv-timeframe").value,
        port:Number($("tv-port").value),...($("tv-target").value?{target_id:$("tv-target").value}:{})};
    };
    $("bt-pine-preview").addEventListener("click",()=>setBusy($("bt-pine-preview"),"bt-pine-feedback",async()=>{
      invalidate();const version=revision(), body=await request();
      if(version!==revision())throw new Error("투자 대상이나 코드가 바뀌었습니다. 다시 확인하세요.");
      const data=await api("/api/backtests/preview",body);
      if (version!==revision())throw new Error("입력이 바뀌었습니다. 실행 조건을 다시 확인하세요.");
      if(data.request?.engine!=="pine" || data.request.code!==body.code)throw new Error("검증할 Pine 원문을 확인하지 못했습니다.");
      approved={request:{...data.request,name:body.name},version};
      const normalized=approved.request;
      const source=normalized.mode==="market"?"선택한 거래소·업종의 전체 종목":(normalized.symbols||[]).join(", ");
      const universe=normalized.universe||{}, groups=[...(universe.sectors||[]),...(universe.industries||[])];
      $("bt-pine-preview-summary").textContent=[normalized.market==="KR"?"국내":"미국",scopes[normalized.mode],basisText(normalized),source,
        universe.exchanges?.length?universe.exchanges.join(", "):"전체 거래소",groups.length?"선택 업종 "+groups.length+"개":"전체 업종",normalized.timeframe,
        "종목별 Strategy Tester 순차 실행 · 날짜·자금·비용은 Pine 코드와 TradingView 설정 사용"].join(" · ");
      $("bt-pine-preview-summary").hidden=false;$("bt-pine-run").disabled=false;
      message("bt-pine-feedback","확인한 코드와 투자 대상으로 실행할 수 있습니다.");
    }));
    $("bt-pine-run").addEventListener("click",async()=>{
      try{
        if(!approved || approved.version!==revision())throw new Error("실행 조건을 다시 확인하세요.");
        const req=approved.request;approved=null;invalidate();await startJob(req);
        $("bt-result-title").scrollIntoView({block:"center"});
      }catch(e){message("bt-pine-feedback",e.message,true);}
    });
    $("bt-save-tested-pine").addEventListener("click",()=>setBusy($("bt-save-tested-pine"),"bt-pine-result-feedback",async()=>{
      if(!selected || !(selected.result?.completed>0))throw new Error("완료된 종목 보고서를 먼저 확인하세요.");
      const req=selected.request;
      const definition={engine:"pine",market:req.market,mode:req.mode,symbols:req.symbols||[],universe:req.universe||{},code:req.code,timeframe:req.timeframe,...(req.selection_snapshot?{selection_snapshot:req.selection_snapshot}:{})};
      await save($("bt-pine-tested-name").value,"pine",definition,"TradingView 코드 실행 "+selected.id);
      message("bt-pine-result-feedback","이번 실행의 원문 코드와 투자 대상을 내 전략에 저장했습니다.");
    }));
    $("bt-pine-export").addEventListener("click",()=>{if(selected)download(selected,"pine-"+selected.id+".json");});
    $("bt-pine-backup").addEventListener("click",()=>{if(selected?.result?.previous_source)download(selected.result.previous_source,"before-"+selected.id+".pine","text/plain");});
    function display(job) {
      selected=job;
      const result=job.result||{}, items=result.rows||[], id=job.id;
      box.hidden=false;$("bt-pine-tested-name").value=job.name||job.request.name||"내 Pine 전략";
      const canSave=result.completed>0 && !["queued","running"].includes(job.status);
      $("bt-save-tested-pine").hidden=!canSave;
      $("bt-pine-tested-name").hidden=!canSave;
      box.querySelector("label[for='bt-pine-tested-name']").hidden=!canSave;
      $("bt-pine-backup").hidden=!result.previous_source;
      $("bt-batch-basis").textContent="종목마다 별도 초기 자금으로 실행합니다. 표의 수익률·낙폭·매수 후 보유 기준은 각 종목의 Strategy Tester 값입니다. 합산 포트폴리오 수익률과 시장 지수 초과수익률은 산출하지 않습니다. 비용은 사용한 Pine 속성을 따르며 미보고 값은 —로 표시합니다.";
      $("bt-batch-count").textContent=[["대상",result.requested],["완료",result.completed],["실패",result.failed],["건너뜀",result.skipped],["완결 거래 0건",items.filter(r=>r.status==="completed"&&r.metrics?.total_trades===0).length]].map(([l,n])=>l+" "+number(n)+"종목").join(" · ");
      $("bt-batch-restore").textContent=result.restore?.message||"";
      message("bt-pine-result-feedback","");
      const body=$("bt-batch-rows");body.replaceChildren();let next=0;
      function append() {
        for(const row of items.slice(next,next+60)) {
          const tr=body.insertRow(), m=row.metrics||{};
          const pc=n=>Number.isFinite(n)?number(n)+"%":"—";
          for(const val of [[row.symbol,row.name&&row.name!==row.symbol?row.name:""].filter(Boolean).join(" · "),label(row.status),pc(m.net_profit_percent),
             pc(m.max_drawdown_percent),pc(m.buy_hold_return_percent),number(m.commission_paid),number(m.total_trades),row.currency||"—"]) tr.append(el("td",val));
          const detail=el("td");
          if(Number.isInteger(row.report_index) && row.report_index>=0 && row.status==="completed"){
            const b=el("button","원본 JSON ↓","text-button");b.type="button";
            b.onclick=()=>setBusy(b,"bt-pine-result-feedback",async()=>{
              const data=await api("/api/backtests/"+encodeURIComponent(id)+"/pine-reports/"+row.report_index);
              download(data,"pine-report-"+row.report_index+".json");
            });
            detail.append(b);
            if(row.execution_title) {
              const info=el("details",null,"bt-execution-source"), summary=el("summary","실행 제목·코드");
              const title=el("p",row.execution_title,"cost-note"), code=el("pre"), actions=el("div",null,"studio-actions");
              const view=el("button","실행 코드 보기","text-button"), file=el("button","실행 코드 ↓","text-button");
              const feedback=el("p",null,"feedback"); feedback.setAttribute("role","status");
              view.type=file.type="button";code.hidden=true;code.tabIndex=0;
              let execution;
              async function loadExecution(button,action) {
                button.disabled=true;
                try {
                  const data=execution || (await api("/api/backtests/"+encodeURIComponent(id)+"/pine-reports/"+row.report_index)).execution;
                  if(!data || data.title!==row.execution_title || typeof data.source!=="string")throw new Error("이 보고서에서 실행 코드를 확인할 수 없습니다.");
                  execution=data;feedback.textContent="";action(data);
                } catch(error) {feedback.textContent=error.message;}
                finally {button.disabled=false;}
              }
              view.onclick=()=>{if(!code.hidden){code.hidden=true;view.textContent="실행 코드 보기";return;}
                loadExecution(view,data=>{code.textContent=data.source;code.hidden=false;view.textContent="실행 코드 닫기";});};
              file.onclick=()=>loadExecution(file,data=>download(data.source,"pine-execution-"+row.report_index+".pine","text/plain"));
              actions.append(view,file); info.append(summary,title,actions,code,feedback); detail.append(info);
            }
          }else detail.textContent=row.error||row.reason||"—";
          tr.append(detail);
        }
        next+=60;$("bt-pine-more").hidden=next>=items.length;
        $("bt-pine-more").textContent="다음 "+Math.max(0,Math.min(60,items.length-next))+"종목 보기";
      }
      append();$("bt-pine-more").onclick=append;
    }
    return {display,hide:()=>{box.hidden=true; selected=null;}};
  }
  window.HyperpassPineBatch={mount};
})();
