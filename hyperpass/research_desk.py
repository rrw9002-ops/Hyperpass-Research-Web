"""Local strategy library, portfolio jobs, and the student's watchlist."""
import json
import math
import re
import threading
import time
import uuid
from datetime import datetime, timezone


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def pack(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def title(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 120:
        raise ValueError('전략 이름을 1~120자로 입력하세요.')
    return value.strip()


def report_symbols(run):
    """Offer named instruments from the question; the student confirms the listing."""
    from .symbol_search import ALIASES
    question = run.get('question', '').split('[질문 범주:')[0]
    hits = []
    for identity, name, aliases in ALIASES:
        ticker = identity.split(':', 1)[1]
        for word in (ticker, name, *aliases.split('|')):
            pattern = re.escape(word)
            if word.isascii():
                pattern = r'(?<![a-z0-9])' + pattern + r'(?![a-z0-9])'
            for match in re.finditer(pattern, question, re.I):
                hits.append((match.start(), match.end(), identity, name))
    # e.g. 삼성전자우선주 includes 삼성전자. Prefer the full match at that position.
    choices = {}
    previous = (-1, -1)
    for start, end, identity, name in sorted(hits, key=lambda hit:(hit[0], -hit[1])):
        if end <= previous[1] and (start,end) != previous:
            continue
        choices[identity] = name
        previous = (start,end)
    return [{'symbol':s,'name':n} for s,n in choices.items()]


class ResearchDesk:
    def __init__(self, store):
        self.store = store
        self.job_lock = threading.RLock()
        self.active = None
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS strategies(
                id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, definition TEXT NOT NULL,
                source TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS backtests(
                id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
                request TEXT NOT NULL, progress TEXT NOT NULL, result TEXT, error TEXT,
                created_at TEXT NOT NULL, finished_at TEXT)""")
            db.execute("""UPDATE backtests SET status='interrupted', error=?, finished_at=?
                WHERE status IN ('queued','running')""", ('앱 종료로 계산이 중단됐습니다. 기록의 설정으로 다시 실행하세요.', timestamp()))
            db.execute("""CREATE TABLE IF NOT EXISTS watchlist(
                symbol TEXT PRIMARY KEY, name TEXT NOT NULL, yahoo TEXT NOT NULL, run_id TEXT,
                chart_id TEXT, added_at TEXT NOT NULL, quote TEXT)""")

    def strategies(self):
        with self.store.connect() as db:
            rows = db.execute('SELECT id,name,kind,definition,source,updated_at FROM strategies ORDER BY updated_at DESC,id')
            return [dict(id=i,name=n,kind=k,definition=json.loads(d),source=s,updated_at=t) for i,n,k,d,s,t in rows]

    def save_strategy(self, payload):
        from .chart_lab import validate_settings
        from .market_backtest import validate_request
        name = title(payload.get('name'))
        kind, definition = payload.get('kind'), payload.get('definition')
        source = payload.get('source', '')
        if not isinstance(source, str) or len(source) > 1200 or not isinstance(definition, dict):
            raise ValueError('전략 출처와 설정을 확인하세요.')
        if kind == 'market':
            definition = validate_request(definition)
        elif kind == 'chart' and isinstance(definition.get('settings'), dict):
            if not definition['settings'].get('strategy') or definition['settings']['strategy'] == 'none':
                raise ValueError('저장할 차트 전략을 선택하세요.')
            interval = definition.get('interval')
            definition = {'settings': validate_settings(definition['settings'])}
            if interval is not None:
                if not isinstance(interval,str) or not re.fullmatch(r'[A-Za-z0-9]{1,24}',interval):
                    raise ValueError('차트의 봉 주기를 확인하세요.')
                definition['interval'] = interval
        elif kind == 'pine':
            code, timeframe = definition.get('code'), definition.get('timeframe', '')
            if not isinstance(code, str) or not code.strip() or len(code.encode()) > 200000 or not re.search(r'(?m)^\s*strategy\s*\(', code):
                raise ValueError('strategy()를 선언한 Pine 전략 원문을 입력하세요.')
            if not isinstance(timeframe, str) or len(timeframe) > 12:
                raise ValueError('Pine 전략 주기를 확인하세요.')
            definition = {'code': code, 'timeframe': timeframe}
        else:
            raise ValueError('저장할 전략 유형이나 설정을 확인하세요.')
        identity, updated = payload.get('id'), timestamp()
        with self.store.connect() as db:
            if identity is None or identity == '':
                identity = uuid.uuid4().hex
                db.execute('INSERT INTO strategies VALUES (?,?,?,?,?,?)',(identity,name,kind,pack(definition),source,updated))
            elif not isinstance(identity,str) or not db.execute(
                    'UPDATE strategies SET name=?,kind=?,definition=?,source=?,updated_at=? WHERE id=?',
                    (name,kind,pack(definition),source,updated,identity)).rowcount:
                raise ValueError('수정할 전략을 찾지 못했습니다.')
        return dict(id=identity,name=name,kind=kind,definition=definition,source=source,updated_at=updated)

    def list_jobs(self):
        with self.store.connect() as db:
            rows = db.execute('SELECT id,name,mode,status,progress,error,created_at,finished_at FROM backtests ORDER BY created_at DESC LIMIT 100')
            return [dict(id=i,name=n,mode=m,status=s,progress=json.loads(p),error=e,created_at=c,finished_at=f)
                    for i,n,m,s,p,e,c,f in rows]

    def job(self, identity):
        with self.store.connect() as db:
            row = db.execute('SELECT name,mode,status,request,progress,result,error,created_at,finished_at FROM backtests WHERE id=?',(identity,)).fetchone()
        if row:
            n,m,s,q,p,r,e,c,f = row
            return dict(id=identity,name=n,mode=m,status=s,request=json.loads(q),progress=json.loads(p),
                        result=json.loads(r) if r else None,error=e,created_at=c,finished_at=f)

    def start(self, payload):
        from .market_backtest import validate_request
        from .chart_lab import STRATEGIES
        request = validate_request({k:v for k,v in payload.items() if k != 'name'})
        name = title(payload.get('name') or STRATEGIES[request['settings']['strategy']])
        identity, stop = uuid.uuid4().hex, threading.Event()
        with self.job_lock:
            if self.active:
                raise ValueError('진행 중인 백테스트가 있습니다. 완료하거나 중단한 뒤 시작하세요.')
            with self.store.connect() as db:
                db.execute('INSERT INTO backtests VALUES (?,?,?,?,?,?,NULL,NULL,?,NULL)',
                           (identity,name,request['mode'],'queued',pack(request),pack(dict(percent=0,label='시작 준비')),timestamp()))
            self.active = identity, stop
            thread = threading.Thread(target=self._work, args=(identity,request,stop), daemon=True)
            thread.start()
        return self.job(identity)

    def _work(self, identity, request, stop):
        from .market_backtest import run_backtest, BacktestCancelled
        last = 0.0

        def progress(percent, label):
            nonlocal last
            if time.monotonic()-last < .35 and percent:
                return
            last = time.monotonic()
            with self.store.connect() as db:
                db.execute("UPDATE backtests SET status='running', progress=? WHERE id=?",
                           (pack(dict(percent=max(0,min(99,int(percent))), label=str(label)[:400])),identity))

        result, error = None, None
        try:
            progress(0, '종목 목록과 시세 확인 중')
            result = pack(run_backtest(request, progress, stop, cache_dir=self.store.path.parent/'price-cache'))
            status = 'completed'
        except BacktestCancelled:
            status, error = 'cancelled', '사용자가 백테스트를 중단했습니다.'
        except ValueError as exc:
            status, error = 'failed', str(exc)
        except Exception:
            status, error = 'failed', '계산을 마치지 못했습니다. 데이터 출처와 입력 조건을 확인하세요.'
        with self.job_lock, self.store.connect() as db:
            if stop.is_set():
                status, result, error = 'cancelled', None, '사용자가 백테스트를 중단했습니다.'
            db.execute('UPDATE backtests SET status=?,result=?,error=?,finished_at=? WHERE id=?',
                       (status,result,error,timestamp(),identity))
            if status == 'completed':
                db.execute('UPDATE backtests SET progress=? WHERE id=?',(pack(dict(percent=100,label='결과 저장 완료')),identity))
            self.active = None

    def cancel(self, identity):
        with self.job_lock:
            if not self.active or self.active[0] != identity:
                raise ValueError('진행 중인 백테스트를 선택하세요.')
            self.active[1].set()
        return {'cancelling':True}

    def watchlist(self):
        with self.store.connect() as db:
            rows = db.execute('SELECT symbol,name,yahoo,run_id,chart_id,added_at,quote FROM watchlist ORDER BY added_at DESC,symbol')
            return [dict(symbol=s,name=n,yahoo=y,run_id=r,chart_id=c,added_at=t,quote=json.loads(q) if q else None)
                    for s,n,y,r,c,t,q in rows]

    def follow(self, payload):
        from .symbol_search import resolve_symbol
        item = resolve_symbol(payload.get('symbol',''), 'any')
        symbol = item.get('id') or item['yahoo']
        run_id, chart_id = payload.get('run_id'), payload.get('chart_id')
        if run_id is not None and (not isinstance(run_id,str) or not self.store.get(run_id)):
            raise ValueError('연결할 분석 기록이 없습니다.')
        if chart_id is not None and (not isinstance(chart_id,str) or not self.store.get_chart(chart_id)):
            raise ValueError('연결할 차트 기록이 없습니다.')
        with self.store.connect() as db:
            db.execute("""INSERT INTO watchlist VALUES (?,?,?,?,?,?,NULL)
                          ON CONFLICT(symbol) DO UPDATE SET run_id=coalesce(excluded.run_id,watchlist.run_id),
                          chart_id=coalesce(excluded.chart_id,watchlist.chart_id),
                          yahoo=excluded.yahoo, name=excluded.name""",
                       (symbol,item['name'],item.get('yahoo') or '',run_id,chart_id,timestamp()))
        return {'symbol':symbol,'name':item['name']}

    def unfollow(self, symbol):
        if not isinstance(symbol,str):
            raise ValueError('관심종목을 선택하세요.')
        with self.store.connect() as db:
            db.execute('DELETE FROM watchlist WHERE symbol=?',(symbol,))
        return {'removed':True}

    def quote(self, symbol, sources):
        if not isinstance(symbol,str):
            raise ValueError('관심종목을 선택하세요.')
        with self.store.connect() as db:
            row = db.execute('SELECT yahoo FROM watchlist WHERE symbol=?',(symbol,)).fetchone()
        if not row or not row[0]:
            raise ValueError('이 관심종목은 Yahoo 시세를 조회할 수 없습니다.')
        packet = sources.chart_history(row[0], '3mo', '1d')
        rows = [r for r in packet['records'] if type(r.get('close')) in (int,float) and math.isfinite(r['close']) and r['close']>0]
        if not rows:
            raise ValueError('종가 관측값이 없습니다.')
        close = rows[-1]['close']
        quote = dict(price=close,change_pct=100*(close/rows[-2]['close']-1) if len(rows)>1 else None,
                     as_of=rows[-1]['timestamp'],currency=packet.get('currency'),retrieved_at=timestamp())
        with self.store.connect() as db:
            db.execute('UPDATE watchlist SET quote=? WHERE symbol=?',(pack(quote),symbol))
        return quote
