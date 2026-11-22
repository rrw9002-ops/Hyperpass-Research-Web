'use strict';
(function(){
  const root=document.getElementById('workspace-screener');
  const columns={price:'현재가',market_cap:'시가총액',turnover:'추정 거래대금',per:'PER',pbr:'PBR',roe:'ROE (%)',margin:'영업이익률 (%)',debt:'부채/자본 (배)',volume:'거래량',income:'순이익 (TTM)',price_date:'가격 기준일',fiscal_date:'재무 기준일'};
  const numeric=Object.keys(columns).filter(k=>!k.endsWith('_date'));
  let data,market='KR',sort='market_cap',asc=false,page=0,version=0;
  let filtered=[],chosen=new Map(),shown=new Set(['price','market_cap','turnover','per','pbr','roe']);
  const size=40,$=id=>document.getElementById('sc-'+id);
  function node(tag,content,cls){const el=document.createElement(tag);if(content!=null)el.textContent=content;if(cls)el.className=cls;return el}
  function button(label,fn){const b=node('button',label,'button ghost compact');b.type='button';b.onclick=fn;return b}
  function option(sel,value,label){sel.add(new Option(label,value))}
  root.innerHTML=`<div class="workspace-heading"><div><span class="eyebrow">EQUITY SCREENER</span><h1>종목 스크리너</h1><p>국내·미국 상장 종목을 같은 조건으로 찾고, 후보를 골라 비교하세요.</p></div></div>
  <div class="sc-layout"><form id="sc-form" class="panel sc-controls"><h2>검색 조건</h2><label>시장<select id="sc-market"><option value="KR">국내 · KRW</option><option value="US">미국 · USD</option></select></label>
  <label>종목명 또는 티커<input id="sc-query" type="search" placeholder="예: 삼성전자, 005930, AAPL"></label>
  <fieldset><legend>거래소</legend><div id="sc-venues" class="sc-checks"></div></fieldset>
  <label>섹터<select id="sc-sector"></select></label><label>업종<select id="sc-industry"></select></label>
  <fieldset><legend>빠른 조건</legend><div id="sc-presets" class="sc-presets"></div></fieldset>
  <fieldset><legend>지표 범위</legend><div id="sc-ranges"></div><button type="button" id="sc-add" class="text-button">＋ 조건 추가</button></fieldset>
  <div class="sc-actions"><button type="button" id="sc-reset" class="button ghost">초기화</button><button class="button primary" id="sc-search">검색하기</button></div></form>
  <div class="sc-output"><section class="panel"><div class="panel-heading"><div><span class="section-kicker">MARKET SNAPSHOT</span><h2>검색 결과 <span id="sc-count"></span></h2></div><button type="button" id="sc-refresh" class="button ghost compact">시세 다시 조회</button></div>
  <p id="sc-status" role="status" class="feedback"></p><p id="sc-date" class="small-muted"></p>
  <div class="sc-actions"><button id="sc-compare" class="button ghost compact">선택 비교</button><button id="sc-backtest" class="button ghost compact">선택 종목 백테스트</button><button id="sc-csv" class="button ghost compact">CSV 다운로드</button>
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
    const val=r[k];if(val==null)return '—';if(typeof val==='string')return val;
    const suffix=k==='income'?(r.income_currency||''):['market_cap','turnover','price'].includes(k)?r.currency:'';
    return val.toLocaleString('ko-KR',{maximumFractionDigits:2})+(suffix?' '+suffix:'');
  }
  function sortRows(){filtered.sort((a,b)=>{const x=a[sort],y=b[sort];if(x==null||y==null)return Number(x==null)-Number(y==null);const c=typeof x==='number'?x-y:String(x).localeCompare(y,'ko');return (asc?c:-c)||a.id.localeCompare(b.id)})}
  function apply(){
    if(!data)return;
    const ranges=[];
    for(const row of $('ranges').children){const [sel,lo,hi]=row.children;if(!lo.checkValidity()||!hi.checkValidity()){message('숫자 범위를 확인하세요.');return}const min=lo.value===''?null:Number(lo.value),max=hi.value===''?null:Number(hi.value);if(min!=null&&max!=null&&min>max){message('최솟값이 최댓값보다 큽니다.');return}if(min!=null||max!=null)ranges.push([sel.value,min,max])}
    const venues=new Set([...$('venues').querySelectorAll(':checked')].map(o=>o.value)),q=$('query').value.trim().toLocaleLowerCase();
    filtered=data.rows.filter(r=>venues.has(r.exchange)&&(!$('sector').value||r.sector===$('sector').value)&&(!$('industry').value||r.industry===$('industry').value)&&(!q||[r.name,r.symbol,r.yahoo,r.id,r.aliases||''].some(v=>String(v).toLocaleLowerCase().includes(q)))&&ranges.every(([k,lo,hi])=>r[k]!=null&&(lo==null||r[k]>=lo)&&(hi==null||r[k]<=hi)));
    page=0;sortRows();message(data.warning||'');render();
  }
  function header(tr,key,label){const th=node('th');if(key){if(sort===key)th.setAttribute('aria-sort',asc?'ascending':'descending');th.append(button(label+(sort===key?(asc?' ↑':' ↓'):''),()=>{asc=sort===key?!asc:key==='name'||key==='industry';sort=key;sortRows();page=0;render()}))}else th.textContent=label;tr.append(th)}
  function updateSelection(){$('compare').textContent=`선택 비교 (${chosen.size})`;$('compare').disabled=!chosen.size;$('backtest').disabled=!chosen.size}
  function render(){
    const head=node('tr');header(head,null,'선택');header(head,'name','종목명 · 티커');header(head,'industry','업종');
    for(const k of shown)header(head,k,columns[k]);header(head,null,'연결');$('head').replaceChildren(head);$('rows').replaceChildren();
    for(const r of filtered.slice(size*page,size*(page+1))){
      const tr=node('tr'),c=node('td');check(c,'',r.id,chosen.has(r.id),ev=>{if(ev.target.checked){if(chosen.size>=6){ev.target.checked=false;message('한 번에 최대 6개 종목을 비교할 수 있습니다.');return}chosen.set(r.id,r)}else chosen.delete(r.id);updateSelection();if(!$('detail').hidden)compare()}).setAttribute('aria-label',r.name+' 비교 선택');tr.append(c);
      const id=node('td');id.append(node('strong',r.name),node('small',`${r.symbol} · ${r.exchange}`));tr.append(id,node('td',r.industry||'—'));
      for(const k of shown)tr.append(node('td',amount(k,r)));
      const actions=node('td');actions.append(button('차트',()=>window.HyperpassChart.openSymbol(r.yahoo)),button('관심 +',async()=>{try{await window.HyperpassApp.api('/api/watchlist',{method:'POST',body:{symbol:r.id}});message(`${r.name}을 관심종목에 저장했습니다.`)}catch(e){message(e.message)}}));tr.append(actions);$('rows').append(tr);
    }
    $('count').textContent=filtered.length.toLocaleString('ko-KR')+' 종목';$('page').textContent=`${filtered.length?page+1:0} / ${Math.ceil(filtered.length/size)}`;$('prev').disabled=!page;$('next').disabled=(page+1)*size>=filtered.length;$('csv').disabled=!filtered.length;updateSelection();
    if(data&&!filtered.length){const td=node('td','조건에 맞는 종목이 없습니다.');td.colSpan=shown.size+4;const tr=node('tr');tr.append(td);$('rows').append(tr)}
  }
  function compare(){if(!chosen.size){$('detail').hidden=true;return}const t=node('table'),head=node('tr');head.append(node('th','항목'));const rows=[...chosen.values()];for(const r of rows)head.append(node('th',`${r.name} · ${r.symbol}`));t.append(head);for(const [k,label] of Object.entries(columns)){const tr=node('tr');tr.append(node('th',label));for(const r of rows)tr.append(node('td',amount(k,r)));t.append(tr)}$('matrix').replaceChildren(t);$('detail').hidden=false}
  function csv(){const keys=['name','symbol','exchange','sector','industry','currency','income_currency',...shown],labels=['종목명','티커','거래소','섹터','업종','통화','재무 통화',...[...shown].map(k=>columns[k])];const escape=v=>{let s=String(v??'');if(typeof v==='string'&&/^[\t\r\n ]*[=+\-@]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"'};
    const blob=new Blob(['\uFEFF'+[labels,...filtered.map(r=>keys.map(k=>k==='symbol'&&/^\d+$/.test(r.symbol)?r.id:r[k]))].map(row=>row.map(escape).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download=`Hyperpass-${market}-${data.as_of.slice(0,10)}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function load(){
    const request=++version;market=$('market').value;data=null;chosen.clear();filtered=[];page=0;$('detail').hidden=true;$('venues').replaceChildren();choices($('sector'),[]);industries();$('date').textContent='';render();message('거래소 상장 목록과 시세·재무 지표를 조회하고 있습니다…');$('search').disabled=true;
    try{const got=await window.HyperpassApp.api('/api/screener?market='+market);if(version!==request)return;data=got;for(const [v,label] of Object.entries(data.exchanges))if(data.rows.some(r=>r.exchange===v))check($('venues'),label,v,true,()=>{});choices($('sector'),data.rows.map(r=>r.sector));industries();const dates=data.rows.map(r=>r.price_date).filter(Boolean).sort();$('date').textContent=`TradingView · 조회 ${new Date(data.as_of).toLocaleString('ko-KR')} · 최근 가격 기준일 ${dates.at(-1)||'미제공'} · 상장 목록 ${data.listed_count.toLocaleString('ko-KR')}종목 중 지표 조회 ${data.rows.length.toLocaleString('ko-KR')}종목. 재무 기준일은 종목별 열에서 확인하세요. 추정 거래대금은 가격 × 거래량입니다.`;apply()}
    catch(e){if(request===version)message(e.message)}finally{if(request===version)$('search').disabled=!data}
  }
  $('form').onsubmit=e=>{e.preventDefault();apply()};$('add').onclick=()=>range();$('sector').onchange=industries;
  $('reset').onclick=()=>{$('ranges').replaceChildren();$('query').value='';$('sector').value='';industries();$('industry').value='';for(const el of $('venues').querySelectorAll('input'))el.checked=true;apply()};
  $('market').onchange=()=>{$('ranges').replaceChildren();$('query').value='';load()};$('refresh').onclick=load;$('prev').onclick=()=>{if(page>0){page--;render()}};$('next').onclick=()=>{if((page+1)*size<filtered.length){page++;render()}};
  $('csv').onclick=csv;$('compare').onclick=()=>{compare();$('detail').scrollIntoView({block:'nearest'})};$('close').onclick=()=>{$('detail').hidden=true};
  $('backtest').onclick=()=>window.HyperpassBacktest.openSymbols({market,symbols:[...chosen.values()].map(r=>r.id)});
  document.addEventListener('hyperpass:workspace-change',e=>{if(e.detail.name==='screener'&&!version)load()});
})();
