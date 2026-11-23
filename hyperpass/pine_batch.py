"""Run one verified TradingView Strategy Tester experiment per selected instrument."""
import re
import time

from . import tradingview_control as tv
from .market_prices import validate_universe
from .pine_identity import new_execution, title_span
from .tradingview_chart import _port


def validate(payload):
    if not isinstance(payload, dict) or payload.get('engine') != 'pine':
        raise ValueError('TradingView Pine 실행 방식을 선택하세요.')
    allowed = {'name','engine','market','mode','symbols','universe','code','timeframe','port','target_id','selection_snapshot'}
    if set(payload) - allowed:
        raise ValueError('Pine 실행 조건을 확인하세요. 매매 규칙·기간·수수료는 전략 코드와 TradingView 속성을 사용합니다.')
    market, mode = payload.get('market'), payload.get('mode')
    if market not in ('KR','US') or mode not in ('single','custom','market'):
        raise ValueError('Pine 전략을 검증할 시장과 범위를 선택하세요.')
    symbols = payload.get('symbols', [])
    if not isinstance(symbols,list) or len(symbols) > 300 or any(not isinstance(s,str) or not 1 <= len(s.strip()) <= 80 for s in symbols):
        raise ValueError('직접 입력할 종목은 최대 300개입니다.')
    if mode == 'single' and len(symbols) != 1 or mode == 'custom' and not symbols or mode == 'market' and symbols:
        raise ValueError('검증 범위에 맞게 종목을 입력하세요. 전체 시장은 거래소·업종 선택을 사용합니다.')
    tf = payload.get('timeframe', '1D')
    if tf not in ('1D','1W','1M','60','15','5'):
        raise ValueError('Pine 차트 주기를 선택하세요.')
    target = payload.get('target_id') or None
    if target is not None and (not isinstance(target,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,150}',target)):
        raise ValueError('TradingView Desktop의 열린 차트 창을 선택하세요.')
    code = tv._validate_code(payload.get('code'))
    span = title_span(code)
    if len(new_execution(code, span)[0].encode('utf-8')) > tv._MAX_CODE:
        raise ValueError('실행 식별용 표시 제목을 포함한 Pine 코드는 200KB 이하여야 합니다.')
    universe = validate_universe(market, payload.get('universe',{}))
    extra = {}
    if 'selection_snapshot' in payload:
        from .selection_snapshot import normalize_selection
        if mode == 'market' or any(universe.values()):
            raise ValueError('선정일 고정 묶음에는 저장한 종목 전체를 사용합니다.')
        extra['selection_snapshot'] = normalize_selection(payload['selection_snapshot'], market, symbols)
    return {**extra, 'engine':'pine', 'market':market, 'mode':mode, 'symbols':[s.strip() for s in symbols],
            'universe':universe, 'code':code,
            'timeframe':tf, 'port':_port(payload.get('port',9222)), 'target_id':target}


# Batch-only operations aren't available through the ordinary chart command registry.
# Every mutation compares a complete observed precondition on the same chart object.
_GUARD = r"""
  if (action === 'batch') {
    const m = editor();
    if (!m) return {error:'editor_unavailable'};
    const allIds = () => chart.getAllStudies().map(s=>s.id).sort();
    const state = () => ({symbol:chart.symbol(), timeframe:String(chart.resolution()),
      chart_type:chart.chartType?.() ?? null, ids:allIds(), source:m.e.getValue()});
    const before = state();
    if (p.operation === 'read') {
      return {...before, login_prompt:loginPrompt()};
    }
    const x = p.expected;
    if (!x || before.symbol!==x.symbol || before.timeframe!==x.timeframe ||
        before.chart_type!==x.chart_type || before.source!==x.source ||
        JSON.stringify(before.ids)!==JSON.stringify(x.ids)) return {error:'batch_changed'};
    if (p.operation === 'symbol') {chart.setSymbol(p.value,{}); return {requested:true};}
    if (p.operation === 'timeframe') {chart.setResolution(p.value,{}); return {requested:true};}
    const run = window.__hyperpassResearchRun;
    if (!run || !p.token || run.token!==p.token || run.kind!=='strategy' || run.source!==before.source)
      return {error:'batch_changed'};
    if (p.operation === 'retire') {
      const id=p.study_id;
      const current=strategies().filter(s=>s.id()===id);
      if (typeof id!=='string' || current.length!==1 || Object.hasOwn(run.refs,id) ||
          !before.ids.includes(id) || run.batchTitle!==p.execution_title ||
          !/^HP-[0-9a-f]{32}$/.test(run.batchTitle) || current[0].metaInfo()?.description!==run.batchTitle ||
          strategies().filter(s=>s.metaInfo()?.description===run.batchTitle).length!==1 ||
          typeof chart.removeEntity!=='function')
        return {error:'batch_changed'};
      await chart.removeEntity(id);
      return {requested:true};
    }
    if (p.operation === 'restore_text') {
      if(typeof p.original!=='string')return {error:'batch_changed'};
      m.e.setValue(p.original);
      return {confirmed:m.e.getValue()===p.original};
    }
    return {error:'batch_changed'};
  }
"""


class _BatchSession(tv._Session):
    actions = frozenset({'batch', 'open_editor', 'editor'})
    program = tv._PROGRAM.replace("  if(action==='status')", _GUARD + "\n  if(action==='status')", 1)


class Changed(ValueError):
    pass


class Unavailable(ValueError):
    pass


class Desktop:
    def __init__(self, request, backup):
        self.request, self.backup = request, backup
        self.expected = self.original = self.token = None
        self.target = self.channel = None
        self.locked = self.text_changed = self.login_prompt = False

    def start(self):
        port = self.request['port']
        self.target, _ = tv._select(port,self.request['target_id'])
        if not tv._MUTATION_LOCK.acquire(blocking=False):
            raise ValueError('다른 TradingView 작업이 진행 중입니다. 완료 후 다시 실행하세요.')
        self.locked = True
        self.channel = _BatchSession(self.target,port)
        self.channel.__enter__()
        tv._check(self.channel.call('open_editor'))
        previous = stable_since = None
        opening = time.monotonic()
        for _ in range(32):
            editor = tv._check(self.channel.call('editor'))
            stable = (editor.get('uri'),editor.get('source'))
            if editor.get('ready') and isinstance(stable[1],str):
                if previous != stable:
                    previous, stable_since = stable, time.monotonic()
                elif time.monotonic()-stable_since >= .75 and (stable[1] or time.monotonic()-opening >= 2):
                    break
            else:
                previous = None
            time.sleep(.25)
        else:
            raise ValueError('Pine 편집기가 준비되지 않았습니다.')
        self.original = self.read()
        if self.original['source'] != stable[1] or len(stable[1].encode()) > 200000:
            raise Changed('편집기 원문을 확인하지 못해 중단했습니다.')
        self.expected = self.original
        if self.login_prompt:
            raise ValueError('TradingView에서 로그인을 요청했습니다. 본인 계정으로 로그인한 Desktop 차트를 선택하세요.')
        self.backup(self.original['source'],self.original['symbol'],self.original['timeframe'],self.target['id'])

    def read(self):
        state = tv._check(self.channel.call('batch', {'operation':'read'}))
        self.login_prompt = bool(state.pop('login_prompt',False))
        if not all(k in state for k in ('source','ids','symbol','timeframe','chart_type')):
            raise Changed('Desktop의 차트·편집기 상태를 확인할 수 없습니다.')
        return state

    def compare(self):
        current = self.read()
        if current != self.expected:
            raise Changed('실행 도중 차트·지표·편집기 상태가 변경됐습니다. 현재 상태와 저장된 실행 기록을 확인하세요.')

    def mutate(self, op, **params):
        result = self.channel.call('batch', {'operation':op,'expected':self.expected,'token':self.token,**params})
        if result.get('error'):
            raise Changed('선택한 창의 상태나 임시 전략의 소유권을 확인할 수 없어 변경을 중단했습니다.')
        return result

    def move(self, key, value):
        equal = tv._same_chart_symbol if key == 'symbol' else tv._same_timeframe
        if equal(self.expected[key], value):
            self.compare()
            return
        self.mutate(key, value=value)
        stable_value, stable_since = None, None
        for _ in range(40):
            current = self.read()
            if any(current[k] != self.expected[k] for k in self.expected if k!=key):
                raise Changed('차트가 변경되는 동안 편집기나 다른 차트 설정이 바뀌어 중단했습니다.')
            if equal(current[key],value):
                if stable_value != current[key]:
                    stable_value, stable_since = current[key], time.monotonic()
                elif time.monotonic()-stable_since >= .75:
                    self.expected = current
                    return
                time.sleep(.25)
                continue
            if current[key] != self.expected[key]:
                raise Changed('다른 종목 또는 주기가 선택되어 실행을 중단했습니다.')
            time.sleep(.25)
        raise Unavailable('TradingView에서 요청한 종목·주기를 확인하지 못했습니다.')

    def execute(self, symbol, source, execution):
        self.move('symbol',symbol)
        self.move('timeframe',self.request['timeframe'])
        self.compare()
        token = execution['title'][3:]
        def progress(*event):
            if len(event)==1 and event[0].get('stage')=='backup':
                if event[0]['previous_source'] != self.expected['source']:
                    raise Changed('새 Pine 문서를 열기 전에 편집기 원문이 변경되어 중단했습니다.')
        result = tv._run_pine(self.request['port'], source,self.target['id'],75,progress,
                              expected_chart=self.expected, batch_token=token)
        current = self.read()
        if (not tv._same_chart_symbol(current['symbol'],symbol) or
                not tv._same_timeframe(current['timeframe'],self.expected['timeframe']) or
                current['chart_type'] != self.expected['chart_type']):
            raise Changed(f'요청한 {symbol} {self.request["timeframe"]}과 실제 {current["symbol"]} {current["timeframe"]}의 차트 설정이 달라 중단했습니다.')
        if (result['status'] != 'completed' and current['source'] == self.expected['source'] and
                current['ids'] == self.expected['ids']):
            self.expected = current
            if 'compile_action' in result and current['source'] == source:
                self.token, self.text_changed = token, True
            if self.login_prompt and result['status'] != 'login_required':
                result['status'] = 'login_required'
                result.setdefault('warnings',[]).append('TradingView 로그인 후 Desktop 차트에서 실행하세요.')
            result.pop('previous_source',None)
            return result
        if current['source'] != source:
            raise Changed('전략 실행 중 편집기 원문이 변경되어 중단했습니다.')
        new_ids = set(current['ids']) - set(self.expected['ids'])
        if not set(self.expected['ids']).issubset(current['ids']):
            raise Changed('기존 차트 지표 목록이 변경되어 실행을 중단했습니다.')
        owner = result.get('study_id')
        report = result.get('report') or {}
        if new_ids and (new_ids != {owner} or report.get('study_id') != owner or result['status'] != 'completed'):
            raise Changed('새 전략을 이번 실행의 단일 항목으로 확인할 수 없습니다. Desktop에서 확인하세요.')
        if result['status'] == 'completed' and (not new_ids or report.get('available') is not True or
                                                 report.get('strategy') != execution['title']):
            raise Changed('이번 종목에서 생성한 새 전략 보고서를 확인할 수 없습니다.')
        self.text_changed = True
        self.token, self.expected = token, current
        if new_ids:
            try:
                self.mutate('retire', study_id=owner, execution_title=execution['title'])
                wanted = dict(current, ids=sorted(set(current['ids']) - {owner}))
                for _ in range(12):
                    current = self.read()
                    if current == wanted:
                        self.expected = current
                        break
                    if current != self.expected:
                        raise Changed('임시 전략 정리 중 차트가 변경됐습니다.')
                    time.sleep(.25)
                else:
                    raise Changed('이번 실행의 임시 전략이 정리됐는지 확인하지 못했습니다.')
            except (ValueError,OSError) as exc:
                result['cleanup_error'] = str(exc)
        result.pop('previous_source',None)
        return result

    def close(self):
        try:
            if self.original is None or self.expected is None:
                return {'status':'not_started','message':'차트 변경을 시작하지 않았습니다.'}
            self.compare()
            if self.expected['ids'] != self.original['ids']:
                raise Changed('원래 차트와 다른 지표가 남아 있어 자동 복원을 중단했습니다.')
            self.move('symbol', self.original['symbol'])
            self.move('timeframe', self.original['timeframe'])
            if self.text_changed and self.expected['source'] != self.original['source']:
                done = self.mutate('restore_text', original=self.original['source'])
                if not done.get('confirmed'):
                    raise Changed('원래 편집기 텍스트 복원을 확인하지 못했습니다.')
                self.expected = dict(self.expected,source=self.original['source'])
            self.compare()
            return {'status':'restored','message':'원래 종목·주기·지표 목록과 편집기 원문을 확인했습니다. 편집기 원문은 새 임시 문서에 복원했습니다.'}
        except (ValueError,OSError) as exc:
            return {'status':'unconfirmed','message':str(exc)}
        finally:
            try:
                if self.channel and getattr(self.channel,'ws',None):
                    self.channel.__exit__(None,None,None)
            finally:
                if self.locked:
                    tv._MUTATION_LOCK.release()


def run(request, stop, checkpoint, store_row, backup):
    """Checkpoint symbol reports individually; interruption never converts them to portfolio P&L."""
    from .market_prices import pine_universe
    result = {'engine':'pine','basis':'independent_per_symbol','requested':0,'completed':0,'failed':0,
              'skipped':0,'restore':{'status':'not_started','message':'차트 작업 시작 전'}}
    desk = None
    reason = None
    visited = 0
    try:
        checkpoint(0,'검증 대상 종목·거래소를 확인하고 있습니다.',result)
        span = title_span(request['code'])
        snapshot = request.get('selection_snapshot')
        if snapshot:
            members = {m['id']:{'name':m['name'], 'target_symbol':m['id']} for m in snapshot['members']}
            source = '스크리너 선정일 고정 목록 · ' + snapshot['selected_at']
            result['selection_snapshot'] = snapshot
        else:
            members, source = pine_universe(request['mode'],request['market'],request['symbols'],request['universe'])
        if not members:
            raise ValueError('조건에 해당하는 Pine 검증 대상이 없습니다.')
        result.update(requested=len(members), universe_source=source)
        if any(member.get('target_symbol') for member in members.values()) and not stop.is_set():
            desk = Desktop(request,backup)
            desk.start()
        for index,(symbol,member) in enumerate(members.items()):
            if stop.is_set():
                break
            target = member.get('target_symbol')
            row = {'symbol':symbol,'name':member['name'],'target_symbol':target,'report_index':index,
                   'status':'skipped','metrics':{},'currency':None,'error':None}
            raw = None
            halt = False
            if target:
                checkpoint(int(100*index/len(members)),f'{index+1:,}/{len(members):,} · {target} 전략 검증 중',result)
                code,execution = new_execution(request['code'], span)
                row['execution_title'] = execution['title']
                try:
                    raw = desk.execute(target,code,execution)
                    rep = raw.get('report') or {}
                    if raw['status'] == 'completed':
                        row.update(status='completed',metrics=rep['metrics'],currency=rep.get('currency'))
                    else:
                        message = ' · '.join(raw.get('warnings') or []) or '이번 실행의 전략 보고서를 확인하지 못했습니다.'
                        row.update(status='failed',error=message)
                        halt = raw['status'] in ('compile_error','login_required')
                    if raw.get('cleanup_error'):
                        reason, halt = raw['cleanup_error'], True
                except Unavailable as exc:
                    row.update(status='failed',error=str(exc))
                except (ValueError,OSError) as exc:
                    row.update(status='failed',error=str(exc))
                    reason, halt = str(exc), True
                raw = raw or {'status':'unverified', 'report':None, 'warnings':[row['error']]}
                raw['execution'] = execution
            else:
                row['error'] = '원본 상장의 TradingView 거래소 식별자를 확인할 수 없습니다.'
            store_row(index,row,raw)
            visited += 1
            result[row['status']] += 1
            checkpoint(min(99,int(100*visited/len(members))),f'{visited:,}/{len(members):,}종목 처리 · 보고서 {result["completed"]:,}개',result)
            if halt:
                reason = reason or row['error']
                break
    except (ValueError,OSError) as exc:
        reason = str(exc)
    finally:
        if desk:
            result['restore'] = desk.close()
    result['not_attempted'] = result['requested'] - visited
    result['skipped'] += result['not_attempted']
    if stop.is_set():
        status, reason = 'cancelled','사용자가 중단했습니다. 완료된 종목 보고서는 기록에 보관했습니다.'
    elif not result['requested'] or not result['completed']:
        status = 'failed'
        reason = reason or '새 전략 보고서를 확인한 종목이 없습니다.'
    elif result['failed'] or result['skipped'] or result['restore']['status'] == 'unconfirmed':
        status = 'partial'
        reason = reason or '종목별 실행 상태와 Desktop 복원 결과를 확인하세요.'
    else:
        status = 'completed'
    return status, result, reason
