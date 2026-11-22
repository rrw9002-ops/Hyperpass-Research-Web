"""Bounded, loopback-only controls for TradingView chart/Pine research.

No broker, orders, alerts, webhook or arbitrary JavaScript interface is exposed.
Compatibility paths adapted from tradesdontlie/tradingview-mcp, MIT (c) 2026;
see docs/TRADINGVIEW-THIRD-PARTY-LICENSE.txt. TradingView internals can change.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .tradingview_chart import same_chart_symbol as _same_chart_symbol
from .tradingview_chart import _port, _targets, _valid_ws, _WebSocket, TradingViewChartError
from .pine_indicator import indicator_title


class ChartControlError(ValueError):
    pass


_MUTATION_LOCK = threading.Lock()
_ACTIONS = frozenset({"status", "configure", "add_study", "set_inputs", "open_editor",
                      "editor", "new_script", "set_source", "compile", "open_tester", "reports", "run_state"})
_MAX_CODE = 200_000

# The only page program. Callers choose a fixed action; all parameters, including
# student Pine source, are JSON data. No user-provided expression is evaluated.
_PROGRAM = r"""async function(action, p) {
  const chart = window.TradingViewApi?._activeChartWidgetWV?.value();
  if (!chart) return {error:'chart_unavailable'};
  function sources() { try { return chart._chartWidget.model().model().dataSources(); } catch (_) { return []; } }
  function strategies() { return sources().filter(s => { try { const m=s.metaInfo?.(); return m && (m.isTVScriptStrategy || m.is_strategy) && typeof s.reportData==='function'; } catch (_) {return false;} }); }
  function unwrap(v) { return v && typeof v.value==='function' ? v.value() : v; }
  function reportOf(s) { try { return unwrap(s.reportData()); } catch (_) { return null; } }
  function safe(v, max=30000) { try { const text=JSON.stringify(v); return text && text.length<=max ? JSON.parse(text) : null; } catch (_) {return null;} }
  function editor() {
    let el=document.querySelector('.monaco-editor.pine-editor-monaco');
    let key; for(let i=0;el && i<20;i++,el=el.parentElement) { key=Object.keys(el).find(k=>k.startsWith('__reactFiber$')); if(key) break; }
    let f=el?.[key]; for(let i=0;f && i<20;i++,f=f.return) {
      const env=f.memoizedProps?.value?.monacoEnv;
      if(env?.editor?.getEditors) { const editors=env.editor.getEditors(); const e=editors.find(e=>el?.contains(e.getDomNode?.())) || editors.find(e=>e.getDomNode?.()?.classList?.contains('pine-editor-monaco')) || (editors.length===1?editors[0]:null); if(e) return {e,env}; }
    } return null;
  }
  function errors(m) { try { return m.env.editor.getModelMarkers({resource:m.e.getModel().uri}).map(x=>({line:x.startLineNumber,column:x.startColumn,message:String(x.message).slice(0,3000),severity:x.severity})).slice(0,60); } catch (_) {return [];} }
  function state() {
    let info={}; try {info=chart._chartWidget.model().mainSeries().symbolInfo() || {};} catch (_) {}
    const ss=sources();
    const studies=chart.getAllStudies().slice(0,100).map(x=>{
      const s=chart.getStudyById(x.id); let inputs=[], meta=[]; try {inputs=s.getInputValues().filter(x=>typeof x.value!=='string' || x.value.length<1000);} catch (_) {}
      try {meta=ss.find(s=>s.id?.()===x.id)?.metaInfo()?.inputs || [];} catch (_) {}
      return {id:x.id,name:x.name || x.title || 'unknown',inputs:inputs.filter(x=>!/^pine|^__/.test(x.id)).slice(0,80).map(x=>({id:x.id,value:x.value,name:meta.find(m=>m.id===x.id)?.name || x.id})),visible:s.isVisible?.()};
    });
    return {symbol:chart.symbol(),timeframe:String(chart.resolution()),chart_type:chart.chartType?.(),currency:info.currency_code || info.currency || null,studies};
  }
  function reports() {
    return strategies().map(s=>{
      const rd=reportOf(s), mi=s.metaInfo(), id=s.id(); let runtime=null;
      try {runtime=safe(s.status());} catch (_) {}
      if(!rd?.performance) return {study_id:id,strategy:mi.description || mi.shortDescription,available:false,runtime_status:runtime};
      const perf=rd.performance, a=perf.all || {};
      const metrics={net_profit:a.netProfit,net_profit_percent:a.netProfitPercent,gross_profit:a.grossProfit,gross_loss:a.grossLoss,
        profit_factor:a.profitFactor,max_drawdown:perf.maxStrategyDrawDown,max_drawdown_percent:perf.maxStrategyDrawDownPercent,
        total_trades:a.totalTrades,winning_trades:a.numberOfWiningTrades,losing_trades:a.numberOfLosingTrades,
        percent_profitable:a.percentProfitable,avg_trade:a.avgTrade,commission_paid:a.commissionPaid,
        sharpe_ratio:perf.sharpeRatio,sortino_ratio:perf.sortinoRatio,buy_hold_return:perf.buyHoldReturn,
        buy_hold_return_percent:perf.buyHoldReturnPercent,open_pl:perf.openPL};
      // TradingView's internal *Percent and percentProfitable are fractions,
      // e.g. 0.4146 is 41.46%, unlike the user-facing percentage-point fields.
      for(const key of ['net_profit_percent','max_drawdown_percent','buy_hold_return_percent','percent_profitable']) {
        if(typeof metrics[key]==='number') metrics[key] *= 100;
      }
      let orders=[]; try {orders=unwrap(s.ordersData()) || [];} catch (_) {}
      const equity=Array.isArray(rd.equity)?rd.equity:Array.isArray(rd.equityChart)?rd.equityChart:[];
      return {study_id:id,strategy:mi.description || mi.shortDescription,available:true,currency:rd.currency || null,
        metrics,metric_units:'percentage_points',performance:safe(perf),settings:safe(rd.settings),runtime_status:runtime,
        trades:Array.isArray(rd.trades)?safe(rd.trades.slice(-500),500000):[],total_report_trades:Array.isArray(rd.trades)?rd.trades.length:null,
        orders:Array.isArray(orders)?orders.slice(-500).map(o=>({id:o.id,type:o.tp,side:o.b?'buy':'sell',entry:o.e,price:o.p,qty:o.q,time_index:o.tm})):[],
        total_orders:Array.isArray(orders)?orders.length:null,equity:safe(equity.slice(-5000),400000) || [],
        notes:[...(equity.length?[]:['TradingView가 봉별 자산곡선을 제공하지 않아 빈 배열로 보존했습니다.']),...(rd.trades?.length>500 || orders?.length>500?['거래/체결 목록은 최근 500개까지 보존하며 요약 지표는 전체 계산 결과입니다.']:[])],source:'tradingview_strategy_tester'};
    });
  }
  if(action==='status') return {chart:state(),capabilities:{chart:typeof chart.setSymbol==='function',indicators:typeof chart.createStudy==='function',pine_editor:!!editor(),strategy_reports:strategies().length>0},editor_open:!!editor()};
  if(action==='configure') { if(p.symbol) chart.setSymbol(p.symbol,{}); if(p.timeframe) chart.setResolution(p.timeframe,{}); return {requested:true}; }
  if(action==='add_study') { const before=chart.getAllStudies().map(x=>x.id); const id=await chart.createStudy(p.name,false,false,[]); return {entity_id:typeof id==='string'?id:null,before}; }
  if(action==='set_inputs') {
    const s=chart.getStudyById(p.entity_id); if(!s) return {error:'study_missing'};
    const meta=sources().find(x=>x.id?.()===p.entity_id)?.metaInfo?.();
    if(meta?.isTVScriptStrategy || meta?.is_strategy) return {error:'strategy_inputs_not_supported'};
    const values=s.getInputValues(); const unknown=[]; const resolved={};
    for(const [key,v] of Object.entries(p.inputs)) {
      let id=key;
      if(key==='length' && !values.some(x=>x.id===id)) {
        const src=sources().find(x=>x.id?.()===p.entity_id); const meta=src?.metaInfo?.()?.inputs || [];
        const length=meta.filter(x=>/^(length|period|기간)$/i.test(x.name || ''));
        if(length.length===1) id=length[0].id;
        else if(['Moving Average','Moving Average Exponential','Relative Strength Index','Bollinger Bands','Average True Range'].includes(p.name) && values.some(x=>x.id==='in_0')) id='in_0';
      }
      if(!values.some(x=>x.id===id)) unknown.push(key); else resolved[id]=v;
    }
    if(unknown.length) return {error:'unknown_inputs',unknown,available_inputs:values.map(x=>x.id)};
    for(const row of values) if(Object.prototype.hasOwnProperty.call(resolved,row.id)) row.value=resolved[row.id];
    s.setInputValues(values); const after=s.getInputValues();
    const confirmed=Object.entries(resolved).every(([k,v])=>after.some(x=>x.id===k && x.value===v));
    return {confirmed,inputs:after.filter(x=>typeof x.value!=='string' || x.value.length<1000),resolved};
  }
  if(action==='open_editor') {
    if(editor()) return {ready:true};
    const b=window.TradingView?.bottomWidgetBar;
    if(typeof b?.activateScriptEditorTab==='function') b.activateScriptEditorTab();
    else if(typeof b?.showWidget==='function') b.showWidget('pine-editor');
    const button=document.querySelector('[aria-label="Pine"], [data-name="pine-dialog-button"]'); if(button) button.click();
    return {ready:!!editor()};
  }
  if(action==='editor') {
    const m=editor(), loading=document.querySelector('[data-name="pine-dialog"] [class*="loadingScreen"][data-hide="false"]');
    return m && !loading?{ready:true,source:m.e.getValue(),uri:String(m.e.getModel()?.uri),errors:errors(m)}:{ready:false};
  }
  if(action==='new_script') {
    const m=editor(); if(!m) return {error:'editor_unavailable'};
    if(typeof p.backed_up_source!=='string' || m.e.getValue()!==p.backed_up_source) return {error:'source_changed_before_new_script'};
    function saveDialog() {
      const dialog=document.querySelector('[data-name="warning-dialog"]');
      return dialog && /script|스크립트/i.test(dialog.textContent) && dialog.querySelector('[data-qa-id="dontSave-btn"]') && dialog.querySelector('[data-qa-id="cancel-btn"]') ? dialog : null;
    }
    // A previous attempt may have left the switching confirmation open. Cancel
    // that pending navigation, then start our own new-document operation.
    const pending=saveDialog();
    if(pending) {pending.querySelector('[data-qa-id="cancel-btn"]').click();await new Promise(r=>setTimeout(r,150));}
    const title=document.querySelector('[data-qa-id="pine-script-title-button"]');
    if(!title) return {error:'new_script_unavailable'};
    if(title.getAttribute('aria-expanded')!=='true') title.click();
    await new Promise(r=>setTimeout(r,100));
    const item=Array.from(document.querySelectorAll('[role="menuitem"]')).find(x=>/^(새로 만들기|Create new|New)$/i.test(x.textContent.trim()));
    if(!item) return {error:'new_script_unavailable'};
    item.focus(); item.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',code:'ArrowRight',keyCode:39,which:39,bubbles:true}));
    await new Promise(r=>setTimeout(r,200));
    const indicator = p.kind === 'indicator';
    const menuLabel = indicator ? /^(지표|인디케이터|Indicator)(Ctrl|⌘|\s|$)/i : /^(전략|Strategy)(Ctrl|⌘|\s|$)/i;
    const scriptType = Array.from(document.querySelectorAll('[role="menuitem"]')).find(x=>menuLabel.test(x.textContent.trim()));
    if(!scriptType || scriptType.getAttribute('aria-disabled')==='true') return {error:'new_script_unavailable'};
    scriptType.click();
    for(let i=0;i<30;i++) {
      await new Promise(r=>setTimeout(r,200));
      const confirmation=saveDialog();
      if(confirmation) {
        // The Python caller has persisted this exact source via its backup
        // callback BEFORE this action. Never discard a subsequently edited draft.
        if(editor()?.e.getValue()!==p.backed_up_source) return {error:'source_changed_before_new_script'};
        confirmation.querySelector('[data-qa-id="dontSave-btn"]').click();
        continue;
      }
      const fresh=editor(), add=document.querySelector('[data-qa-id="add-script-to-chart"]');
      const label=add?.textContent?.trim() || add?.getAttribute('title') || '';
      // TradingView reuses Monaco's model URI across documents. The new-document
      // menu plus an enabled Add (never Update) action is the observable boundary.
      const declaration = indicator ? /^\s*indicator\s*\(/m : /^\s*strategy\s*\(/m;
      if(fresh && declaration.test(fresh.e.getValue()) && add && !add.disabled && /^(Add to chart|차트에 추가|차트에 넣기)$/i.test(label)) return {created:true,uri:String(fresh.e.getModel()?.uri)};
    }
    return {created:false};
  }
  if(action==='set_source') {
    const m=editor(); if(!m) return {error:'editor_unavailable'};
    const previous=m.e.getValue(); if(previous.length>200000) return {error:'backup_too_large'};
    const refs={}; for(const s of strategies()) {const rd=reportOf(s);refs[s.id()]={ref:rd,signature:JSON.stringify(rd?.performance || null)};}
    const beforeStudies=p.kind==='indicator' ? chart.getAllStudies().map(s=>s.id) : [];
    window.__hyperpassResearchRun={token:p.token,refs,beforeStudies,kind:p.kind,source:p.code,started:Date.now()};
    m.e.setValue(p.code); m.e.focus();
    return {previous_source:previous,source_matches:m.e.getValue()===p.code,before_ids:Object.keys(refs)};
  }
  if(action==='compile') {
    const m=editor(); if(!m) return {error:'editor_unavailable'};
    const panel=document.querySelector('[data-name="pine-dialog"]') || document.querySelector('.pine-editor-container');
    const buttons=Array.from((panel || document).querySelectorAll('button')).filter(b=>b.offsetParent!==null && !b.disabled);
    // Never click Save/Publish or update a pre-existing strategy implicitly.
    const add=buttons.find(b=>/^(Add to chart|차트에 추가|차트에 넣기)$/i.test(b.textContent.trim() || b.getAttribute('title') || ''));
    if(add) {add.click();return {triggered:true,mode:'add',button:add.textContent.trim()};}
    return {triggered:false,error:'add_button_unavailable'};
  }
  if(action==='open_tester') {
    const b=window.TradingView?.bottomWidgetBar; if(typeof b?.showWidget==='function') b.showWidget('backtesting');
    return {requested:true};
  }
  if(action==='reports') return {chart:state(),reports:reports()};
  if(action==='run_state') {
    const run=window.__hyperpassResearchRun, m=editor(); if(!run || run.token!==p.token) return {error:'run_replaced'};
    if(run.kind==='indicator') {
      const chartState=state();
      const newIds=chartState.studies.map(s=>s.id).filter(id=>!run.beforeStudies.includes(id));
      const indicators=sources().flatMap(s=>{
        if(!newIds.includes(s.id?.())) return [];
        const meta=s.metaInfo?.();
        if(!meta?.isTVScript || meta.isTVScriptStrategy || meta.is_strategy) return [];
        return [{study_id:s.id(),title:meta.description,runtime_status:safe(s.status?.())}];
      });
      return {chart:chartState,new_ids:newIds,indicators,source_matches:!!m && m.e.getValue()===run.source,errors:m?errors(m):[]};
    }
    const changed=[]; for(const s of strategies()) {const rd=reportOf(s), old=run.refs[s.id()];if(!old || (rd && (rd!==old.ref || JSON.stringify(rd.performance || null)!==old.signature))) changed.push(s.id());}
    return {chart:state(),reports:reports(),changed_ids:changed,new_ids:strategies().map(s=>s.id()).filter(id=>!Object.prototype.hasOwnProperty.call(run.refs,id)),source_matches:!!m && m.e.getValue()===run.source,errors:m?errors(m):[]};
  }
  return {error:'unsupported_action'};
}"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _finite_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, list):
        return [_finite_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _finite_json(v) for k, v in value.items()}
    return value


def _valid_target(target, port):
    try:
        parsed = urlsplit(target.get("url", ""))
        if (target.get("type") != "page" or parsed.scheme not in ("http", "https")
                or parsed.username or parsed.password or parsed.port not in (None, 80, 443)
                or not (parsed.hostname == "tradingview.com" or (parsed.hostname or "").endswith(".tradingview.com"))
                or not re.match(r"^/chart(?:/|$)", parsed.path)):
            return False
        _valid_ws(target.get("webSocketDebuggerUrl", ""), port)
        return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,150}", target.get("id", "")))
    except (ValueError, TypeError):
        return False


def _select(port, target_id=None):
    _port(port)
    if target_id is not None and (not isinstance(target_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", target_id)):
        raise ChartControlError("TradingView 차트 탭 ID가 올바르지 않습니다.")
    try:
        targets = [t for t in _targets(port) if isinstance(t, dict) and _valid_target(t, port)]
    except (OSError, ValueError, TypeError):
        raise ChartControlError("TradingView Desktop 디버그 연결이 없습니다. 앱을 연결한 뒤 다시 시도하세요.") from None
    selected = [t for t in targets if target_id is None or t["id"] == target_id]
    if not selected:
        raise ChartControlError("연결된 TradingView 차트 탭이 없습니다. Desktop에서 차트를 열어 주세요.")
    if len(selected) != 1:
        raise ChartControlError("TradingView 차트가 여러 개 열려 있습니다. 사용할 차트 탭을 선택하세요.")
    return selected[0], targets


class _Session:
    def __init__(self, target, port):
        self.target, self.port, self.ws, self.counter = target, port, None, 0

    def __enter__(self):
        try:
            self.ws = _WebSocket(self.target["webSocketDebuggerUrl"], self.port)
        except (OSError, ValueError):
            raise ChartControlError("TradingView 차트에 연결하지 못했습니다.") from None
        return self

    def __exit__(self, *_):
        if self.ws:
            self.ws.close()

    def call(self, action, params=None):
        if action not in _ACTIONS:
            raise ChartControlError("지원하지 않는 차트 작업입니다.")
        self.counter += 1
        expression = "(" + _PROGRAM + ")(" + json.dumps(action) + "," + json.dumps(params or {}, ensure_ascii=True, allow_nan=False) + ")"
        self.ws.send(json.dumps({"id": self.counter, "method": "Runtime.evaluate", "params": {
            "expression": expression, "returnByValue": True, "awaitPromise": True, "timeout": 8000,
        }}).encode())
        deadline = time.monotonic() + 12
        try:
            for _ in range(32):
                if time.monotonic() > deadline:
                    break
                packet = self.ws.receive()
                if not isinstance(packet, dict) or packet.get("id") != self.counter:
                    continue
                result = packet.get("result", {})
                if packet.get("error") or result.get("exceptionDetails"):
                    raise ChartControlError("TradingView가 이 작업을 처리하지 못했습니다. 차트·편집기 상태를 확인하세요.")
                value = result.get("result", {}).get("value")
                if not isinstance(value, dict):
                    raise ChartControlError("TradingView 응답 형식을 확인할 수 없습니다.")
                return _finite_json(value)
        except (OSError, TradingViewChartError, json.JSONDecodeError):
            raise ChartControlError("TradingView 응답을 받지 못했습니다. 연결 상태를 확인하세요.") from None
        raise ChartControlError("TradingView 응답 시간이 초과되었습니다.")


def _check(value):
    if value.get("error"):
        messages = {"chart_unavailable": "현재 탭의 TradingView 차트가 아직 준비되지 않았습니다.",
                    "editor_unavailable": "Pine 편집기를 열지 못했습니다. TradingView 앱에서 Pine 편집기를 확인하세요.",
                    "new_script_unavailable": "새 Pine 문서를 만들지 못했습니다. TradingView 편집기의 새로 만들기 메뉴를 확인하세요.",
                    "source_changed_before_new_script": "백업 후 Pine 원문이 바뀌어 새 문서로 전환하지 않았습니다. 편집 내용을 확인하고 다시 실행하세요.",
                    "backup_too_large": "기존 Pine 코드가 백업 한도를 초과하여 편집하지 않았습니다.",
                    "run_replaced": "다른 실행이 현재 Pine 작업을 변경했습니다.",
                    "study_missing": "설정할 지표를 차트에서 찾지 못했습니다.",
                    "strategy_inputs_not_supported": "기존 전략의 설정은 지표 메뉴에서 바꾸지 않습니다. 새 Pine 전략 코드로 실행하세요.",
                    "unknown_inputs": "해당 지표에 없는 입력 항목입니다: " + ", ".join(map(str, value.get("unknown", [])))}
        raise ChartControlError(messages.get(value["error"], "TradingView에서 요청한 작업을 완료하지 못했습니다."))
    return value


def _target_meta(target):
    return {"id": target["id"], "title": str(target.get("title", "TradingView 차트"))[:160], "url": "https://www.tradingview.com/chart/"}


def status(port=9222, target_id=None):
    """Read-only capabilities and chart selection; never opens panels."""
    _port(port)
    try:
        target, targets = _select(port, target_id)
        with _Session(target, port) as session:
            value = _check(session.call("status"))
        return {"connected": True, "port": port, "target_id": target["id"], "targets": [_target_meta(t) for t in targets], **value}
    except ChartControlError as exc:
        # Multiple charts remain selectable even when none was selected.
        try:
            targets = [_target_meta(t) for t in _targets(port) if isinstance(t, dict) and _valid_target(t, port)]
        except (OSError, ValueError, TypeError):
            targets = []
        return {"connected": False, "port": port, "targets": targets, "message": str(exc), "capabilities": {}}


def _validate_config(symbol, timeframe, indicators):
    if symbol is not None:
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9.^=_:!\-]{1,80}", symbol):
            raise ChartControlError("거래소:종목 형식의 TradingView 심볼을 입력하세요.")
        symbol = symbol.upper()
    if timeframe is not None:
        if not isinstance(timeframe, str) or not re.fullmatch(r"(?:[1-9][0-9]{0,3}|(?:[1-9][0-9]?)?[SDWM])", timeframe.upper()):
            raise ChartControlError("차트 주기는 1, 5, 15, 60, 1D, 1W, 1M 형식으로 입력하세요.")
        timeframe = timeframe.upper()
    if indicators is None:
        indicators = []
    if not isinstance(indicators, list) or len(indicators) > 8:
        raise ChartControlError("지표는 한 번에 최대 8개까지 설정할 수 있습니다.")
    clean = []
    for item in indicators:
        if not isinstance(item, dict) or set(item) - {"name", "inputs", "entity_id"}:
            raise ChartControlError("지표 설정 형식이 올바르지 않습니다.")
        name, inputs, entity = item.get("name"), item.get("inputs", {}), item.get("entity_id")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or any(ord(c) < 32 for c in name):
            raise ChartControlError("TradingView에서 사용하는 지표 이름을 입력하세요.")
        if entity is not None and (not isinstance(entity, str) or not re.fullmatch(r"[A-Za-z0-9_$-]{1,100}", entity)):
            raise ChartControlError("지표 ID가 올바르지 않습니다.")
        if not isinstance(inputs, dict) or len(inputs) > 40:
            raise ChartControlError("지표 입력값은 최대 40개 항목의 객체여야 합니다.")
        for key, value in inputs.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,80}", key) or key in {"__proto__", "prototype", "constructor"} or key.startswith("pine"):
                raise ChartControlError("지표 입력 항목 이름이 올바르지 않습니다.")
            if not isinstance(value, (bool, int, float, str)) or (isinstance(value, str) and len(value) > 300) or (isinstance(value, (int, float)) and not math.isfinite(value)):
                raise ChartControlError("지표 입력값에는 유한한 숫자·문자·참/거짓만 사용할 수 있습니다.")
        clean.append({"name": name.strip(), "inputs": dict(inputs), "entity_id": entity})
    return symbol, timeframe, clean


def _same_timeframe(a, b):
    return re.sub(r"^1([SDWM])$", r"\1", str(a)) == re.sub(r"^1([SDWM])$", r"\1", str(b))


def configure_chart(port=9222, symbol=None, timeframe=None, indicators=None, target_id=None):
    """Change only requested chart fields/add studies. Never remove a study."""
    symbol, timeframe, indicators = _validate_config(symbol, timeframe, indicators)
    target, _ = _select(port, target_id)
    if not _MUTATION_LOCK.acquire(blocking=False):
        raise ChartControlError("다른 TradingView 작업이 진행 중입니다. 완료 후 다시 시도하세요.")
    changed, warnings = [], []
    try:
        with _Session(target, port) as session:
            before = _check(session.call("status"))["chart"]
            try:
                # Sequential symbol and interval readback avoids chart reload races.
                for key, value in (("symbol", symbol), ("timeframe", timeframe)):
                    if value is None:
                        continue
                    _check(session.call("configure", {key: value}))
                    for _ in range(24):
                        observed = _check(session.call("status"))["chart"].get(key)
                        if (_same_chart_symbol(observed, value) if key == "symbol" else _same_timeframe(observed, value)):
                            changed.append({"field": key, "value": observed})
                            break
                        time.sleep(.25)
                    else:
                        raise ChartControlError("요청한 종목 또는 주기를 차트에서 확인하지 못했습니다.")
                for indicator in indicators:
                    entity = indicator["entity_id"]
                    if not entity:
                        added = _check(session.call("add_study", {"name": indicator["name"]}))
                        for _ in range(20):
                            chart = _check(session.call("status"))["chart"]
                            found = [s["id"] for s in chart["studies"] if s["id"] not in added["before"]]
                            entity = added.get("entity_id") if added.get("entity_id") in found else found[0] if len(found) == 1 else None
                            if entity:
                                break
                            time.sleep(.25)
                        if not entity:
                            raise ChartControlError("지표 추가를 차트에서 확인하지 못했습니다. TradingView의 지표 개수 제한도 확인하세요.")
                        changed.append({"field": "indicator_added", "entity_id": entity, "name": indicator["name"]})
                    if indicator["inputs"]:
                        result = _check(session.call("set_inputs", {**indicator, "entity_id": entity}))
                        if not result.get("confirmed"):
                            raise ChartControlError("지표 입력값을 차트에서 확인하지 못했습니다.")
                        changed.append({"field": "indicator_inputs", "entity_id": entity, "inputs": result["resolved"]})
            except ChartControlError as exc:
                warnings.append(str(exc))
            current = _check(session.call("status"))["chart"]
            if ((symbol is not None and not _same_chart_symbol(current.get("symbol"),symbol)) or
                (timeframe is not None and not _same_timeframe(current.get("timeframe"),timeframe))):
                warnings.append("설정을 적용하는 동안 차트 종목 또는 주기가 바뀌었습니다. 차트에서 다시 확인하세요.")
        return {"status": "partial" if warnings else "configured", "target_id": target["id"], "before": before,
                "chart": current, "changed": changed, "warnings": warnings, "retrieved_at": _now()}
    finally:
        _MUTATION_LOCK.release()


def strategy_results(port=9222, target_id=None):
    """Read current real reports. Does not imply a newly submitted Pine run."""
    target, _ = _select(port, target_id)
    with _Session(target, port) as session:
        value = _check(session.call("reports"))
    available = [r for r in value.get("reports", []) if r.get("available")]
    return {"status": "completed" if available else "no_report", "target_id": target["id"], **value,
            "retrieved_at": _now(), "warnings": [] if available else ["계산된 전략 보고서가 없습니다. TradingView에서 전략 테스터를 열고 전략 상태를 확인하세요."],
            "verification": "current_chart_reports_only"}


def _validate_code(code):
    if not isinstance(code, str) or not code.strip() or len(code.encode("utf-8")) > _MAX_CODE or "\x00" in code:
        raise ChartControlError("Pine 전략 코드는 비어 있지 않은 200KB 이하 텍스트여야 합니다.")
    # Remove comments for declaration detection only. The original text is sent unchanged.
    uncommented = re.sub(r"(?m)^\s*//.*$", "", code)
    if not re.search(r"(?m)^\s*strategy\s*\(", uncommented):
        raise ChartControlError("전략 테스터에는 strategy()로 선언한 Pine 전략 코드를 입력하세요.")
    return code


def run_strategy(port=9222, code="", target_id=None, timeout=60, on_progress=None, expected_chart=None):
    return _run_pine(port, _validate_code(code), target_id, timeout, on_progress, expected_chart=expected_chart)


def run_indicator(port=9222, code="", target_id=None, timeout=60, on_progress=None, expected_chart=None):
    return _run_pine(port, code, target_id, timeout, on_progress, indicator_title(code), expected_chart)


def _run_pine(port, code, target_id, timeout, on_progress, title=None, expected_chart=None):
    """Add a fresh script, preserve the editor backup, and require chart-side readback."""
    kind = "indicator" if title is not None else "strategy"
    label = "지표" if title is not None else "전략"
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 5 <= timeout <= 120:
        raise ChartControlError("실행 대기 시간은 5–120초여야 합니다.")
    target, _ = _select(port, target_id)
    if not _MUTATION_LOCK.acquire(blocking=False):
        raise ChartControlError("다른 TradingView 작업이 진행 중입니다. 완료 후 다시 시도하세요.")
    result = {"status": "no_report", "target_id": target["id"], "compile_errors": [], "report": None,
              "previous_source": None, "study_id": None, "chart": None, "warnings": [],
              "source_sha256": hashlib.sha256(code.encode()).hexdigest(), "started_at": _now(),
              "verification": "new_study_report_required"}
    if title is not None:
        result.update(status="unverified_indicator", verification="new_indicator_title_id_runtime_required")

    def progress(stage, message):
        if on_progress:
            on_progress(stage, message)

    try:
        with _Session(target, port) as session:
            result["chart"] = _check(session.call("status"))["chart"]
            expected_symbol = result["chart"].get("symbol")
            expected_timeframe = result["chart"].get("timeframe")
            if expected_chart and (expected_symbol != expected_chart.get("symbol") or
                                   not _same_timeframe(expected_timeframe, expected_chart.get("timeframe"))):
                raise ChartControlError("차트 설정 확인 후 종목 또는 주기가 바뀌었습니다. 다시 요청하세요.")
            progress("opening_editor", "TradingView Pine 편집기를 준비하고 있습니다.")
            _check(session.call("open_editor"))
            editor_state, stable_state, stable_since = None, None, None
            editor_wait_started = time.monotonic()
            for _ in range(30):
                editor_state = _check(session.call("editor"))
                if editor_state.get("ready"):
                    observation = (editor_state.get("uri"), editor_state.get("source"))
                    if observation != stable_state:
                        stable_state, stable_since = observation, time.monotonic()
                    elif stable_since is not None and time.monotonic() - stable_since >= .75 and (editor_state.get("source") or time.monotonic() - editor_wait_started >= 2):
                        break
                time.sleep(.25)
            else:
                raise ChartControlError("Pine 편집기를 열지 못했습니다. TradingView에서 직접 편집기를 열어 주세요.")
            previous = editor_state.get("source")
            if not isinstance(previous, str) or len(previous.encode("utf-8")) > _MAX_CODE:
                raise ChartControlError("기존 Pine 코드를 안전하게 백업할 수 없어 편집하지 않았습니다.")
            result["previous_source"] = previous
            if on_progress:
                on_progress({"stage": "backup", "message": "기존 Pine 편집기 코드를 백업했습니다.", "previous_source": previous})
            progress("new_script", f"새 Pine {label} 문서를 만들고 있습니다.")
            fresh = _check(session.call("new_script", {"backed_up_source": previous, "kind": kind}))
            if not fresh.get("created"):
                raise ChartControlError(f"새 {label} 문서를 확인하지 못했습니다. TradingView 편집기를 확인하세요.")
            token = uuid.uuid4().hex
            changed = _check(session.call("set_source", {"code": code, "token": token, "kind": kind}))
            if not changed.get("source_matches"):
                raise ChartControlError("Pine 편집기의 입력 코드가 요청과 일치하지 않습니다.")
            progress("compiling", f"입력한 Pine {label}를 TradingView 차트에 추가하고 있습니다.")
            clicked = {}
            for _ in range(12):
                clicked = session.call("compile")
                if clicked.get("triggered"):
                    break
                time.sleep(.25)
            result["compile_action"] = clicked
            if not clicked.get("triggered"):
                result["warnings"].append("Pine 편집기에 코드와 원본 백업을 준비했습니다. 기존 전략을 보호하기 위해 업데이트/저장은 누르지 않았습니다. TradingView 편집기의 ‘차트에 추가’가 가능한 새 스크립트에서 다시 실행하세요.")
                return result
            if title is None:
                _check(session.call("open_tester"))
                progress("backtesting", "TradingView가 새 전략의 실제 백테스트 보고서를 계산하는지 확인하고 있습니다.")
            else:
                progress("verifying_indicator", "차트에서 새 지표의 이름과 계산 상태를 확인하고 있습니다.")
            deadline, error_since, last_errors = time.monotonic() + timeout, None, []
            while time.monotonic() < deadline:
                snapshot = _check(session.call("run_state", {"token": token}))
                result["chart"] = snapshot.get("chart")
                observed_chart = result["chart"] or {}
                if observed_chart.get("symbol") != expected_symbol or not _same_timeframe(observed_chart.get("timeframe"), expected_timeframe):
                    raise ChartControlError("실행 중 차트 종목 또는 주기가 바뀌어 결과를 이번 요청으로 확인할 수 없습니다.")
                if not snapshot.get("source_matches"):
                    raise ChartControlError("실행 중 Pine 코드가 변경되어 결과를 이번 요청으로 확인할 수 없습니다.")
                # An old report can update for unrelated reasons. Only a new
                # strategy ID created after this submission can complete this run.
                matches = [r for r in snapshot.get("reports", []) if r.get("available") and r.get("study_id") in snapshot.get("new_ids", []) and (r.get("runtime_status") or {}).get("type") != 3]
                current_errors = []
                for error in snapshot.get("errors", []):
                    if error.get("severity", 0) >= 8 and error not in current_errors:
                        current_errors.append(error)
                if title is not None:
                    new_ids = snapshot.get("new_ids", [])
                    if len(new_ids) > 1:
                        raise ChartControlError("동시에 여러 지표가 추가됐습니다. 차트에서 결과를 확인하세요.")
                    for study in snapshot.get("indicators", []):
                        if study.get("study_id") not in new_ids or study.get("title") != title:
                            continue
                        runtime = study.get("runtime_status") or {}
                        if runtime.get("type") == 3:
                            result.update(status="compile_error", compile_errors=current_errors or [runtime], indicator=study)
                            return result
                        if runtime.get("type") == 2 and not current_errors:
                            result.update(status="applied", indicator=study, study_id=study["study_id"], completed_at=_now())
                            progress("completed", "새 지표가 차트에서 계산되는 것을 확인했습니다.")
                            return result
                if len(matches) == 1 and not current_errors:
                    result.update(status="completed", report=matches[0], study_id=matches[0]["study_id"], completed_at=_now())
                    progress("completed", "TradingView의 새 전략 보고서를 확인했습니다.")
                    return result
                if len(matches) > 1:
                    raise ChartControlError("여러 새 전략이 동시에 생성되어 이번 코드의 결과를 특정할 수 없습니다.")
                if current_errors:
                    if current_errors != last_errors:
                        error_since = time.monotonic()
                    elif error_since is not None and time.monotonic() - error_since >= 1:
                        result.update(status="compile_error", compile_errors=current_errors)
                        result["warnings"].append(f"TradingView Pine 컴파일 오류입니다. {label} 코드를 확인하세요.")
                        return result
                else:
                    error_since = None
                last_errors = current_errors
                time.sleep(.5)
            result["compile_errors"] = last_errors
            result["warnings"].append("차트에서 새 지표의 이름과 계산 상태를 확인하지 못했습니다. 편집기 오류와 지표 한도를 확인하세요." if title is not None else "대기 시간 안에 이번 코드의 새 전략 보고서를 확인하지 못했습니다. 기존 보고서를 이번 결과로 저장하지 않았습니다. TradingView 편집기 오류·전략 개수 제한·전략 테스터 상태를 확인하세요.")
            return result
    except ChartControlError as exc:
        if result["previous_source"] is None:
            raise
        result["warnings"].append(str(exc))
        return result
    finally:
        _MUTATION_LOCK.release()
