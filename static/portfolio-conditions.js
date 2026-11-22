"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const create = (tag, text, cls) => {
    const el = document.createElement(tag);
    if (text != null) el.textContent=text;
    if (cls) el.className=cls;
    return el;
  };
  const fields={momentum:"모멘텀 수익률 (%)",per:"PER (배)",close:"종가 (현지 통화)",volume:"거래량 (주)"};
  const frequencyNames={daily:"매 거래일",monthly:"매월",quarterly:"분기마다",annual:"매년"};
  const fieldOptions = Object.entries(fields).map(([id,label])=>new Option(label,id));
  const freshCode = () => ({version:1,entry:"ranked",exit:"rank_drop",factors:[{field:"momentum",order:"desc"}]});

  function mount({api, invalidate, message, labelMode}) {
    $("bt-universe-options").innerHTML=`
      <details class="bt-disclosure" id="bt-scope-details"><summary>거래소·업종 선택 <span id="bt-scope-count">전체</span></summary>
        <div class="bt-disclosure-body"><p id="bt-market-meta" class="cost-note" role="status"></p>
          <div id="bt-exchanges"></div><div id="bt-industries"></div>
          <button id="bt-scope-retry" hidden class="text-button" type="button">목록 다시 조회</button>
        </div></details>`;
    $("bt-schedule").innerHTML=`
      <div class="field-pair"><div><label class="field-label" for="bt-frequency">리밸런싱 주기</label>
      <select id="bt-frequency"><option value="daily">매 거래일</option><option value="monthly" selected>매월</option><option value="quarterly">분기마다</option><option value="annual">매년</option></select></div>
      <div id="bt-month-wrap" hidden><label class="field-label" for="bt-month">기준 월</label><select id="bt-month"></select></div></div>
      <label class="field-label" for="bt-contribution">월 추가 납입액 <span id="bt-deposit-unit"></span></label>
      <input type="number" id="bt-contribution" min="0" max="1000000000000000" step="any" value="0">
      <label class="bt-check bt-dividend"><input type="checkbox" id="bt-dividends"> 현금 배당 반영</label>`;
    for (let i=1;i<=12;i++) $("bt-month").add(new Option(i+"월",i));
    $("bt-month").value="3";
    $("bt-condition-rules").innerHTML=`
      <div id="bt-legacy-note" class="bt-legacy-note" hidden><p>이 전략은 기존 기술 신호와 순위 방식으로 저장됐습니다.</p>
      <button type="button" class="button ghost compact" id="bt-upgrade">조건 코드로 편집</button></div>
      <fieldset class="bt-rule-builder" id="bt-builder">
        <div class="field-pair"><div><label class="field-label" for="bt-entry">매수 조건</label>
          <select id="bt-entry"><option value="ranked">조건을 통과한 상위 종목</option><option value="technical">기술 신호 + 종목 조건</option></select></div>
          <div><label class="field-label" for="bt-exit">매도 조건</label><select id="bt-exit"><option value="rank_drop">리밸런싱 때 편입 순위 이탈</option>
          <option value="technical">기술 청산 신호</option><option value="either">순위 이탈 또는 기술 청산</option></select></div></div>
        <div class="bt-subhead"><h3>매수 범위와 정렬 순서</h3><button type="button" id="bt-factor-add" class="text-button">조건 추가 ＋</button></div>
        <p class="cost-note">모든 범위를 통과한 종목을 위에서부터 순서대로 정렬합니다. 빈 범위는 제한 없이 사용합니다.</p>
        <div id="bt-factors" class="bt-factors"></div>
        <div class="bt-factor-presets"><span>예시</span><button type="button" class="chip" id="bt-per-preset">저PER 1~15배</button>
        <button type="button" class="chip" id="bt-momentum-preset">모멘텀 상위</button></div>
      </fieldset>`;
    $("bt-fundamental-data").innerHTML=`
      <details class="bt-disclosure" id="bt-fund-detail"><summary>과거 EPS 자료 <span id="bt-eps-count">0행</span></summary>
        <div class="bt-disclosure-body"><p class="cost-note" id="bt-eps-help">PER을 쓰려면 해당 날짜에 공개된 최근 12개월 주당순이익(EPS)을 불러오세요. 종가와 같은 통화·주식분할 기준을 사용합니다. 공개일 다음 거래일부터 사용하며, 최대 350,000행·24 MiB를 지원합니다.</p>
        <label class="field-label" for="bt-eps-file">EPS CSV (UTF-8)</label><input id="bt-eps-file" type="file" accept=".csv,text/csv" aria-describedby="bt-eps-help">
        <div class="bt-file-actions"><button type="button" class="text-button" id="bt-eps-sample">CSV 양식 다운로드</button>
        <button type="button" class="text-button" id="bt-eps-clear" hidden>등록 자료 지우기</button></div>
        <p id="bt-eps-feedback" class="feedback" role="status"></p></div></details>`;
    $("bt-code-editor").innerHTML=`
      <details class="bt-disclosure bt-code-disclosure" id="bt-code-detail" open>
        <summary>포트폴리오 전략 코드 <span>JSON</span></summary><div class="bt-disclosure-body">
        <label class="field-label" for="bt-strategy-code">실행할 종목 선정·매도 규칙</label>
        <textarea id="bt-strategy-code" spellcheck="false" rows="10" maxlength="16000" aria-describedby="bt-code-help"></textarea>
        <p class="cost-note" id="bt-code-help">조건을 바꾸면 코드가 갱신됩니다. 직접 편집한 코드는 아래 버튼으로 적용하세요.</p>
        <div class="bt-file-actions"><button type="button" id="bt-code-apply" class="button ghost compact" disabled>편집한 코드 적용</button>
          <button type="button" id="bt-code-reset" class="text-button" hidden>코드 편집 취소</button></div>
        <p id="bt-code-feedback" class="feedback" role="status"></p></div></details>`;

    let code = freshCode(), dirty=false, legacy=false, market="KR", mode="market";
    let scope={exchanges:[],sectors:[],industries:[]}, rows=[], options=null;
    let activeEngine="pine";
    let generation=0, loadPending=false, uploadPending=false, fileRevision=0;
    const catalog = new Map();

    function showSchedule() {
      const show=["annual","quarterly"].includes($("bt-frequency").value);
      $("bt-month-wrap").hidden=!show;
    }
    function updateCodeState() {
      $("bt-builder").disabled=dirty;
      $("bt-entry").disabled=legacy;
      $("bt-legacy-note").hidden=!legacy;
      $("bt-builder").hidden=legacy;
      $("bt-code-editor").hidden=legacy;
      $("bt-legacy-ranking").hidden=!legacy;
      $("bt-schedule").hidden=legacy;
      $("bt-universe-options").hidden=legacy && activeEngine!=="pine";
      $("bt-fundamental-data").hidden=legacy || !code.factors.some(f=>f.field==="per");
      $("bt-technical-fields").hidden=!legacy && !(code.entry==="technical" || code.exit==="technical" || code.exit==="either");
      $("bt-lookback-field").hidden=!legacy && code.factors.length>0 && !code.factors.some(f=>f.field==="momentum");
      $("bt-code-apply").disabled=!dirty;
      $("bt-code-reset").hidden=!dirty;
    }
    function reflectCode() {
      $("bt-strategy-code").value=JSON.stringify(code,null,2);
      dirty=false;
      message("bt-code-feedback","");
      $("bt-entry").value=code.entry; $("bt-exit").value=code.exit;
      updateCodeState();
    }
    function scaleRow(factor,index) {
      const row=create("div",null,"bt-factor");
      const field=create("select"), order=create("select");
      field.replaceChildren(...fieldOptions.map(option=>option.cloneNode(true))); field.value=factor.field;
      order.add(new Option("오름차순","asc")); order.add(new Option("내림차순","desc")); order.value=factor.order;
      const rank=create("span",String(index+1),"bt-rank");
      rank.setAttribute("aria-label","우선순위 "+(index+1));
      function labelled(title,input) {
        const label=create("label",title,"bt-mini-field"); label.append(input); return label;
      }
      const criteria=create("div",null,"bt-factor-values");
      criteria.append(labelled("지표",field),labelled("정렬",order));
      for (const [key,title] of [["min","최솟값"],["max","최댓값"]]) {
        const input=create("input"); input.type="number"; input.step="any"; input.placeholder="제한 없음"; input.value=factor[key]??"";
        input.addEventListener("input",()=>{
          if (input.value==="") delete factor[key]; else factor[key]=Number(input.value);
          reflectCode();
        });
        criteria.append(labelled(title,input));
      }
      field.addEventListener("change",()=>{factor.field=field.value;reflectCode();});
      order.addEventListener("change",()=>{factor.order=order.value;reflectCode();});
      const actions=create("div",null,"bt-factor-actions");
      for(const [name,label,delta] of [["위로","↑",-1],["아래로","↓",1],["삭제","삭제",0]]) {
        const button=create("button",label,"text-button"); button.type="button"; button.setAttribute("aria-label",(index+1)+"순위 조건 "+name);
        button.disabled=delta!==0 && (index+delta<0 || index+delta>=code.factors.length);
        button.addEventListener("click",()=>{
          code.factors.splice(index,1);
          if(delta) code.factors.splice(index+delta,0,factor);
          drawFactors(); invalidate();
        });
        actions.append(button);
      }
      row.append(rank,criteria,actions); return row;
    }
    function drawFactors() {
      const host=$("bt-factors"); host.replaceChildren(...code.factors.map(scaleRow));
      if (!code.factors.length) host.append(create("p","범위 조건 없음 · 기본 모멘텀 순위 사용","cost-note"));
      $("bt-factor-add").disabled=code.factors.length>=Object.keys(fields).length;
      reflectCode();
    }
    function validateCode(value) {
      if (!value || typeof value!=="object" || Array.isArray(value) || value.version!==1 ||
          !["technical","ranked"].includes(value.entry) || !["rank_drop","technical","either"].includes(value.exit) ||
          !Array.isArray(value.factors) || value.factors.length>Object.keys(fields).length ||
          Object.keys(value).some(k=>!["version","entry","exit","factors"].includes(k))) throw new Error("version 1, entry, exit, factors가 있는 포트폴리오 JSON을 확인하세요.");
      const used = new Set();
      for (const [i,f] of value.factors.entries()) {
        if(!f || !Object.hasOwn(fields,f.field) || used.has(f.field) || !["asc","desc"].includes(f.order) ||
           Object.keys(f).some(k=>!["field","min","max","order"].includes(k))) throw new Error((i+1)+"번째 조건의 지표·정렬 또는 중복 지표를 확인하세요.");
        for(const bound of ["min","max"]) if(f[bound]!==undefined && !Number.isFinite(f[bound])) throw new Error((i+1)+"번째 조건 범위에는 숫자를 입력하세요.");
        if (f.min!==undefined && f.max!==undefined && f.min>f.max) throw new Error((i+1)+"번째 조건의 최솟값이 최댓값보다 큽니다.");
        used.add(f.field);
      }
      return value;
    }

    $("bt-factor-add").addEventListener("click",()=>{
      const field=Object.keys(fields).find(key=>!code.factors.some(f=>key===f.field));
      if(field) {code.factors.push({field,order:field==="per"?"asc":"desc"});drawFactors();invalidate();}
    });
    for (const name of ["entry","exit"]) $("bt-"+name).addEventListener("change",()=>{code[name]=$("bt-"+name).value;reflectCode();});
    for(const id of ["per","momentum"]) $("bt-"+id+"-preset").addEventListener("click",()=>{
      code=freshCode(); if (id==="per") code.factors=[{field:"per",min:1,max:15,order:"asc"}];
      drawFactors(); invalidate();
      $("bt-name").value=id==="per"?"저PER 순위 전략":"모멘텀 순위 전략";
      if(id==="per") $("bt-fund-detail").open=true;
    });
    $("bt-strategy-code").addEventListener("input",()=>{dirty=true;updateCodeState();message("bt-code-feedback","편집한 코드를 적용하면 위 조건에도 반영됩니다.");});
    $("bt-code-apply").addEventListener("click",()=>{
      try {
        code=validateCode(JSON.parse($("bt-strategy-code").value));
        drawFactors(); invalidate(); message("bt-code-feedback","코드의 진입·청산·순위 조건을 적용했습니다.");
      } catch(error){message("bt-code-feedback",error instanceof SyntaxError?"JSON 문법을 확인하세요. "+error.message:error.message,true);}
    });
    $("bt-code-reset").addEventListener("click",()=>{reflectCode();invalidate();});
    $("bt-upgrade").addEventListener("click",()=>{legacy=false;drawFactors();showSchedule();invalidate();});
    $("bt-frequency").addEventListener("change",showSchedule);
    function showRows(status="") {
      $("bt-eps-count").textContent=rows.length.toLocaleString("ko-KR")+"행";
      $("bt-eps-clear").hidden=!rows.length;
      message("bt-eps-feedback",status || (rows.length?"등록됨 · "+new Set(rows.map(r=>r.symbol)).size+"개 종목":""));
    }
    $("bt-eps-clear").addEventListener("click",()=>{fileRevision++; uploadPending=false; rows=[]; $("bt-eps-file").value="";showRows();invalidate();});
    $("bt-eps-file").addEventListener("change",async()=>{
      const rev=++fileRevision, file=$("bt-eps-file").files[0]; if(!file)return;
      rows=[]; uploadPending=true; showRows("자료를 읽는 중입니다.");
      try{
        if(file.size>24*1024*1024) throw new Error("CSV 파일은 24 MiB 이하로 선택하세요.");
        const data=await api("/api/backtests/fundamentals/import",{market,csv:await file.text()});
        if(rev!==fileRevision)return;
        if(!Array.isArray(data.fundamentals)) throw new Error("EPS 행을 읽지 못했습니다.");
        rows=data.fundamentals;showRows();
      }catch(e){if(rev===fileRevision){showRows();message("bt-eps-feedback",e.message,true);}}
      finally{if(rev===fileRevision){uploadPending=false;invalidate();}}
    });
    $("bt-eps-sample").addEventListener("click",()=>{
      const symbol=market==="KR"?"005930.KS":"AAPL";
      const url=URL.createObjectURL(new Blob(["\ufeffsymbol,available_date,eps\r\n"+symbol+",YYYY-MM-DD,\r\n"],{type:"text/csv;charset=utf-8"}));
      const a=create("a");a.href=url;a.download="EPS-"+market+"-template.csv";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    });

    function choicesLabel(values) {return values.length?values.join(", "):"전체";}
    function scopeLabel(){
      $("bt-scope-count").textContent="거래소 "+(scope.exchanges.length?scope.exchanges.length+"개":"전체")+" · 업종 "+(scope.sectors.length+scope.industries.length?(scope.sectors.length+scope.industries.length)+"개 선택":"전체");
      $("bt-deposit-unit").textContent=market==="KR"?"(KRW)":"(USD)";
    }
    function check(label, checked, onChange) {
      const wrap=create("label",null,"bt-check"); const input=create("input"); input.type="checkbox";input.checked=checked;
      input.addEventListener("change",onChange);wrap.append(input,document.createTextNode(label));return wrap;
    }
    let exchangesEmpty=false, industriesEmpty=false;
    function controls(title, action) {
      const line=create("div",null,"bt-subhead"), group=create("div",null,"bt-check-actions");
      for(const [label,all] of [["전체 선택",true],["해제",false]]){
        const b=create("button",label,"text-button");b.type="button";b.onclick=()=>action(all);group.append(b);
      }
      line.append(create("h4",title),group);return line;
    }
    function renderCatalog() {
      if(!options)return;
      const exHost=$("bt-exchanges"), inHost=$("bt-industries");
      const exchanges=options.exchanges||[], sectors=options.sectors||[];
      exHost.replaceChildren(); inHost.replaceChildren();
      const selectedEx=new Set(exchangesEmpty?[]:scope.exchanges.length?scope.exchanges:exchanges.map(e=>e.id));
      const selectedItems=new Map();
      for(const s of sectors){
        const complete=!industriesEmpty && ((!scope.sectors.length&&!scope.industries.length) || scope.sectors.includes(s.id));
        const children=s.industries?.length?s.industries.map(c=>c.id):[s.id];
        selectedItems.set(s.id,new Set(complete?children:children.filter(id=>scope.industries.includes(id))));
      }
      function collect() {
        exchangesEmpty=exchanges.length>0 && !selectedEx.size;
        scope.exchanges=selectedEx.size===exchanges.length?[]:[...selectedEx];
        let all=true, any=false;
        scope.sectors=[];scope.industries=[];
        for(const s of sectors){
          const set=selectedItems.get(s.id);
          const complete=set.size>0 && set.size===(s.industries?.length||1);
          if(complete)scope.sectors.push(s.id);else scope.industries.push(...set);
          any||=!!set.size;all&&=complete;
        }
        if(all) {scope.sectors=[];scope.industries=[];}
        industriesEmpty=sectors.length>0&&!any;
        scopeLabel();
        if(exchangesEmpty || industriesEmpty)$("bt-scope-count").textContent="선택된 "+(exchangesEmpty?"거래소":"업종")+" 없음";
        invalidate();
      }
      const exGrid=create("div",null,"bt-check-grid"),exChecks=[];
      for (const ex of exchanges){
        const el=check(ex.label,selectedEx.has(ex.id),ev=>{
          if(ev.target.checked)selectedEx.add(ex.id);else selectedEx.delete(ex.id);collect();
        });
        exChecks.push(el.firstChild);exGrid.append(el);
      }
      exHost.append(controls("거래소",all=>{selectedEx.clear();if(all)exchanges.forEach(ex=>selectedEx.add(ex.id));exChecks.forEach(c=>c.checked=all);collect();}),exGrid);
      const groupControls=[];
      inHost.append(controls("업종",all=>{for(const draw of groupControls)draw(all);collect();}));
      for(const sector of sectors){
        const group=create("div",null,"bt-industry-group"),set=selectedItems.get(sector.id);
        const children=sector.industries||[], ids=children.length?children.map(c=>c.id):[sector.id];
        const detail=create("details"), header=create("summary",sector.label);
        const row=check(sector.label,false,ev=>{update(ev.target.checked);collect();});
        const parentBox=row.firstChild, checks=[];
        function status(){
          parentBox.checked=set.size===ids.length;
          parentBox.indeterminate=set.size>0&&!parentBox.checked;
        }
        function update(all) {
          set.clear();if(all)ids.forEach(id=>set.add(id));checks.forEach(c=>c.checked=all);status();
        }
        if(children.length) {
          header.textContent=sector.label+" 상세 업종 ("+children.length+")";detail.append(header);
          const grid=create("div",null,"bt-check-grid");
          for(const c of children) {
            const item=check(c.label,set.has(c.id),ev=>{
              if(ev.target.checked)set.add(c.id);else set.delete(c.id);status();collect();
            });
            checks.push(item.firstChild);grid.append(item);
          }
          detail.append(grid);
        }
        status();groupControls.push(update);group.append(row);if(children.length)group.append(detail);inHost.append(group);
      }
      if(!sectors.length) inHost.append(create("p","이 목록에서 조회할 수 있는 업종이 없습니다.","cost-note"));
      $("bt-market-meta").textContent=[options.source,options.as_of,options.warning].filter(Boolean).join(" · ");
    }
    async function loadOptions() {
      if((legacy && activeEngine!=="pine") || loadPending || options)return;
      const ticket=generation, reqMarket=market; loadPending=true;
      $("bt-market-meta").textContent="거래소와 업종 목록을 읽는 중입니다."; $("bt-scope-retry").hidden=true;
      try {
        const data=catalog.get(reqMarket) || await api("/api/backtests/universe-options?market="+reqMarket);
        if(ticket!==generation)return;
        if(!Array.isArray(data.exchanges)||!Array.isArray(data.sectors))throw new Error("거래소·업종 목록 형식을 확인할 수 없습니다.");
        options=data;catalog.set(reqMarket,data);renderCatalog();
      } catch(e){if(ticket===generation){$("bt-market-meta").textContent=e.message;$("bt-scope-retry").hidden=false;}}
      finally{if(ticket===generation)loadPending=false;}
    }
    $("bt-scope-details").addEventListener("toggle",()=>{if($("bt-scope-details").open)loadOptions();});
    $("bt-scope-retry").addEventListener("click",loadOptions);

    function setScope(nextMode,nextMarket,nextEngine) {
      mode=nextMode;activeEngine=nextEngine;
      $("bt-universe-options").hidden=legacy && activeEngine!=="pine";
      if(market!==nextMarket){
        market=nextMarket; scope={exchanges:[],sectors:[],industries:[]};options=null;loadPending=false;generation++;
        exchangesEmpty=false;industriesEmpty=false;rows=[];fileRevision++;uploadPending=false;$("bt-eps-file").value="";showRows();
        $("bt-exchanges").replaceChildren();$("bt-industries").replaceChildren();$("bt-market-meta").textContent="";
        if($("bt-scope-details").open)loadOptions();
      }
      scopeLabel();
    }
    function restoreScope(value) {
      scope=structuredClone(value||{exchanges:[],sectors:[],industries:[]});
      for(const key of ["exchanges","sectors","industries"])scope[key]??=[];
      exchangesEmpty=false;industriesEmpty=false;scopeLabel();renderCatalog();
    }
    function readScope() {
      if(exchangesEmpty || industriesEmpty) throw new Error("검증할 거래소와 업종을 각각 하나 이상 선택하세요.");
      return structuredClone(scope);
    }
    function restore(def) {
      legacy=!def.strategy_code;
      code=legacy?{version:1,entry:"technical",exit:"technical",factors:[{field:"momentum",order:def.ranking==="momentum_low"?"asc":"desc"}]}:
        validateCode(typeof def.strategy_code==="string"?JSON.parse(def.strategy_code):structuredClone(def.strategy_code));
      scope=structuredClone(def.universe||{exchanges:[],sectors:[],industries:[]});
      for(const key of ["exchanges","sectors","industries"])scope[key]??=[];
      exchangesEmpty=false;industriesEmpty=false;
      rows=(def.fundamentals||[]).slice();fileRevision++;uploadPending=false;$("bt-eps-file").value="";showRows();
      $("bt-frequency").value=def.rebalance?.frequency||"daily";$("bt-month").value=def.rebalance?.month||3;
      $("bt-contribution").value=def.monthly_contribution||0;$("bt-dividends").checked=!!def.dividends;
      drawFactors();showSchedule();scopeLabel();renderCatalog();
      if(!legacy && $("bt-scope-details").open && !options)loadOptions();
    }
    function read() {
      if(legacy)return {};
      if(dirty)throw new Error("편집한 전략 코드를 적용하거나 편집 취소를 누르세요.");
      if(uploadPending) throw new Error("EPS 자료를 읽은 뒤 다시 확인하세요.");
      if(exchangesEmpty || industriesEmpty)throw new Error("검증할 거래소와 업종을 각각 하나 이상 선택하세요.");
      validateCode(code);
      return {strategy_code:structuredClone(code),rebalance:{frequency:$("bt-frequency").value,month:Number($("bt-month").value)},
        universe:structuredClone(scope),fundamentals:rows.slice(),dividends:$("bt-dividends").checked,monthly_contribution:Number($("bt-contribution").value)};
    }
    function summary(def) {
      const s=def.settings, u=def.universe||{}, money=v=>Number(v).toLocaleString("ko-KR"), unit=def.market==="KR"?"원":" USD";
      const parts=[def.market==="KR"?"국내":"미국",labelMode(def.mode),s.start_date+" ~ "+s.end_date,
        "시작 자본 "+money(s.initial_capital)+unit, "최대 "+def.max_positions+"종목",
        "수수료 "+s.fee_bps+"bp / 슬리피지 "+s.slippage_bps+"bp"];
      if(def.strategy_code)parts.push("거래소 "+choicesLabel(u.exchanges||[]),u.sectors?.length || u.industries?.length?"업종 제한 적용":"전체 업종",
        frequencyNames[def.rebalance.frequency]+(["quarterly","annual"].includes(def.rebalance.frequency)?" ("+def.rebalance.month+"월 기준)":""),
        "월 납입 "+money(def.monthly_contribution)+unit,def.dividends?"현금 배당 포함":"현금 배당 제외");
      if(def.strategy_code) {
        const c=def.strategy_code;
        parts.push(c.entry==="ranked"?"상위 종목 편입":"기술 진입 + 순위",c.exit==="rank_drop"?"순위 이탈 매도":c.exit==="technical"?"기술 신호 매도":"순위 이탈·기술 매도");
        for(const f of c.factors)parts.push(fields[f.field]+" "+(f.min??"−∞")+" ~ "+(f.max??"∞")+" "+(f.order==="asc"?"오름차순":"내림차순"));
      }
      return parts.join(" · ");
    }
    drawFactors();scopeLabel();showSchedule();showRows();
    return {setScope,restore,restoreScope,readScope,summary,read};
  }
  function pineTemplate({api,message,setBusy,rules,defaults}) {
    const pane=create("details",null,"bt-disclosure bt-pine-template");
    pane.id="bt-pine-template";
    pane.innerHTML=`<summary>실행 조건으로 Pine 전략 코드 만들기</summary>
      <div class="bt-disclosure-body"><p class="cost-note">시장과 비용, 기간을 일봉 예제 코드에 넣습니다. 직접 붙여넣은 Pine은 자체 코드와 TradingView의 전략 속성을 사용합니다.</p>
      <div class="studio-fields">
        <div><label for="bt-pine-market" class="field-label">시장 · 기준 통화</label><select id="bt-pine-market"><option value="KR">국내 · KRW</option><option value="US">미국 · USD</option></select></div>
        <div><label for="bt-pine-rule" class="field-label">기술 전략</label><select id="bt-pine-rule"></select></div>
        <div><label for="bt-pine-start" class="field-label">시작일</label><input id="bt-pine-start" type="date" required></div>
        <div><label for="bt-pine-end" class="field-label">종료일</label><input id="bt-pine-end" type="date" required></div>
        <div><label for="bt-pine-capital" class="field-label">초기 자본 (KRW)</label><input id="bt-pine-capital" type="number" value="100000000" min="1" max="1000000000000000" step="any" required></div>
        <div><label for="bt-pine-fee" class="field-label">편도 수수료 (bp)</label><input id="bt-pine-fee" type="number" min="0" max="1000" step="any" value="5" required></div>
        <div><label for="bt-pine-slippage" class="field-label">슬리피지 (틱)</label><input id="bt-pine-slippage" type="number" min="0" max="1000" step="1" value="1" required></div>
      </div><button type="button" id="bt-pine-generate" class="button ghost compact">조건으로 Pine 코드 만들기</button>
      <p id="bt-pine-template-feedback" class="feedback" role="status"></p></div>`;
    $("tv-code").before(pane);
    for(const [id,rule] of Object.entries(rules)) $("bt-pine-rule").add(new Option(rule.title,id));
    const format=date=>[date.getFullYear(),String(date.getMonth()+1).padStart(2,"0"),String(date.getDate()).padStart(2,"0")].join("-");
    const end=new Date();end.setDate(end.getDate()-1); const start=new Date(end);start.setFullYear(end.getFullYear()-1);
    $("bt-pine-start").value=format(start);$("bt-pine-end").value=format(end);
    $("bt-pine-market").addEventListener("change",()=>{
      if ($("bt-market").value!==$("bt-pine-market").value) {
        $("bt-market").value=$("bt-pine-market").value; $("bt-market").dispatchEvent(new Event("change",{bubbles:true}));
      }
      const kr=$("bt-pine-market").value==="KR";
      pane.querySelector("label[for='bt-pine-capital']").textContent="초기 자본 ("+(kr?"KRW":"USD")+")";
      if (["100000000","100000"].includes($("bt-pine-capital").value)) $("bt-pine-capital").value=kr?100000000:100000;
    });
    $("bt-pine-generate").addEventListener("click",()=>setBusy($("bt-pine-generate"),"bt-pine-template-feedback",async()=>{
      for(const input of pane.querySelectorAll("input")) if(!input.reportValidity())return;
      const capture=()=>JSON.stringify({market:$("bt-pine-market").value,settings:{
        ...defaults,strategy:$("bt-pine-rule").value,start_date:$("bt-pine-start").value,end_date:$("bt-pine-end").value,
        initial_capital:Number($("bt-pine-capital").value),fee_bps:Number($("bt-pine-fee").value),
        slippage_mode:"ticks",slippage_ticks:Number($("bt-pine-slippage").value)}});
      const body=capture(), before=$("tv-code").value;
      if(before.trim() && !window.confirm("편집 중인 Pine 코드를 이 조건으로 만든 예제로 바꿀까요?"))return;
      const data=await api("/api/backtests/pine-template",JSON.parse(body));
      if($("tv-code").value!==before || capture()!==body)throw new Error("입력이 바뀌었습니다. 조건을 확인하고 다시 만드세요.");
      if(!data.code || data.timeframe!=="1D")throw new Error("일봉 Pine 예제 응답을 확인할 수 없습니다.");
      $("tv-code").value=data.code;$("tv-timeframe").value=data.timeframe;$("tv-code").dispatchEvent(new Event("input",{bubbles:true}));
      message("bt-pine-template-feedback",data.currency+" 기준 일봉 전략을 만들었습니다. 같은 시장의 종목을 선택하고 코드를 확인하세요.");
    }));
  }
  window.HyperpassPortfolioConditions={mount,pineTemplate};
})();
