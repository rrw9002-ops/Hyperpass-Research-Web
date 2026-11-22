"""Latest equity screener observations. Historical backtests consume their own dated data."""
from datetime import datetime, timezone
import json
import math
import time
from threading import Lock
import urllib.error
import urllib.request

from .market_prices import MarketBacktestError, resolve_universe
from .market_universe import EXCHANGES, SCANNERS
from .symbol_search import ALIASES

COLUMNS = ['description', 'sector.tr', 'industry.tr', 'close', 'currency', 'volume',
           'market_cap_basic', 'price_earnings_ttm', 'price_book_fq', 'return_on_equity',
           'operating_margin_ttm', 'debt_to_equity', 'net_income_ttm', 'time',
           'fiscal_period_end_fq', 'fundamental_currency_code']


def number(value):
    return value if type(value) in (float, int) and math.isfinite(value) else None


def utc_date(value):
    if number(value) is None or not 0 < value < 8_000_000_000:
        return None
    return datetime.fromtimestamp(value, timezone.utc).date().isoformat()


def _fetch(market):
    region, venues = SCANNERS[market]
    members, directory = resolve_universe('market', market, [])
    listed = {symbol.split('.')[0] if market == 'KR' else symbol: (symbol, name)
              for symbol, name in members.items()}
    body = {'columns': COLUMNS, 'range': [0, 20000], 'options': {'lang': 'ko'}, 'filter': [
        {'left':'type', 'operation':'equal', 'right':'stock'},
        {'left':'exchange', 'operation':'in_range', 'right':venues}]}
    req = urllib.request.Request(f'https://scanner.tradingview.com/{region}/scan', data=json.dumps(body).encode(),
                                 headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0 (Hyperpass Research)'})
    with urllib.request.urlopen(req, timeout=20) as res:
        raw = res.read(16_000_001)
    if len(raw) > 16_000_000:
        raise MarketBacktestError('스크리너 응답이 예상 크기를 초과했습니다.')
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not payload.get('data') or len(payload['data']) != payload.get('totalCount'):
        raise MarketBacktestError('스크리너가 전체 조회 결과를 반환하지 않았습니다.')
    aliases = {symbol:(name, terms) for symbol, name, terms in ALIASES}
    rows = []
    for item in payload['data']:
        exchange, _, ticker = item['s'].partition(':')
        key = ticker.replace('.', '-').replace('/', '-') if market == 'US' else ticker
        if key not in listed or exchange not in venues:
            continue
        if len(item['d']) != len(COLUMNS):
            raise MarketBacktestError('스크리너 열 구성이 변경되었습니다.')
        (name, sector, industry, price, currency, volume, cap, per, pbr, roe, margin, debt, income,
         last_bar, fiscal, financial_currency) = item['d']
        yahoo, directory_name = listed[key]
        board = ('KOSPI' if yahoo.endswith('.KS') else 'KOSDAQ') if market == 'KR' else (
            'NYSEAMERICAN' if exchange == 'AMEX' else exchange)
        if currency != ('KRW' if market == 'KR' else 'USD'):
            continue
        price, volume = number(price), number(volume)
        local_name, alternate = aliases.get(item['s'], (None, ''))
        rows.append({'id':item['s'], 'symbol':ticker, 'yahoo':yahoo,
                     'name':directory_name if market == 'KR' else local_name or name or directory_name,
                     'aliases':' '.join(v for v in (name, alternate) if v),
                     'exchange':board, 'sector':sector, 'industry':industry, 'currency':currency,
                     'price':price, 'market_cap':number(cap), 'volume':volume,
                     'turnover':None if price is None or volume is None else price*volume,
                     'per':number(per), 'pbr':number(pbr), 'roe':number(roe), 'margin':number(margin),
                     'debt':number(debt), 'income':number(income), 'income_currency':financial_currency,
                     'price_date':utc_date(last_bar), 'fiscal_date':utc_date(fiscal)})
    if not rows:
        raise MarketBacktestError('상장 목록과 스크리너에서 일치하는 종목이 없습니다.')
    return {'market':market, 'source':'TradingView', 'directory':directory, 'as_of':datetime.now(timezone.utc).isoformat(),
            'listed_count':len(members), 'rows':rows, 'exchanges':EXCHANGES[market]}

FINANCIALS = ('per','pbr','roe','margin','debt','income')


def supplement_kr(data):
    extra = {r['id']:r for r in _fetch('KR')['rows']}
    rows = []
    for original in data['rows']:
        row = dict(original)
        other = extra.get(row['id'], {})
        fields = [k for k in FINANCIALS if row.get(k) is None and other.get(k) is not None]
        if fields:
            row.update((k,other[k]) for k in fields)
            row['supplement_fields'] = fields
            row['supplement_fiscal_date'] = other.get('fiscal_date')
            if 'income' in fields:
                row['income_currency'] = other.get('income_currency')
        rows.append(row)
    return dict(data, rows=rows, supplement='TradingView', supplement_count=sum(bool(r.get('supplement_fields')) for r in rows))


class EquityScreen:
    """One local session, with independent quote refreshes for each market."""
    def __init__(self, sources):
        self.sources = sources
        self.locks = {market:Lock() for market in ('KR','US')}
        self.state_lock = Lock()
        self.cache = {}
        self.progress = {}
        self.kis_revision = 0

    def invalidate_kis(self):
        with self.state_lock:
            self.kis_revision += 1
            self.cache = {k:v for k,v in self.cache.items() if k[0] != 'KR'}

    def status(self, market):
        if market not in self.locks:
            raise ValueError('국내 또는 미국 시장을 선택하세요.')
        with self.state_lock:
            return dict(self.progress.get(market, {'running':False}))

    def _progress(self, market, done=0, total=0, message='시세 제공자에 연결 중'):
        with self.state_lock:
            self.progress[market] = dict(running=True,done=done,total=total,message=message)

    def snapshot(self, market, *, refresh=False, extra=False):
        if market not in self.locks or (extra and market != 'KR'):
            raise ValueError('시장과 자료 출처를 확인하세요.')
        with self.state_lock:
            revision_at_entry = self.kis_revision if market == 'KR' else 0
            at_entry = self.cache.get((market,revision_at_entry,extra))
        with self.locks[market]:
            with self.state_lock:
                revision = self.kis_revision if market == 'KR' else 0
                key = (market,revision,extra)
                previous = self.cache.get(key)
            if previous:
                # A completed full fetch may serve overlapping requests. The clock is for TTL only.
                filled_while_waiting = at_entry is None or previous[2] is not at_entry[2]
                if filled_while_waiting or (not refresh and time.monotonic()-previous[0] < 90):
                    return dict(previous[1], cache_status='cached')
            self._progress(market)
            def report(done,total,message='공급자 데이터 조회 중'):
                self._progress(market,done,total,message)
            try:
                if market == 'KR':
                    from .screen_kis import fetch_snapshot
                    data = fetch_snapshot(self.sources, progress=report)
                else:
                    from .screen_yahoo import fetch_snapshot
                    data = fetch_snapshot(progress=report)
                if extra:
                    self._progress(market,0,0,'선택한 추가 재무 지표 조회 중')
                    try:
                        data = supplement_kr(data)
                    except (OSError, ValueError, TypeError, KeyError):
                        data = dict(data, warnings=[*data.get('warnings',[]),'TradingView 재무 보강을 조회하지 못했습니다. KIS 자료를 표시합니다.'])
                with self.state_lock:
                    if market == 'KR' and revision != self.kis_revision:
                        raise ValueError('KIS 연결이 변경됐습니다. 새 설정으로 다시 조회하세요.')
                    self.cache[key] = (time.monotonic(),data,object())
                return dict(data,cache_status='fresh')
            except (ValueError,OSError) as error:
                provider = '한국투자증권(KIS)' if market == 'KR' else 'Yahoo Finance'
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                if previous and (market != 'KR' or revision == self.kis_revision):
                    return dict(previous[1],cache_status='stale',warning=f'{provider} 갱신에 실패해 마지막 조회 자료를 표시합니다.')
                if isinstance(error, ValueError):
                    raise
                raise MarketBacktestError(f'{provider}에 연결할 수 없습니다. 잠시 후 다시 조회하세요.') from None
            finally:
                with self.state_lock:
                    self.progress[market] = {'running':False}

    def quotes(self, symbols):
        from .screen_kis import fetch_quotes
        with self.locks['KR']:
            revision = self.kis_revision
            self._progress('KR')
            try:
                result = fetch_quotes(self.sources, symbols, progress=lambda done,total,message='KIS 개별 종목 지표 조회 중':self._progress('KR',done,total,message))
                with self.state_lock:
                    if revision != self.kis_revision:
                        raise ValueError('KIS 연결이 변경됐습니다. 다시 조회하세요.')
                    updates = {r['symbol']:r for r in result['rows']}
                    for key,(stamp,old,generation) in list(self.cache.items()):
                        if key[0] != 'KR':
                            continue
                        rows = []
                        for row in old['rows']:
                            patch = updates.get(row['symbol'])
                            if patch:
                                row = {**row, **{k:v for k,v in patch.items() if v is not None}}
                                row['supplement_fields'] = [k for k in row.get('supplement_fields',[]) if patch.get(k) is None]
                            rows.append(row)
                        self.cache[key] = stamp,dict(old,rows=rows),generation
                return result
            finally:
                with self.state_lock:
                    self.progress['KR'] = {'running':False}
