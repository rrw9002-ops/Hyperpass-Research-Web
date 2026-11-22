'use strict';
(function(){
  const root=document.getElementById('workspace-screener');
  const columns={price:'현재가',market_cap:'시가총액',turnover:'추정 거래대금',per:'PER',pbr:'PBR',roe:'ROE (%)',margin:'영업이익률 (%)',debt:'부채/자본 (배)',volume:'거래량',income:'순이익',price_time:'시세 시각 (KST)',quote_received_at:'종목 수신 시각 (KST)',delay_minutes:'표시 지연 (분)',price_date:'가격 기준일',fiscal_date:'재무 기준일'};
  const numeric=Object.keys(columns).filter(k=>!['price_date','price_time','quote_received_at','delay_minutes','fiscal_date'].includes(k));
  let data,market='KR',sort='market_cap',asc=false,page=0,version=0;
  let filtered=[],chosen=new Map(),shown=new Set(['price','market_cap','turnover','per','pbr','roe']);
  const size=40,$=id=>document.getElementById('sc-'+id);
  function node(tag,content,cls){const el=document.createElement(tag);if(content!=null)el.textContent=content;if(cls)el.className=cls;return el}
  function button(label,fn){const b=node('button',label,'button ghost compact');b.type='button';b.onclick=fn;return b}
  function option(sel,value,label){sel.add(new Option(label,value))}
  root.innerHTML=`<div class="workspace-heading"><div><span class="eyebrow">EQUITY SCREENER</span><h1>종목 스크리너</h1><p>국내·미국 상장 종목을 같은 조건으로 찾고, 후보를 골라 비교하세요.</p></div></div>
  <div class="sc-layout"><form id="sc-form" class="panel sc-controls"><h2>검색 조건</h2><label>시장<select id="sc-market"><option value="KR">국내 · KRW</option><option value="US">미국 · USD</option></select></label>
  <div id="sc-extras"><label class="sc-extra"><input type="checkbox" id="sc-extra">미제공 재무 지표 보강 · TradingView</label></div><label>종목명 또는 티커<input id="sc-query" type="search" placeholder="예: 삼성전자, 005930, AAPL"></label>
  <fieldset><legend>거래소</legend><div id="sc-venues" class="sc-checks"></div></fieldset>
  <label>섹터<select id="sc-sector"></select></label><label>업종<select id="sc-industry"></select></label>
  <fieldset><legend>빠른 조건</legend><div id="sc-presets" class="sc-presets"></div></fieldset>
  <fieldset><legend>지표 범위</legend><div id="sc-ranges"></div><button type="button" id="sc-add" class="text-button">＋ 조건 추가</button></fieldset>
  <div class="sc-actions"><button type="button" id="sc-reset" class="button ghost">초기화</button><button class="button primary" id="sc-search">검색하기</button></div></form>
  <div class="sc-output"><section class="panel"><div class="panel-heading"><div><span class="section-kicker"><span id="sc-provider">시세 제공자</span></span><h2>검색 결과 <span id="sc-count"></span></h2></div><button type="button" id="sc-refresh" class="button ghost compact">공급자에서 새로 조회</button></div>
  <p id="sc-status" role="status" class="feedback"></p><p id="sc-date" class="small-muted"></p>
  <p id="sc-notes" class="small-muted"></p><details class="sc-coverage"><summary>항목별 출처와 제공 종목 수</summary><ul id="sc-fields"></ul></details><div class="sc-actions"><button id="sc-connect" class="button ghost compact" hidden>KIS 연결 설정</button><button id="sc-page-quotes" class="button ghost compact" hidden>이 페이지 KIS 상세 시세·PER 갱신</button><button id="sc-compare" class="button ghost compact">선택 비교</button><button id="sc-backtest" class="button ghost compact">선택 종목 백테스트</button><button id="sc-csv" class="button ghost compact">CSV 다운로드</button>
  <details><summary>표시할 열</summary><div id="sc-cols" class="sc-checks"></div></details></div>
  <div class="sc-scroll"><table><thead id="sc-head"></thead><tbody id="sc-rows"></tbody></table></div><div class="sc-pages"><button id="sc-prev" class="button ghost compact">이전</button><span id="sc-page"></span><button id="sc-next" class="button ghost compact">다음</button></div></section>
  <section class="panel" id="sc-detail" hidden><div class="panel-heading"><h2>종목 비교</h2><button id="sc-close" class="button ghost compact">닫기</button></div><div id="sc-matrix" class="sc-scroll"></div></section></div></div>`;
  function check(parent,text,value,checked,fn){const label=node('label');const input=node('input');input.type='checkbox';input.value=value;input.checked=checked;input.onchange=fn;label.append(input,document.createTextNode(text));parent.append(label);return input}
  function range(field='per',low='',high=''){
    const div=node('div',null,'sc-range'),sel=node('select');sel.setAttribute('aria-label','지표');for(const k of numeric)option(sel,k,columns[k]);
    sel.value=field;div.append(sel);for(const [label,n] of [['최솟값',low],['최댓값',high]]){const input=node('input');input.type='number';input.step='any';input.placeholder=label;input.setAttribute('aria-label',label);input.value=n;div.append(input)}
    const rm=button('×',()=>div.remove());rm.setAttribute('aria-label','조건 삭제');div.append(rm);$('ranges').append(div);
  }
  function choices(select,items){const old=select.value;select.replaceChildren();option(select,'','전체');for(const val of [...new Set(items.filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ko')))option(select,val,val);if([...select.options].some(o=>o.value===old))select.value=old}
  function industries(){choices($('industry'),(data?.rows||[]).filter(r=>!$('sector').value||r.sector===$('sector').value).map(r=>r.industry))}
  const presets={'저평가':()=>[['per',1,15]],'수익성 우수':()=>[['roe',15,'']],'낮은 부채·흑자':()=>[['debt',0,1],['income',1,'']],'높은 영업이익률':()=>[['margin',15,'']],'거래대금 상위':()=>[['turnover',market==='KR'?1e10:1e7,'']],'대형주':()=>[['market_cap',market==='KR'?1e12:1e10,'']]};
  for(const [label,get] of Object.entries(presets))$('presets').append(button(label,()=>{$('ranges').replaceChildren();for(const row of get())range(...row);apply()}));
  for(const [k,label] of Object.entries(columns))check($('cols'),label,k,shown.has(k),event=>{if(event.target.checked)shown.add(k);else shown.delete(k);render()});
  function message(text){$('status').textContent=text}
  function amount(k,r){
    const val=r[k];if(val==null)return '—';if(k==='price_time'||k==='quote_received_at')return dateText(val);if(typeof val==='string')return val;
    const suffix=k==='income'?(r.income_currency||''):['market_cap','turnover','price'].includes(k)?r.currency:'';
    return val.toLocaleString('ko-KR',{maximumFractionDigits:2})+(suffix?' '+suffix:'')+(r.supplement_fields?.includes(k)?' *':'');
  }
  function sortRows(){filtered.sort((a,b)=>{const x=a[sort],y=b[sort];if(x==null||y==null)return Number(x==null)-Number(y==null);const c=typeof x==='number'?x-y:String(x).localeCompare(y,'ko');return (asc?c:-c)||a.id.localeCompare(b.id)})}
  function apply(){
    if(!data)return;
    const ranges=[];
    for(const row of $('ranges').children){const [sel,lo,hi]=row.children;if(!lo.checkValidity()||!hi.checkValidity()){message('숫자 범위를 확인하세요.');return}const min=lo.value===''?null:Number(lo.value),max=hi.value===''?null:Number(hi.value);if(min!=null&&max!=null&&min>max){message('최솟값이 최댓값보다 큽니다.');return}if(min!=null||max!=null)ranges.push([sel.value,min,max])}
    const venues=new Set([...$('venues').querySelectorAll(':checked')].map(o=>o.value)),q=$('query').value.trim().toLocaleLowerCase();
    filtered=data.rows.filter(r=>venues.has(r.exchange)&&(!$('sector').value||r.sector===$('sector').value)&&(!$('industry').value||r.industry===$('industry').value)&&(!q||[r.name,r.symbol,r.yahoo,r.id,r.aliases||''].some(v=>String(v).toLocaleLowerCase().includes(q)))&&ranges.every(([k,lo,hi])=>r[k]!=null&&(lo==null||r[k]>=lo)&&(hi==null||r[k]<=hi)));
    page=0;sortRows();const missing=ranges.filter(([k])=>!data.rows.some(r=>r[k]!=null));message([data.warning,missing.length?'이번 자료에 '+missing.map(([k])=>columns[k]).join(', ')+' 관측값이 없습니다. 항목별 출처와 제공 종목 수를 확인하세요.':''].filter(Boolean).join(' '));render();
  }
  function header(tr,key,label){const th=node('th');if(key){if(sort===key)th.setAttribute('aria-sort',asc?'ascending':'descending');th.append(button(label+(sort===key?(asc?' ↑':' ↓'):''),()=>{asc=sort===key?!asc:key==='name'||key==='industry';sort=key;sortRows();page=0;render()}))}else th.textContent=label;tr.append(th)}
  function updateSelection(){$('compare').textContent=`선택 비교 (${chosen.size})`;$('compare').disabled=!chosen.size;$('backtest').disabled=!chosen.size}
  function render(){
    const head=node('tr');header(head,null,'선택');header(head,'name','종목명 · 티커');header(head,'industry','업종');
    for(const k of shown)header(head,k,labelFor(k));header(head,null,'연결');$('head').replaceChildren(head);$('rows').replaceChildren();
    for(const r of filtered.slice(size*page,size*(page+1))){
      const tr=node('tr'),c=node('td');check(c,'',r.id,chosen.has(r.id),ev=>{if(ev.target.checked){if(chosen.size>=6){ev.target.checked=false;message('한 번에 최대 6개 종목을 비교할 수 있습니다.');return}chosen.set(r.id,r)}else chosen.delete(r.id);updateSelection();if(!$('detail').hidden)compare()}).setAttribute('aria-label',r.name+' 비교 선택');tr.append(c);
      const id=node('td');id.append(node('strong',r.name),node('small',`${r.symbol} · ${r.exchange}`));tr.append(id,node('td',r.industry||'—'));
      for(const k of shown)tr.append(node('td',amount(k,r)));
      const actions=node('td');actions.append(button('차트',()=>window.HyperpassChart.openSymbol(r.yahoo)),button('관심 +',async()=>{try{await window.HyperpassApp.api('/api/watchlist',{method:'POST',body:{symbol:r.id}});message(`${r.name}을 관심종목에 저장했습니다.`)}catch(e){message(e.message)}}));tr.append(actions);$('rows').append(tr);
    }
    $('count').textContent=filtered.length.toLocaleString('ko-KR')+' 종목';$('page').textContent=`${filtered.length?page+1:0} / ${Math.ceil(filtered.length/size)}`;$('prev').disabled=!page;$('next').disabled=(page+1)*size>=filtered.length;$('csv').disabled=!filtered.length;updateSelection();
    if(data&&!filtered.length){const td=node('td','조건에 맞는 종목이 없습니다.');td.colSpan=shown.size+4;const tr=node('tr');tr.append(td);$('rows').append(tr)}
  }
  function compare(){if(!chosen.size){$('detail').hidden=true;return}const t=node('table'),head=node('tr');head.append(node('th','항목'));const rows=[...chosen.values()];for(const r of rows)head.append(node('th',`${r.name} · ${r.symbol}`));t.append(head);for(const [k,label] of Object.entries(columns)){const tr=node('tr');tr.append(node('th',labelFor(k)));for(const r of rows)tr.append(node('td',amount(k,r)));t.append(tr)}$('matrix').replaceChildren(t);$('detail').hidden=false}
  function csv(){const keys=['name','symbol','exchange','sector','industry','currency','income_currency','provider','as_of','row_quote_source','row_received','row_price_time','supplement_fields','supplement_fiscal_date',...shown],labels=['종목명','티커','거래소','섹터','업종','통화','재무 통화','시세 제공자','전체 조회 시각','종목별 가격 출처','종목별 수신 시각','공급자 시세 시각','TradingView 보강 항목','보강 재무 기준일',...[...shown].map(k=>labelFor(k))];const escape=v=>{let s=String(v??'');if(typeof v==='string'&&/^[\t\r\n ]*[=+\-@]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"'};
    const blob=new Blob(['\uFEFF'+[labels,...filtered.map(r=>keys.map(k=>k==='provider'?data.source:k==='as_of'?data.as_of:k==='row_quote_source'?r.quote_source:k==='row_received'?r.quote_received_at:k==='row_price_time'?r.price_time:k==='supplement_fields'?(r.supplement_fields||[]).join('|'):k==='symbol'&&/^\d+$/.test(r.symbol)?r.id:r[k]))].map(row=>row.map(escape).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download=`Hyperpass-${market}-${data.as_of.slice(0,10)}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  function dateText(value){
    if(!value)return '미제공';
    if(/^\d{4}-\d{2}-\d{2}$/.test(value))return value;
    const parsed=new Date(value);
    return Number.isNaN(+parsed)?String(value):parsed.toLocaleString('ko-KR',{timeZone:'Asia/Seoul',hour12:false})+' KST';
  }
  function sourceSummary(){
    const values=data.rows.map(r=>r.price_date).filter(Boolean).sort();
    const latest=values.at(-1);
    const priceCount=data.rows.filter(r=>r.price!=null).length;
    $('provider').textContent=data.source||providerName();
    $('date').textContent=[data.cache_status==='stale'?'마지막 성공 자료':data.cache_status==='cached'?'최근 조회 자료':'공급자 조회 완료',
      '앱 수신 '+dateText(data.as_of),data.master_at?'KIS 마스터 게시 '+dateText(data.master_at):null,latest?'가장 최근 가격 기준일 '+latest:null,
      '목록 '+data.listed_count.toLocaleString('ko-KR')+'종목 · 가격 있음 '+priceCount.toLocaleString('ko-KR')+'종목'].filter(Boolean).join(' · ');
    const notes=[data.note,...(data.warnings||[]), data.supplement?'추가 재무 지표를 받은 종목 '+data.supplement_count+'개. 별표(*) 값의 출처는 TradingView입니다.':null];
    $('notes').textContent=notes.filter(Boolean).join(' ');
    $('fields').replaceChildren();
    const notesByField=data.field_notes||data.field_sources||{};
    for(const [k,label] of Object.entries(columns)){
      if(!numeric.includes(k))continue;
      const available=data.rows.filter(r=>r[k]!=null).length;
      const row=node('li',labelFor(k)+' · '+available.toLocaleString('ko-KR')+'종목'+(typeof notesByField[k]==='string'?' · '+notesByField[k]:''));
      $('fields').append(row);
    }
    $('page-quotes').hidden=market!=='KR'||data.quote_mode!=='api';
    $('connect').hidden=market!=='KR'||data.quote_mode==='api';
  }
  function providerName(){return market==='KR'?'한국투자증권(KIS)':'Yahoo Finance'}
  function labelFor(k){return k==='price'&&data?.price_label?data.price_label:k==='turnover'&&data?.turnover_label?data.turnover_label:k==='volume'&&data?.volume_label?data.volume_label:columns[k]}
  async function withProgress(request,selectedMarket,call) {
    let polling=false;
    const interval=setInterval(async()=>{
      if(polling||request!==version)return;
      polling=true;
      try{const pr=await window.HyperpassApp.api('/api/screener/status?market='+selectedMarket);
        if(version===request&&pr.running)message(pr.message+(pr.total?' · '+pr.done.toLocaleString()+' / '+pr.total.toLocaleString():''))}
      catch{}finally{polling=false}
    },1800);
    try{return await call()}finally{clearInterval(interval)}
  }
  async function load(refresh=false){
    const request=++version;market=$('market').value;
    const sameMarket=data?.market===market;
    const selectedVenues=sameMarket?new Set([...$('venues').querySelectorAll(':checked')].map(el=>el.value)):null;
    if(!sameMarket){data=null;chosen.clear();filtered=[];page=0;$('detail').hidden=true;$('venues').replaceChildren();choices($('sector'),[]);industries();$('date').textContent='';$('notes').textContent='';$('fields').replaceChildren();render()}
    $('extras').hidden=market!=='KR';$('connect').hidden=market!=='KR'||sameMarket&&data.quote_mode==='api';$('page-quotes').hidden=true;
    $('provider').textContent=providerName();message(providerName()+'에서 목록과 가격을 조회하는 중입니다…');
    $('search').disabled=true;$('refresh').disabled=true;
    try{
      const query=new URLSearchParams({market});
      if(refresh)query.set('refresh','1');
      if(market==='KR'&&$('extra').checked)query.set('extra','1');
      const got=await withProgress(request,market,()=>window.HyperpassApp.api('/api/screener?'+query));
      if(request!==version)return;
      data=got;const available=new Map(data.rows.map(r=>[r.id,r]));
      chosen=new Map([...chosen.keys()].filter(k=>available.has(k)).map(k=>[k,available.get(k)]));
      $('venues').replaceChildren();
      for(const [v,label] of Object.entries(data.exchanges))if(data.rows.some(r=>r.exchange===v))check($('venues'),label,v,selectedVenues?selectedVenues.has(v):true,()=>{});
      choices($('sector'),data.rows.map(r=>r.sector));industries();sourceSummary();apply();if(!$('detail').hidden)compare();
    }catch(e){if(request===version){if(sameMarket){sourceSummary();message('갱신 실패 · 이전 조회 자료를 표시합니다. '+e.message)}else message(e.message)}}
    finally{if(request===version){$('search').disabled=!data;$('refresh').disabled=false}}
  }
  async function updatePage(){
    if(!data||market!=='KR'||data.quote_mode!=='api')return;
    const symbols=filtered.slice(page*size,(page+1)*size).map(r=>r.symbol);
    if(!symbols.length)return;
    const request=++version;
    $('page-quotes').disabled=true;$('refresh').disabled=true;
    message('현재 페이지의 '+symbols.length+'개 종목을 KIS API로 조회하는 중입니다…');
    try{
      const got=await withProgress(request,market,()=>window.HyperpassApp.api('/api/screener/kis-quotes',{method:'POST',body:{symbols}}));
      if(request!==version)return;
      const updates=new Map(got.rows.map(r=>[r.symbol,r]));
      for(const row of data.rows){
        const patch=updates.get(row.symbol);if(!patch)continue;
        for(const [k,v] of Object.entries(patch))if(v!=null)row[k]=v;
        row.supplement_fields=(row.supplement_fields||[]).filter(k=>patch[k]==null);
      }
      const oldPage=page;sourceSummary();apply();page=Math.min(oldPage,Math.max(0,Math.ceil(filtered.length/size)-1));render();if(!$('detail').hidden)compare();
      message('KIS 상세 시세 '+updates.size+' / '+symbols.length+'종목 갱신 · '+dateText(got.as_of||new Date().toISOString())+' '+(got.warnings||[]).join(' '));
    }catch(e){if(request===version)message(e.message)}
    finally{$('page-quotes').disabled=false;if(request===version)$('refresh').disabled=false}
  }
  $('form').onsubmit=e=>{e.preventDefault();apply()};$('add').onclick=()=>range();$('sector').onchange=industries;
  $('reset').onclick=()=>{$('ranges').replaceChildren();$('query').value='';$('sector').value='';industries();$('industry').value='';for(const el of $('venues').querySelectorAll('input'))el.checked=true;apply()};
  $('market').onchange=()=>{$('ranges').replaceChildren();$('query').value='';load()};$('refresh').onclick=()=>load(true);$('extra').onchange=()=>load();$('page-quotes').onclick=updatePage;$('connect').onclick=()=>document.getElementById('sources-button').click();
  document.addEventListener('hyperpass:source-changed',e=>{if(e.detail==='kis'&&market==='KR'&&!root.hidden)load(true)});$('prev').onclick=()=>{if(page>0){page--;render()}};$('next').onclick=()=>{if((page+1)*size<filtered.length){page++;render()}};
  $('csv').onclick=csv;$('compare').onclick=()=>{compare();$('detail').scrollIntoView({block:'nearest'})};$('close').onclick=()=>{$('detail').hidden=true};
  $('backtest').onclick=()=>window.HyperpassBacktest.openSymbols({market,symbols:[...chosen.values()].map(r=>r.id)});
  document.addEventListener('hyperpass:workspace-change',e=>{if(e.detail.name==='screener'&&!version)load()});
})();
