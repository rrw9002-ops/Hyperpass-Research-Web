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
_CACHE = {}
_LOCK = {market: Lock() for market in SCANNERS}


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


def snapshot(market):
    if market not in SCANNERS:
        raise MarketBacktestError('스크리너 시장을 선택하세요.')
    with _LOCK[market]:
        cached = _CACHE.get(market)
        if cached and time.monotonic()-cached[0] < 90:
            return cached[1]
        try:
            data = _fetch(market)
        except (ValueError, OSError, TypeError, KeyError) as error:
            if isinstance(error, urllib.error.HTTPError):
                error.close()
            if cached:
                return dict(cached[1], warning='새 조회에 실패해 마지막 조회 자료를 표시합니다.')
            raise MarketBacktestError('거래소 종목 목록 또는 TradingView 스크리너에 연결할 수 없습니다. 잠시 후 다시 조회하세요.') from None
        _CACHE[market] = time.monotonic(), data
        return data
