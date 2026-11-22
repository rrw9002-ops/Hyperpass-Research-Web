"use strict";
(() => {
 const $=id=>document.getElementById(id), node=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls||'';if(text!==undefined)n.textContent=text;return n;};
 const host=$('workspace-chart');if(!host)return;
 host.innerHTML=`<div class="lab-heading"><div><span class="section-kicker">OBSERVE / TEST / UNDERSTAND</span><h1>차트 실험실<span>.</span></h1><p>실제 가격에서 규칙을 검증하고, 기술 분석 에이전트와 해석하세요.</p></div><span class="lab-badge">연구 전용 · 주문 없음</span></div>
 <div class="lab-grid"><form id="chart-form" class="panel lab-controls">
 <div class="panel-heading"><h2>데이터와 가설</h2><span class="small-muted">01 — SETUP</span></div>
 <label for="chart-source" class="field-label">차트 데이터</label><select id="chart-source"><option value="yahoo">Yahoo Finance · 키 없이 조회</option><option value="tradingview">TradingView · 열린 Desktop 차트</option><option value="csv">TradingView · CSV 가져오기</option></select>
 <label for="chart-symbol" class="field-label">종목명 또는 티커</label><input id="chart-symbol" maxlength="80" required autocomplete="off" spellcheck="false" placeholder="예: 삼성전자, 애플 또는 AAPL" aria-describedby="chart-symbol-status"><div id="chart-symbol-matches" class="tv-symbol-matches"></div><p id="chart-symbol-status" class="small-muted" aria-live="polite"></p>
 <div class="field-pair"><div><label for="chart-period" class="field-label">조회 기간</label><select id="chart-period"><option value="1y">1년</option><option value="2y" selected>2년</option><option value="5y">5년</option></select></div><div><label for="chart-interval" class="field-label">차트 주기</label><select id="chart-interval"><option value="1d">일봉</option><option value="1wk">주봉</option><option value="1mo">월봉</option></select></div></div><p id="chart-source-hint" class="cost-note"></p>
 <div id="chart-desktop" hidden><label class="field-label" for="chart-port">Desktop 연결 포트</label><input id="chart-port" type="number" value="9222" min="1024" max="65535"><p class="cost-note">열린 차트의 종목과 주기를 읽습니다. 최대 500봉을 읽습니다. 거래소가 다른 경우 Desktop에 열린 종목을 선택할 수 있습니다.</p><div class="chart-actions"><button type="button" class="button ghost compact" id="chart-use-desktop">열린 종목 가져오기</button><button type="button" class="text-button" id="chart-desktop-launch">Desktop 연결 실행</button></div><label id="chart-target-block" hidden>열린 차트 탭<select id="chart-target" aria-label="열린 Desktop 차트 탭"></select></label><p id="chart-desktop-status" class="small-muted" role="status"></p></div>
 <div id="chart-csv-block" hidden><label class="field-label" for="chart-csv-file">내보낸 CSV 파일</label><input id="chart-csv-file" type="file" accept=".csv,text/csv"><label class="field-label" for="chart-csv">또는 CSV 붙여넣기</label><textarea id="chart-csv" rows="4" placeholder="time,open,high,low,close,volume"></textarea><p class="cost-note">TradingView 차트 메뉴의 ‘차트 데이터 내보내기’에서 저장한 CSV를 선택하세요. 파일 이름에 거래소와 종목이 있으면 자동으로 채웁니다. 최대 5,000행이며 시가·고가·저가·종가가 필요합니다.</p></div>
 <label for="chart-strategy" class="field-label">검증할 전략</label><select id="chart-strategy"><option value="trend_breakout">강의 ① 추세 돌파</option><option value="mean_reversion">강의 ② 평균 회귀</option><option value="sma_cross">추가 예제 · 이동평균 교차</option><option value="none">지표·차트만 분석</option></select><p id="chart-rule" class="lab-rule"></p>
 <details class="lab-settings"><summary>지표·비용·검증 기간 조정</summary><div class="field-pair"><div><label for="chart-fast" class="field-label">단기 SMA</label><input id="chart-fast" type="number" min="2" max="299" value="20"></div><div><label for="chart-slow" class="field-label">장기 SMA</label><input id="chart-slow" type="number" min="3" max="300" value="60"></div></div><div class="field-pair"><div><label for="chart-breakout" class="field-label">돌파 기준 봉 수</label><input id="chart-breakout" type="number" min="2" max="300" value="20"></div><div><label for="chart-rsi-entry" class="field-label">RSI 진입 기준</label><input id="chart-rsi-entry" type="number" min="1" max="49" value="30"></div></div>
 <div class="field-pair"><div><label for="chart-rsi-period" class="field-label">RSI 기간</label><input id="chart-rsi-period" type="number" min="2" max="300" value="14"></div><div><label for="chart-bb-period" class="field-label">볼린저 기간</label><input id="chart-bb-period" type="number" min="2" max="300" value="20"></div></div><div class="field-pair"><div><label for="chart-bb-std" class="field-label">볼린저 배수</label><input id="chart-bb-std" type="number" min="0.1" max="10" step="0.1" value="2"></div><div><label for="chart-capital" class="field-label">초기 자본 · 시세 통화</label><input id="chart-capital" type="number" min="1" max="1000000000000000" value="100000000"></div></div>
 <div class="field-pair"><div><label for="chart-fee" class="field-label">체결당 수수료 (%)</label><input id="chart-fee" type="number" min="0" max="10" step="0.01" value="0.05"></div><div><label for="chart-slip-mode" class="field-label">슬리피지 단위</label><select id="chart-slip-mode"><option value="bps">bps · 1bp = 0.01%</option><option value="ticks">틱 · 가격 단위 직접 지정</option></select></div></div><div class="field-pair"><div><label for="chart-slip" class="field-label">슬리피지 (bps / 틱)</label><input id="chart-slip" type="number" min="0" max="100" step="1" value="5"></div><div><label for="chart-tick" class="field-label">1틱 가격 · 틱 선택 시</label><input id="chart-tick" type="number" min="0.00000001" step="any" placeholder="예: 0.01"></div></div>
 <div class="field-pair"><div><label for="chart-start" class="field-label">진입 시작일 · UTC</label><input id="chart-start" type="date"></div><div><label for="chart-end" class="field-label">진입 종료일 · UTC</label><input id="chart-end" type="date"></div></div><label for="chart-train" class="field-label">앞 구간 비중 (%) · 뒤 구간은 별도 검증</label><input id="chart-train" type="number" min="50" max="90" value="70"><p class="cost-note">봉 마감에 신호를 만들고 다음 관측 시가에 체결합니다. 롱만 사용하며 추가 매수·자동 최적화는 하지 않습니다.</p></details>
 <button id="chart-submit" class="button primary start-button" type="submit">차트 불러오기 · 전략 검증 ↗</button><p id="chart-feedback" class="feedback" role="status">AI 호출 없이 데이터를 조회하고 계산합니다.</p></form>
 <div class="lab-main"><section class="panel market-overview" aria-labelledby="market-heading"><div class="market-overview-head"><div><span class="section-kicker">MARKET INDICES</span><h2 id="market-heading">시장 지수</h2></div><div class="market-pickers"><div class="market-region" role="group" aria-label="시장 지역"><button class="chip" type="button" data-index-region="kr" aria-pressed="true">국내</button><button class="chip" type="button" data-index-region="us" aria-pressed="false">미국</button></div><select id="market-index" aria-label="시장 지수 선택"><option value="^KS11">코스피</option><option value="^KQ11">코스닥</option></select></div></div><p id="market-index-info" class="small-muted" aria-live="polite"></p><canvas id="market-index-curve" role="img" aria-label="선택한 지수의 최근 3개월 종가" hidden></canvas><button type="button" id="market-index-retry" class="text-button" hidden>다시 조회</button></section><section class="panel lab-chart-panel"><div class="lab-chart-title"><div><span class="section-kicker">02 — PRICE & SIGNALS</span><h2 id="chart-title">가격을 먼저 확인하세요.</h2><p id="chart-provenance">데이터를 불러오면 실제 캔들과 지표가 표시됩니다.</p></div><a id="chart-tv-link" class="text-button" href="https://www.tradingview.com/chart/" target="_blank" rel="noopener noreferrer">TradingView 열기 ↗</a></div>
 <div class="chart-toggles">
   <fieldset class="chart-overlay-field"><legend>가격 차트 표시</legend><div id="chart-overlays" class="chart-overlay-options"></div></fieldset>
   <div class="chart-osc-choice"><label for="chart-subindicator">보조지표</label><select id="chart-subindicator"></select></div>
 </div><p id="chart-overlay-note" class="chart-series-note" hidden></p>
 <div class="price-canvas-wrap"><canvas id="price-canvas" aria-label="실제 OHLCV 가격 차트"></canvas><div id="chart-empty">차트 데이터가 아직 없습니다.<br><small>왼쪽에서 종목과 전략을 선택해 시작하세요.</small></div></div><p id="chart-cursor" class="chart-cursor"></p><details id="chart-overlay-readout" class="chart-overlay-readout"><summary>가격 지표 값</summary><div id="chart-overlay-values"></div></details><div class="chart-indicator-strip"><span id="chart-indicator-period"></span><div id="chart-indicator-values"></div></div><p id="chart-indicator-note" class="chart-series-note" hidden></p><canvas id="indicator-canvas" role="img" aria-label="보조지표 차트"></canvas><div class="chart-navigation"><label>확대 <input id="chart-visible" aria-label="표시할 봉 수" type="range" min="30" max="500" value="150"></label><label>시간 이동 <input id="chart-position" aria-label="차트 구간 이동" type="range" min="0" max="100" value="100"></label></div><div id="chart-latest" class="chart-latest"></div></section>
 <section id="backtest-result" class="panel backtest-panel" hidden><div class="panel-heading"><div><span class="section-kicker">03 — LOCAL BACKTEST</span><h2>가설을 숫자로 확인하기</h2></div><span class="lab-badge">앱 자체 OHLCV 계산</span></div><p class="cost-note">TradingView Strategy Tester 실행 결과가 아닙니다. 자산 곡선에는 미실현 손익이 포함됩니다.</p><div id="chart-metrics" class="chart-metrics"></div><canvas id="equity-canvas" aria-label="미실현 손익 포함 자산 곡선"></canvas><div id="chart-validation" class="chart-validation"></div><details><summary>체결 기록 · 신호와 실행 시점</summary><div class="chart-table-scroll"><table><thead><tr><th>진입 체결</th><th>청산 체결</th><th>진입가</th><th>청산가</th><th>비용 차감 수익률</th></tr></thead><tbody id="chart-trades"></tbody></table></div></details></section>
 <section id="chart-conclusion" class="panel chart-conclusion" hidden><div class="panel-heading"><div><span class="section-kicker">04 — SAVE & INTERPRET</span><h2>데이터에서 해석으로</h2></div><span class="saved-chip">Second Brain에 저장됨</span></div><div class="chart-actions"><button id="chart-ask" class="button primary" type="button">기술 분석 에이전트에게 질문 ↗</button><span id="chart-watch-actions"></span><a id="chart-json" class="button ghost" download>원본 결과 JSON ↓</a><a id="chart-pine" class="button ghost" download>Pine Script ↓</a></div><p class="cost-note">Pine은 표준 일봉용입니다. TradingView 컴파일·실행은 확인 전이며, bps 슬리피지는 Pine에서 1틱 가정으로 바뀝니다. AI 해석은 질문을 확인하고 시작 버튼을 눌렀을 때만 호출합니다.</p><details><summary>데이터 품질·계산 가정·한계</summary><ul id="chart-warnings"></ul><pre id="chart-assumptions"></pre></details></section></div></div>`;
 const oscillators = {
   rsi: {group:'모멘텀', label:'RSI · 상대강도지수', lines:[['rsi','RSI']], bounds:[0,100], guides:[30,70], period:s=>s.rsi_period+'봉'},
   stochastic: {group:'모멘텀', label:'스토캐스틱 · %K / %D', lines:[['stoch_k','%K'],['stoch_d','%D']], bounds:[0,100], guides:[20,80], period:()=>'14 · 3 · 3봉'},
   cci: {group:'모멘텀', label:'CCI · 상품채널지수', lines:[['cci','CCI']], guides:[-100,0,100], period:()=>'20봉'},
   williams_r: {group:'모멘텀', label:'윌리엄스 %R', lines:[['williams_r','%R']], bounds:[-100,0], guides:[-80,-20], period:()=>'14봉'},
   roc: {group:'모멘텀', label:'ROC · 가격 변화율', lines:[['roc','ROC']], guides:[0], unit:'%', period:()=>'12봉'},
   macd: {group:'추세', label:'MACD · 이동평균 수렴·확산', lines:[['macd','MACD'],['macd_signal','신호선'],['macd_histogram','히스토그램']], bars:'macd_histogram', guides:[0], period:()=>'12 · 26 · 9봉'},
   dmi: {group:'추세', label:'ADX / DMI · 추세 강도와 방향', lines:[['adx','ADX'],['di_plus','+DI'],['di_minus','−DI']], bounds:[0,100], guides:[25], period:()=>'14봉'},
   atr: {group:'변동성', label:'ATR · 평균 실변동폭', lines:[['atr','ATR']], guides:[], period:s=>s.atr_period+'봉'},
   obv: {group:'거래량·자금 흐름', label:'OBV · 누적 거래량', lines:[['obv','OBV']], guides:[], volume:true, period:()=>'거래량 결측 후 0에서 재시작'},
   mfi: {group:'거래량·자금 흐름', label:'MFI · 자금흐름지수', lines:[['mfi','MFI']], bounds:[0,100], guides:[20,80], volume:true, period:()=>'14봉'},
   cmf: {group:'거래량·자금 흐름', label:'CMF · 차이킨 자금 흐름', lines:[['cmf','CMF']], guides:[0], volume:true, period:()=>'20봉'}
 };
 const overlays = {
   sma: {label:'단순이평 SMA', description:'단기·장기 단순이동평균', checked:true, lines:[['sma_fast','#ff9858'],['sma_slow','#c4b5ee']]},
   ema: {label:'지수이평 EMA', description:'지수이동평균', lines:[['ema','#d0bf7e']]},
   wma: {label:'가중이평 WMA', description:'최근 봉에 높은 가중치를 둔 20봉 이동평균', lines:[['wma','#8cd5cd']]},
   bollinger: {label:'볼린저 밴드', description:'이동평균과 표준편차로 구한 상·하단', checked:true, lines:[['bb_upper','#a3a59b'],['bb_lower','#a3a59b']]},
   donchian: {label:'돈치안 채널', description:'20봉 최고가·최저가와 중간값', lines:[['donchian_upper','#b9aeef'],['donchian_middle','#b9aeef'],['donchian_lower','#b9aeef']], dash:[5,3]},
   keltner: {label:'켈트너 채널', description:'종가 EMA 20봉과 ATR 10봉의 2배로 구한 상·하단', lines:[['keltner_upper','#85baca'],['keltner_middle','#85baca'],['keltner_lower','#85baca']], dash:[2,3]},
   volume: {label:'거래량', description:'봉별 거래량', checked:true, lines:[]}
 };
 const seriesColors=['#efb876','#b8a8eb','#83c9bc'];
 const indicatorGroups=[...Object.keys(overlays),...Object.keys(oscillators)];
 for(const [key, spec] of Object.entries(overlays)){
   const toggle=document.createElement('input');toggle.type='checkbox';toggle.dataset.overlay=key;toggle.checked=!!spec.checked;
   const label=node('label','chart-overlay-chip');label.title=spec.description; label.dataset.group=key;
   label.append(toggle, document.createTextNode(spec.label));$('chart-overlays').append(label);
 }
 const grouped=new Map();
 for(const [key, spec] of Object.entries(oscillators)){
   if(!grouped.has(spec.group)){
     const category=document.createElement('optgroup');category.label=spec.group;
     grouped.set(spec.group,category);$('chart-subindicator').append(category);
   }
   grouped.get(spec.group).append(new Option(spec.label,key));
 }
 function enabledOverlays(){
   return Array.from($('chart-overlays').querySelectorAll('input:checked'), input=>input.dataset.overlay);
 }
 let current=null,hover=-1,busy=false,sourceRestoreNote='',appliedSettings={};
 const fmt=(x,d=2)=>Number.isFinite(x)?x.toLocaleString('ko-KR',{maximumFractionDigits:d,minimumFractionDigits:d}):'—';
 const pct=x=>Number.isFinite(x)?`${x>0?'+':''}${fmt(x)}%`:'계산 대상 없음';
 function feedback(text,error=false){$('chart-feedback').textContent=text;$('chart-feedback').classList.toggle('error-text',error);}
 function updateSource(){const v=$('chart-source').value;$('chart-desktop').hidden=v!=='tradingview';$('chart-csv-block').hidden=v!=='csv';$('chart-source').required=true;$('chart-period').disabled=v!=='yahoo';$('chart-period').required=v==='yahoo';$('chart-interval').disabled=v==='tradingview';$('chart-interval').required=v==='yahoo'||v==='csv';$('chart-port').required=v==='tradingview';$('chart-symbol').required=v!=='tradingview';const hints={yahoo:'조회 기간·주기는 새로 가져올 Yahoo 가격 이력에 적용됩니다.',tradingview:'열린 Desktop 차트와 연결합니다. 종목을 비워 두면 현재 열린 차트를 사용합니다.',csv:'조회 기간은 CSV에 포함된 실제 봉의 범위입니다. 차트 주기는 원본 파일과 같게 지정하세요.'};$('chart-source-hint').textContent=[hints[v]||'새 조회에 사용할 데이터 출처를 선택하세요.',sourceRestoreNote].filter(Boolean).join(' ');}
 function restoreChoice(id,value,unknownLabel){const input=$(id);input.querySelector('option[data-unrecorded]')?.remove();if([...input.options].some(option=>option.value===value)){input.value=value;return true;}const missing=node('option','',unknownLabel);missing.value='';missing.disabled=true;missing.dataset.unrecorded='true';input.prepend(missing);input.value='';return false;}
 function restoreSource(result){
  const packet=result.source_packet||{},p=result.provenance||{},provider=packet.provider||result.provider||p.provider;
  const source=provider==='yahoo'?'yahoo':provider==='tradingview-csv'||provider==='csv'||packet.mode==='csv'?'csv':provider==='tradingview'?'tradingview':'';
  const notes=[];restoreChoice('chart-source',source,'원본 출처 미확인 · 새 조회 출처 선택');$('chart-symbol').value=result.symbol||packet.symbol||p.symbol||'';
  let savedPeriod=packet.period||packet.range||'',savedInterval=packet.timeframe||packet.interval||result.timeframe||p.timeframe||'';
  if(source==='yahoo')try{const url=new URL(packet.source_url||p.source_url);if(url.protocol==='https:'&&['query1.finance.yahoo.com','query2.finance.yahoo.com'].includes(url.hostname)&&url.pathname.startsWith('/v8/finance/chart/')){savedPeriod=savedPeriod||url.searchParams.get('range')||'';if(!savedInterval||savedInterval==='unknown')savedInterval=url.searchParams.get('interval')||'';}}catch{}
  if(source==='yahoo'){
   if(!restoreChoice('chart-period',savedPeriod,'기록 없음 · 새 조회 기간 선택'))notes.push('원본 조회 기간은 기록에 없습니다. 봉 수로 추정하지 않았으며 새 조회 기간을 직접 선택해야 합니다.');
  }else restoreChoice('chart-period','','원본 자료 범위 사용');
  const interval={'1d':'1d','1D':'1d','D':'1d','1wk':'1wk','1W':'1wk','W':'1wk','1mo':'1mo','1M':'1mo','M':'1mo'}[savedInterval]||'';
  if(!restoreChoice('chart-interval',interval,source==='tradingview'?`Desktop 원본 주기: ${String(savedInterval||'미확인').slice(0,30)}`:'기록 없음 · 새 조회 주기 선택')&&source!=='tradingview')notes.push('원본 주기를 확인한 뒤 새 조회에 사용할 주기를 선택하세요.');
  $('chart-csv-file').value='';$('chart-csv').value='';
  if(source==='csv'){
   const raw=typeof packet.csv==='string'?packet.csv:typeof packet.raw_csv==='string'?packet.raw_csv:null;
   if(raw!==null&&raw.length<=900000){$('chart-csv').value=raw;notes.push('저장된 원본 CSV 내용을 복원했습니다.');}
   else{const rows=Array.isArray(packet.records)?packet.records:result.candles;const quote=value=>{const text=value===null||value===undefined?'':String(value);return /[",\r\n]/.test(text)?'"'+text.replace(/"/g,'""')+'"':text;};const csv=Array.isArray(rows)?['time,open,high,low,close,volume',...rows.map(row=>[row.timestamp??row.time??row.date,row.open,row.high,row.low,row.close,row.volume].map(quote).join(','))].join('\n'):'';if(csv&&csv.length<=900000){$('chart-csv').value=csv;notes.push('원본 CSV 문자열은 저장되지 않아 보존된 OHLCV 행으로 다시 구성했습니다. 원본 파일의 다른 열은 포함하지 않습니다.');}else notes.push('CSV 내용을 복원할 수 없습니다. 다시 계산하려면 원본 파일을 가져오세요.');}
  }
  if(source==='tradingview'){const port=packet.port;const known=Number.isInteger(port)&&port>=1024&&port<=65535;$('chart-port').value=known?String(port):'';if(!known)notes.push('원본 연결 포트는 기록에 없습니다. 다시 읽을 Desktop 포트를 입력하세요.');}
  if(!source)notes.push('원본 출처를 지원하는 조회 방식으로 확인할 수 없습니다. 현재 결과는 저장 기록이며 새 조회 출처를 직접 선택해야 합니다.');
  sourceRestoreNote=notes.join(' ');updateSource();
 }
 function costMode(){const ticks=$('chart-slip-mode').value==='ticks';$('chart-slip').max=ticks?'100':'1000';$('chart-slip').step='any';$('chart-tick').disabled=!ticks;$('chart-tick').required=ticks;}
 function rule(){const rules={trend_breakout:'종가 > 단기 SMA > 장기 SMA + 직전 N봉 고가 돌파에 진입. 단기 SMA 하향 교차에 청산.',mean_reversion:'볼린저 하단 아래 + RSI 진입 기준 미만에 진입. 볼린저 중심선 상향 교차에 청산.',sma_cross:'단기 SMA가 장기 SMA를 위로 교차하면 진입, 아래로 교차하면 청산.',none:'성과를 계산하지 않고 가격·거래량·지표만 확인합니다.'};$('chart-rule').textContent=rules[$('chart-strategy').value];}
 function options(){const n=id=>Number($(id).value),saved=appliedSettings,kept={};for(const key of ['ema_period','atr_period','indicators'])if(saved[key]!==undefined)kept[key]=saved[key];return{...kept,strategy:$('chart-strategy').value,fast_period:n('chart-fast'),slow_period:n('chart-slow'),breakout_period:n('chart-breakout'),rsi_period:n('chart-rsi-period'),rsi_entry:n('chart-rsi-entry'),bb_period:n('chart-bb-period'),bb_std:n('chart-bb-std'),initial_capital:n('chart-capital'),fee_bps:n('chart-fee')*100,slippage_mode:$('chart-slip-mode').value,slippage_bps:$('chart-slip-mode').value==='bps'?n('chart-slip'):(saved.slippage_bps??5),slippage_ticks:$('chart-slip-mode').value==='ticks'?n('chart-slip'):(saved.slippage_ticks??1),tick_size:$('chart-tick').value?n('chart-tick'):null,train_fraction:n('chart-train')/100,start_date:$('chart-start').value,end_date:$('chart-end').value};}
 function surface(id,height){const canvas=$(id);const w=Math.max(200,canvas.clientWidth),dpr=Math.min(window.devicePixelRatio||1,2);canvas.width=w*dpr;canvas.height=height*dpr;const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,w,height);const fontFamily=getComputedStyle(canvas).fontFamily;ctx.font='500 11px '+fontFamily;return{ctx,w,h:height,fontFamily};}
 function chartRange(){const n=current.candles.length,k=Math.min(n,Number($('chart-visible').value)),end=k+Math.round((n-k)*Number($('chart-position').value)/100);return{start:end-k,end,k};}
 function plotLine(ctx,values,start,end,x,y,color,width=1.3){
   if(!Array.isArray(values))return;
   ctx.beginPath();ctx.lineWidth=width;ctx.strokeStyle=color;
   let previousValid=false, length=0;
   const singles=[];
   for(let i=start;i<=end;i++){
     if(i===end || !Number.isFinite(values[i])){
       if(length===1)singles.push(i-1);
       previousValid=false;length=0;
       continue;
     }
     if(previousValid)ctx.lineTo(x(i),y(values[i]));
     else ctx.moveTo(x(i),y(values[i]));
     previousValid=true;length++;
   }
   ctx.stroke();
   ctx.fillStyle=color;
   for(const i of singles){ctx.beginPath();ctx.arc(x(i),y(values[i]),1.5,0,2*Math.PI);ctx.fill();}
 }
 function overlayReading(group, data, settings, candleIndex) {
   if(group==='volume')return '거래량 '+fmt(current.candles[candleIndex].volume,0);
   const names={
     sma_fast:'SMA '+settings.fast_period, sma_slow:'SMA '+settings.slow_period, ema:'EMA '+settings.ema_period, wma:'WMA 20',
     bb_upper:'볼린저 상단',bb_lower:'볼린저 하단',
     donchian_upper:'돈치안 상단',donchian_middle:'돈치안 중심',donchian_lower:'돈치안 하단',
     keltner_upper:'켈트너 상단',keltner_middle:'켈트너 중심',keltner_lower:'켈트너 하단'
   };
   return overlays[group].lines.map(([key])=>names[key]+' '+fmt(data[key]?.[candleIndex])).join(' · ');
 }
 function drawOverlayReadout() {
   if(!$('chart-overlay-readout').open || !current)return;
   const {start,end}=chartRange(), i=hover>=start && hover<end?hover:end-1;
   const groups=enabledOverlays(), container=$('chart-overlay-values');
   container.replaceChildren();
   if(!groups.length){container.textContent='가격 차트에 표시할 지표를 선택하세요.';return;}
   for(const group of groups){
     const row=node('div','chart-overlay-value',overlayReading(group,current.indicators,current.settings,i));
     row.dataset.group=group; container.append(row);
   }
 }
 function drawPrice(){
  const {ctx,w,h,fontFamily}=surface('price-canvas',340);
  if(!current)return;
  const {start,end,k}=chartRange(),bars=current.candles.slice(start,end),plotW=w-65,priceH=265;
  const active=enabledOverlays(), ind=current.indicators;
  const priceLines=active.flatMap(key=>overlays[key].lines.map(([name,color])=>({name,color,dash:overlays[key].dash || []})));
  let low=Math.min(...bars.map(b=>b.low)),high=Math.max(...bars.map(b=>b.high));
  for(const line of priceLines){
    for(const v of (ind[line.name] || []).slice(start,end)){
      if(Number.isFinite(v)){low=Math.min(low,v);high=Math.max(high,v);}
    }
  }
  const pad=(high-low || Math.abs(high)*.01 || 1)*.08,min=low-pad,max=high+pad;
  const x=i=>12+(i-start+.5)*(plotW-15)/k,y=p=>16+(max-p)/(max-min)*(priceH-25);
  ctx.strokeStyle='#2b2923';ctx.fillStyle='#aaa497';
  for(let j=0;j<5;j++){
    const py=16+j*(priceH-25)/4;ctx.beginPath();ctx.moveTo(8,py);ctx.lineTo(plotW,py);ctx.stroke();ctx.fillText(fmt(max-(max-min)*j/4),plotW+8,py+3);
  }
  const candleW=Math.max(1,Math.min(12,(plotW-15)/k*.66)),volMax=Math.max(1,...bars.map(b=>b.volume || 0));
  for(let i=start;i<end;i++){
    const b=current.candles[i],color=b.close>=b.open?'#78c7b1':'#e88c75';
    ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(x(i),y(b.high));ctx.lineTo(x(i),y(b.low));ctx.stroke();
    ctx.fillRect(x(i)-candleW/2,Math.min(y(b.open),y(b.close)),candleW,Math.max(1,Math.abs(y(b.open)-y(b.close))));
    if(active.includes('volume')&&Number.isFinite(b.volume)){
      ctx.globalAlpha=.35;ctx.fillRect(x(i)-candleW/2,h-22-b.volume/volMax*45,candleW,b.volume/volMax*45);ctx.globalAlpha=1;
    }
  }
  for(const {name,color,dash} of priceLines){
    ctx.setLineDash(dash);plotLine(ctx,ind[name],start,end,x,y,color);
  }
  ctx.setLineDash([]);
  const missing=active.filter(key=>key==='volume'
    ? !bars.some(b=>Number.isFinite(b.volume))
    : !overlays[key].lines.some(([name])=>(ind[name] || []).slice(start,end).some(Number.isFinite)));
  const note=$('chart-overlay-note');
  note.hidden=missing.length===0;
  if(missing.length) note.textContent='표시 구간에 계산값 없음 · '+missing.map(key=>overlays[key].label).join(', ');
  for(const order of current.backtest?.orders||[]){if(order.execution_index<start||order.execution_index>=end)continue;const i=order.execution_index;ctx.fillStyle=order.side==='buy'?'#a6e0cc':'#f3ac91';ctx.font='700 10px '+fontFamily;ctx.fillText(order.side==='buy'?'B':'S',x(i)-3,order.side==='buy'?y(current.candles[i].low)+14:y(current.candles[i].high)-8);}
  ctx.font='500 11px '+fontFamily;ctx.fillStyle='#928d80';ctx.fillText(bars[0].timestamp.slice(0,10),12,h-4);ctx.fillText(bars[bars.length-1].timestamp.slice(0,10),Math.max(90,plotW-68),h-4);
  if(hover>=start&&hover<end){ctx.strokeStyle='#f1e4cf66';ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x(hover),0);ctx.lineTo(x(hover),h-18);ctx.stroke();ctx.setLineDash([]);}drawOverlayReadout();drawIndicator();
 }
 function axisNumber(value,compact){
   if(compact && Math.abs(value)>=10000)return new Intl.NumberFormat('ko-KR',{notation:'compact',maximumFractionDigits:1}).format(value);
   if(Math.abs(value)>0 && Math.abs(value)<0.01)return value.toPrecision(2);
   return fmt(value);
 }
 function drawIndicator(){
   const spec=oscillators[$('chart-subindicator').value], canvas=$('indicator-canvas');
   const {ctx,w,h}=surface('indicator-canvas',136), legend=$('chart-indicator-values');
   const note=$('chart-indicator-note'), period=$('chart-indicator-period');
   if(!current)return;
   const {start,end,k}=chartRange(), raw=current.indicators;
   const values=spec.lines.flatMap(([key])=>(raw[key] || []).slice(start,end)).filter(Number.isFinite);
   const focus=(hover>=start && hover<end)?hover:end-1;
   const time=current.candles[focus].timestamp;
   const dateLabel=current.timeframe && ['1d','1wk','1mo','D','W','M','1D','1W','1M'].includes(current.timeframe)?time.slice(0,10):time.replace('T',' ').replace(/([+-]\d\d:\d\d|Z)$/,' UTC');
   period.textContent=spec.label+' · '+spec.period(current.settings)+' · '+dateLabel;
   legend.replaceChildren();
   for(const [index,[key,label]] of spec.lines.entries()){
     const v=raw[key]?.[focus],chip=node('span','chart-ind-value series-'+index);
     chip.append(node('span','',label+' '),node('strong','',Number.isFinite(v)?axisNumber(v,false)+(spec.unit||''):'—'));
     legend.append(chip);
   }
   const noVolume=spec.volume && !current.candles.slice(start,end).some(b=>Number.isFinite(b.volume));
   const noValueAtBar=spec.lines.every(([key])=>!Number.isFinite(raw[key]?.[focus]));
   let message='';
   if(noVolume)message='이 구간에 거래량이 없어 지표를 계산할 수 없습니다.';
   else if(!values.length)message=spec.volume?'이 구간에 계산 가능한 값이 없습니다. 연속된 거래량과 준비 봉을 확인하세요.':'이 구간에 계산 가능한 값이 없습니다. 준비 봉과 가격 변동 범위를 확인하세요.';
   else if(noValueAtBar)message='선택한 봉의 지표를 계산할 수 없습니다.';
   note.textContent=message;note.hidden=!message;
   canvas.setAttribute('aria-label',spec.label+' · '+period.textContent+' · '+legend.textContent+(message?' · '+message:''));
   if(!values.length)return;
   let min,max;
   if(spec.bounds){[min,max]=spec.bounds;}
   else{
     min=Math.min(...values,...spec.guides);max=Math.max(...values,...spec.guides);
     const padding=(max-min || Math.abs(max)*.05 || 1)*.1;
     min-=padding;max+=padding;
     if($('chart-subindicator').value==='atr')min=Math.max(0,min);
   }
   const plotW=w-65, x=i=>12+(i-start+.5)*(plotW-15)/k, y=v=>12+(max-v)/(max-min)*(h-25);
   ctx.fillStyle='#b0a99b';ctx.textBaseline='middle';ctx.font='500 10px '+getComputedStyle(canvas).fontFamily;
   for(const edge of [min,max])ctx.fillText(axisNumber(edge,true),plotW+4,y(edge),59);
   for(const guide of spec.guides){
     ctx.strokeStyle='#625644';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(10,y(guide));ctx.lineTo(plotW,y(guide));ctx.stroke();
     if(Math.abs(y(guide)-y(min))>12 && Math.abs(y(guide)-y(max))>12)ctx.fillText(String(guide),plotW+4,y(guide));
   }
   ctx.setLineDash([]);
   if(spec.bars){
     const barWidth=Math.max(1,Math.min(12,(plotW-15)/k*.65));
     for(let i=start;i<end;i++){
       const v=raw[spec.bars]?.[i];
       if(!Number.isFinite(v))continue;
       ctx.fillStyle=v>=0?'#73b9a8':'#c68172';
       ctx.fillRect(x(i)-barWidth/2,Math.min(y(v),y(0)),barWidth,Math.max(1,Math.abs(y(v)-y(0))));
     }
   }
   for(const [i,[name]] of spec.lines.entries()){
     if(name!==spec.bars)plotLine(ctx,raw[name],start,end,x,y,seriesColors[i],1.6);
   }
   if(hover===focus){
     ctx.strokeStyle='#f1e4cf66';ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x(focus),5);ctx.lineTo(x(focus),h-5);ctx.stroke();ctx.setLineDash([]);
   }
 }
 function drawEquity(){const{ctx,w,h}=surface('equity-canvas',145);const points=current?.backtest?.equity||[];if(!points.length)return;const values=points.map(p=>p.equity),min=Math.min(current.settings.initial_capital,...values),max=Math.max(...values),range=max-min||1,x=i=>10+i/(points.length-1||1)*(w-95),y=v=>h-22-(v-min)/range*(h-37);plotLine(ctx,values,0,values.length,x,y,'#ff8d4d',2);ctx.fillStyle='#9f9685';ctx.fillText(fmt(max,0),w-77,15);ctx.fillText(fmt(min,0),w-77,h-24);ctx.fillText(points[0].timestamp.slice(0,10),10,h-3);ctx.fillText(points[points.length-1].timestamp.slice(0,10),w-156,h-3);const split=current.backtest.split_time,splitSeconds=typeof split==='number'?split:typeof split==='string'?Date.parse(split)/1000:NaN;if(Number.isFinite(splitSeconds)){const at=points.findIndex(p=>p.time>=splitSeconds);if(at>=0){ctx.strokeStyle='#ada28a88';ctx.setLineDash([3,4]);ctx.beginPath();ctx.moveTo(x(at),4);ctx.lineTo(x(at),h-16);ctx.stroke();ctx.setLineDash([]);}}}
 function metric(parent,label,value,accent){const box=node('div','chart-metric');box.append(node('span','',label),node('strong',accent||'',value));parent.append(box);}
 function assumptionsText(result){
  const s=result.settings,a=result.backtest?.assumptions,number=x=>Number.isFinite(x)?x.toLocaleString('ko-KR',{maximumFractionDigits:8}):'미확인';
  const rows=[['SMA 기간',`단기 ${s.fast_period}봉 · 장기 ${s.slow_period}봉`],['EMA 기간',`${s.ema_period}봉`],['RSI 기간',`${s.rsi_period}봉`],['볼린저 설정',`${s.bb_period}봉 · 표준편차 ${number(s.bb_std)}배`],['ATR 기간',`${s.atr_period}봉`]];
  if(a){rows.unshift(['계산 방식','앱에 저장된 가격 이력으로 수행한 가상 백테스트']);rows.push(['체결 시점',a.execution],['포지션 방향',a.direction==='long-only'?'매수 포지션만':'저장된 원본 설정 확인'],['투입 규모',a.position_size],['초기 자본',`${number(s.initial_capital)} · 시세와 같은 통화`],['레버리지',`${number(a.leverage)}배`],['추가 매수',a.pyramiding?'허용':'하지 않음'],['체결당 수수료',`${number(a.fee_bps_per_order/100)}%`],['슬리피지',a.slippage_mode==='ticks'?`${number(a.slippage_ticks)}틱 · 1틱 가격 ${number(a.tick_size)}`:`체결 가격의 ${number(a.slippage_bps/100)}% (${number(a.slippage_bps)}bp)`],['손익 평가',a.mark_to_market],['최대 낙폭 기준',a.drawdown],['통화·환율',a.capital_currency],['종료일 처리',a.end_date_exit],['앞·뒤 구간 검증',a.split],['설정 반복과 과최적화',a.parameter_selection]);}
  else rows.unshift(['계산 방식','지표·차트만 계산 · 전략 성과 계산 없음']);
  return rows.filter(([,value])=>value!==undefined&&value!==null&&value!=='').map(([label,value])=>`${label}: ${value}`).join('\n');
 }
 function render(result){current=result;hover=-1;$('chart-cursor').textContent='';$('chart-empty').hidden=true;$('chart-visible').max=result.candles.length;$('chart-visible').min=Math.min(30,result.candles.length);$('chart-visible').value=Math.min(150,result.candles.length);$('chart-position').value=100;$('chart-title').textContent=`${result.symbol} / ${result.timeframe}`;const p=result.provenance;$('chart-provenance').textContent=`${result.provider} · ${p.bars}봉 · ${p.first_time.slice(0,10)} — ${p.last_time.slice(0,10)} · ${p.currency} · 저장됨`;
  $('chart-tv-link').href='https://www.tradingview.com/chart/?symbol='+encodeURIComponent(result.symbol);$('chart-conclusion').hidden=false;$('chart-json').href=`/api/charts/${result.id}/export`;$('chart-pine').href=`/api/charts/${result.id}/pine`;$('chart-pine').hidden=!result.pine_script;
  $('chart-warnings').replaceChildren(...result.warnings.map(w=>node('li','',w)));$('chart-assumptions').textContent=assumptionsText(result);$('chart-latest').replaceChildren();const last=result.candles.at(-1),lastInd=result.evidence_summary.latest_indicators;metric($('chart-latest'),'마지막 종가',fmt(last.close));metric($('chart-latest'),`SMA ${result.settings.fast_period}`,fmt(lastInd.sma_fast));metric($('chart-latest'),'RSI',fmt(lastInd.rsi));metric($('chart-latest'),'ATR',fmt(lastInd.atr));
  const b=result.backtest;$('backtest-result').hidden=!b;
  if(b){$('chart-metrics').replaceChildren();const m=b.metrics;metric($('chart-metrics'),'총수익률 · 평가손익 포함',pct(m.total_return_pct),m.total_return_pct>=0?'positive':'negative');metric($('chart-metrics'),'최대 낙폭',pct(m.max_drawdown_pct),'negative');metric($('chart-metrics'),'완결 거래',String(m.closed_trades));metric($('chart-metrics'),'승률',Number.isFinite(m.win_rate_pct)?fmt(m.win_rate_pct)+'%':'완결 거래 없음');$('chart-validation').replaceChildren();metric($('chart-validation'),'뒤 구간 별도 검증',pct(b.out_of_sample?.metrics?.total_return_pct));metric($('chart-validation'),'비용 2배 가정',pct(b.cost_stress?.metrics?.total_return_pct));metric($('chart-validation'),'동일 구간 단순 보유',pct(m.buy_hold_return_pct));metric($('chart-validation'),'종료 시 포지션',b.open_position?'미청산 · 평가손익 포함':'보유 없음');$('chart-trades').replaceChildren();for(const t of b.trades){const tr=node('tr');for(const v of [t.entry_time.slice(0,10),t.exit_time.slice(0,10),fmt(t.entry_price),fmt(t.exit_price),pct(t.return_pct)])tr.append(node('td','',v));$('chart-trades').append(tr);}if(!b.trades.length){const tr=node('tr'),td=node('td','','이 구간에는 완결 거래가 없습니다.');td.colSpan=5;tr.append(td);$('chart-trades').append(tr);}}
  applySettings(result.settings);drawPrice();if(b)drawEquity();window.HyperpassBrain?.refresh();document.dispatchEvent(new CustomEvent('hyperpass:chart-result',{detail:result}));
 }
 function applySettings(selection){const s={...options(),...selection};appliedSettings={...s};for(const[id,key]of Object.entries({'chart-fast':'fast_period','chart-slow':'slow_period','chart-breakout':'breakout_period','chart-rsi-period':'rsi_period','chart-rsi-entry':'rsi_entry','chart-bb-period':'bb_period','chart-bb-std':'bb_std','chart-capital':'initial_capital','chart-start':'start_date','chart-end':'end_date'}))$(id).value=s[key]??$(id).defaultValue??'';$('chart-strategy').value=s.strategy;$('chart-fee').value=s.fee_bps/100;$('chart-slip-mode').value=s.slippage_mode;$('chart-slip').value=s.slippage_mode==='ticks'?s.slippage_ticks:s.slippage_bps;$('chart-tick').value=s.tick_size??'';$('chart-train').value=s.train_fraction*100;costMode();rule();}
 $('chart-form').addEventListener('submit',async event=>{event.preventDefault();if(busy)return;busy=true;$('chart-submit').disabled=true;feedback('실제 OHLCV를 조회하고 지표·전략을 계산합니다…');try{const source=$('chart-source').value;
   if(source==='csv'&&!$('chart-csv').value.trim())throw new Error('내보낸 CSV 파일을 선택하거나 내용을 붙여넣으세요.');
   if(source==='tradingview'&&!$('chart-symbol').value.trim())await desktopSymbol(true);
   let symbol;
   if(source==='csv'){
     const text=$('chart-symbol').value.trim();
     symbol=/^[A-Z0-9.^=_:!-]+$/i.test(text)?text.toUpperCase():(await window.HyperpassSymbols.field('chart-symbol','any')).id;
   }else{
     const item=await window.HyperpassSymbols.field('chart-symbol',source==='tradingview'?'tradingview':'yahoo');
     symbol=source==='tradingview'?item.id:item.yahoo;
   }
   const result=await window.HyperpassApp.api('/api/charts',{method:'POST',body:{source,symbol,period:$('chart-period').value,interval:$('chart-interval').value,port:Number($('chart-port').value),target_id:source==='tradingview'?$('chart-target').value:undefined,count:500,csv:$('chart-csv').value,options:{...options(),indicators:indicatorGroups}}});render(result);feedback('조회·계산·Second Brain 저장이 완료됐습니다. AI 해석을 이어갈 수 있습니다.');}catch(error){feedback(error.message,true);}finally{busy=false;$('chart-submit').disabled=false;}});
 $('chart-source').addEventListener('change',()=>{sourceRestoreNote='';updateSource();if($('chart-source').value==='tradingview')desktopSymbol(false).catch(()=>{});});$('chart-strategy').addEventListener('change',rule);$('chart-slip-mode').addEventListener('change',costMode);
 async function desktopSymbol(use){
   const port=Number($('chart-port').value);
   const display=$('chart-desktop-status');
   display.textContent='열린 Desktop 차트를 확인하고 있습니다…';
   try{
     const previous=$('chart-target').value;
     const data=await window.HyperpassApp.api('/api/tradingview/status?'+new URLSearchParams(previous?{port,target_id:previous}:{port}));
     const targets=Array.isArray(data.targets)?data.targets:[],select=$('chart-target');
     select.replaceChildren(new Option('조회할 탭 선택',''),...targets.map(t=>new Option(t.title||'차트 탭',t.id)));
     select.value=targets.some(t=>t.id===previous)?previous:(data.connected?data.target_id:'')||'';
     $('chart-target-block').hidden=targets.length<2;
     if(!data.connected||!data.chart?.symbol)throw new Error(data.message||'Desktop을 연결 실행하고 차트를 연 뒤 다시 확인하세요.');
     const symbol=data.chart.symbol;
     display.textContent='연결됨 · '+symbol+' · '+(data.chart.timeframe||'주기 미확인');
     if(use){$('chart-symbol').value=symbol;$('chart-symbol').dispatchEvent(new Event('input'));}
     return symbol;
   }catch(error){display.textContent=error.message;throw error;}
 }
 $('chart-target').addEventListener('change',()=>desktopSymbol(true).catch(()=>{}));
 $('chart-port').addEventListener('change',()=>{$('chart-target').replaceChildren();desktopSymbol(false).catch(()=>{});});
 $('chart-use-desktop').addEventListener('click',()=>desktopSymbol(true).catch(()=>{}));
 $('chart-desktop-launch').addEventListener('click',async()=>{
   try{const status=await window.HyperpassApp.api('/api/tradingview/launch',{method:'POST',body:{port:Number($('chart-port').value)}});
     $('chart-desktop-status').textContent=status.message||'Desktop 실행 후 열린 종목 가져오기를 누르세요.';
   }catch(error){$('chart-desktop-status').textContent=error.message;}
 });
 $('chart-csv-file').addEventListener('change',async()=>{
   const file=$('chart-csv-file').files[0];if(!file)return;
   try{
     if(file.size>900000)throw new Error('CSV는 900KB 이하로 가져오세요.');
     const bytes=await file.arrayBuffer();
     let csv;
     try{csv=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{csv=new TextDecoder('euc-kr').decode(bytes);}
     $('chart-csv').value=csv;
     const match=/^([A-Z0-9]+)[_:]([A-Z0-9.^=!-]+),\s*(1D|1W|1M|D|W|M)(?=\.|\s|_|$)/i.exec(file.name);
     if(match){$('chart-symbol').value=match[1].toUpperCase()+':'+match[2].toUpperCase();$('chart-symbol').dispatchEvent(new Event('input'));$('chart-interval').value=({D:'1d',W:'1wk',M:'1mo'})[match[3].slice(-1).toUpperCase()];}
     feedback('CSV를 읽었습니다. '+(match?'파일 이름에서 가져온 종목과 주기를 확인하세요.':'파일의 실제 종목명 또는 티커와 주기를 지정하세요.'));
   }catch(error){$('chart-csv').value='';feedback(error.message,true);}
 });
 for(const input of document.querySelectorAll('[data-overlay]'))input.addEventListener('change',drawPrice);
 $('chart-overlay-readout').addEventListener('toggle',drawOverlayReadout);
 $('chart-subindicator').addEventListener('change',drawIndicator);for(const id of ['chart-visible','chart-position'])$(id).addEventListener('input',drawPrice);
 $('price-canvas').addEventListener('mousemove',event=>{if(!current)return;const {start,end,k}=chartRange(),box=$('price-canvas').getBoundingClientRect();hover=Math.max(start,Math.min(end-1,start+Math.floor((event.clientX-box.left-12)/(box.width-80)*k)));const b=current.candles[hover];$('chart-cursor').textContent=`${b.timestamp.slice(0,10)}  O ${fmt(b.open)}  H ${fmt(b.high)}  L ${fmt(b.low)}  C ${fmt(b.close)}  V ${fmt(b.volume,0)}`;drawPrice();});
 $('price-canvas').addEventListener('mouseleave',()=>{hover=-1;$('chart-cursor').textContent='';drawPrice();});$('chart-ask').addEventListener('click',()=>{if(current)window.HyperpassApp.useChart(current);});
 new ResizeObserver(()=>{if(!host.hidden){drawPrice();if(current?.backtest)drawEquity();}}).observe($('price-canvas'));
 const indexGroups={kr:[['^KS11','코스피'],['^KQ11','코스닥']],us:[['^IXIC','나스닥 종합'],['^GSPC','S&P 500'],['^DJI','다우존스 산업평균']]};
 let indexRequest=0,indexSeries=[];
 function drawMarket(){
   if(!indexSeries.length||host.hidden)return;
   const {ctx,w,h,fontFamily}=surface('market-index-curve',78);
   const values=indexSeries.map(p=>p.close),min=Math.min(...values),max=Math.max(...values),range=max-min||1;
   const x=i=>5+(w-10)*i/(values.length-1),y=v=>5+(max-v)*(h-26)/range;
   ctx.strokeStyle=getComputedStyle(host).getPropertyValue('--accent')||'#ff6b1a';ctx.lineWidth=2;ctx.beginPath();
   values.forEach((v,i)=>i?ctx.lineTo(x(i),y(v)):ctx.moveTo(x(i),y(v)));ctx.stroke();
   ctx.fillStyle='#b8af9d';ctx.font='11px '+fontFamily;ctx.textAlign='left';ctx.fillText(indexSeries[0].date,4,h-2);
   ctx.textAlign='right';ctx.fillText(indexSeries.at(-1).date,w-4,h-2);
 }
 async function loadMarket(){
   const version=++indexRequest, select=$('market-index'),symbol=select.value,info=$('market-index-info');
   indexSeries=[];$('market-index-curve').hidden=true;$('market-index-retry').hidden=true;info.textContent=select.selectedOptions[0].text+' 조회 중…';
   try{
     const data=await window.HyperpassApp.api('/api/market-index?symbol='+encodeURIComponent(symbol));
     if(version!==indexRequest)return;
     indexSeries=data.series;
     const last=indexSeries.at(-1), previous=indexSeries.at(-2), change=100*(last.close/previous.close-1);
     info.textContent=data.name+' · '+fmt(last.close)+' pt · 전 거래일 대비 '+pct(change)+' · 관측일 '+data.as_of+' · ';
     const link=new URL(data.source_url);
     const trust=['query1.finance.yahoo.com','query2.finance.yahoo.com','stock.naver.com','fred.stlouisfed.org'];
     if(link.protocol==='https:'&&trust.includes(link.hostname)){
       const a=node('a','text-button',data.provider+' ↗');a.href=link.href;a.target='_blank';a.rel='noopener noreferrer';info.append(a);
     }else info.append(document.createTextNode(data.provider));
     const label=data.cache_status==='stale_cache'?'마지막 저장값':data.cache_status==='fresh_cache'?'최근 저장값':'조회';
     const when=new Date(data.retrieved_at).toLocaleString('ko-KR');
     info.append(document.createTextNode(' · '+label+' '+when+(data.notice?' · '+data.notice:'')));
     $('market-index-retry').hidden=data.cache_status!=='stale_cache';
     $('market-index-curve').setAttribute('aria-label',data.name+' 최근 3개월 종가 추이');$('market-index-curve').hidden=false;drawMarket();
   }catch(error){if(version===indexRequest){info.textContent='지수 조회 실패 · '+error.message;$('market-index-retry').hidden=false;}}
 }
 for(const button of document.querySelectorAll('[data-index-region]'))button.addEventListener('click',()=>{
   for(const b of document.querySelectorAll('[data-index-region]'))b.setAttribute('aria-pressed',String(b===button));
   $('market-index').replaceChildren(...indexGroups[button.dataset.indexRegion].map(([value,label])=>new Option(label,value)));
   loadMarket();
 });
 $('market-index').addEventListener('change',loadMarket);$('market-index-retry').addEventListener('click',loadMarket);
 document.addEventListener('hyperpass:workspace-change',event=>{if(event.detail.name==='chart')loadMarket();});
 new ResizeObserver(drawMarket).observe($('market-index-curve'));
 window.HyperpassChart={lastResult:()=>current,settings:options,applySettings,
   openSymbol:async symbol=>{
     if(busy){feedback('현재 차트 조회가 끝난 뒤 다시 선택하세요.');return;}
     window.HyperpassApp.selectWorkspace('chart');$('chart-source').value='yahoo';sourceRestoreNote='';
     $('chart-symbol').value=symbol;$('chart-symbol').dispatchEvent(new Event('input'));
     if(!$('chart-period').value)$('chart-period').value='1y';if(!$('chart-interval').value)$('chart-interval').value='1d';
     updateSource();$('chart-form').requestSubmit();},
   open:async id=>{feedback('저장된 차트 기록을 여는 중…');try{const result=await window.HyperpassApp.api('/api/charts/'+encodeURIComponent(id)+'?view=chart');restoreSource(result);render(result);feedback('저장된 계산 결과와 분석 설정을 복원했습니다. 기록되지 않은 조회 값은 출처 안내에 표시했습니다. 새로 조회하면 별도 기록으로 저장됩니다.');}catch(error){feedback(error.message,true);}}};$('chart-fee').step='any';$('chart-train').step='any';updateSource();costMode();rule();
})();
