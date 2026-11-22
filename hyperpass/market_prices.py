"""Current equity universes and bounded, cached daily price history for the lab."""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from . import symbol_search

CURRENT_LIST_WARNING = '조회 시점의 상장 목록을 사용합니다. 과거 편입·퇴출·상장폐지를 복원하지 않아 생존편향이 있습니다.'
KR_SOURCE = '한국투자증권 KOSPI·KOSDAQ 종목 마스터 (ST·FS 주권)'
US_SOURCE = 'Nasdaq Trader nasdaqlisted·otherlisted (보통주·일반주·ADR 표기, ETF·테스트 종목 제외)'
US_DIR = 'https://www.nasdaqtrader.com/dynamic/SymDir/'
YAHOO = 'https://query1.finance.yahoo.com/v8/finance/chart/'


class MarketBacktestError(ValueError):
    pass


class ProviderUnavailable(MarketBacktestError):
    pass


def _get(url, limit):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; HyperpassResearch)'})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        if status in (401, 403, 429):
            raise ProviderUnavailable(f'제공자가 조회를 제한했습니다 (HTTP {status}). 잠시 후 다시 시도하세요.') from None
        if status >= 500:
            raise ProviderUnavailable(f'가격 제공자 일시 오류 (HTTP {status})') from None
        raise MarketBacktestError(f'제공자 응답 HTTP {status}') from None
    except OSError:
        raise ProviderUnavailable('데이터 제공자 연결 시간 초과 또는 네트워크 오류') from None
    if len(raw) > limit:
        raise MarketBacktestError('데이터 제공자의 응답 크기가 허용 범위를 초과합니다.')
    return raw


def _us_listings(content, nasdaq=False):
    rows = csv.DictReader(io.StringIO(content.decode('utf-8-sig')), delimiter='|')
    other = {'N':'NYSE','A':'NYSEAMERICAN','P':'NYSEARCA','Z':'CBOE','V':'IEX','F':'TXSE','M':'NYSETEXAS'}
    for row in rows:
        if row.get('ETF') != 'N' or row.get('Test Issue') != 'N':
            continue
        raw = row.get('Symbol') or row.get('ACT Symbol') or ''
        name = (row.get('Security Name') or '').strip()
        if not re.search(r'common (stock|shares?)|ordinary shares?|depositary (shares?|receipts?)|\bADR\b|capital stock|subordinate voting shares?', name, re.I):
            continue
        if re.search(r'\bwarrants?\b|\bpreferred\b|\bunits?\b|\brights? to\b', name, re.I):
            continue
        if re.fullmatch(r'[A-Z]{1,6}(?:[./-][A-Z]{1,2})?', raw):
            yield raw.replace('.', '-').replace('/', '-'), name, 'NASDAQ' if nasdaq else other.get(row.get('Exchange'))


def _us_stocks(content):
    return ((ticker, name) for ticker, name, exchange in _us_listings(content))


def validate_universe(market, raw):
    from .market_universe import validate_universe as validate
    return validate(market, raw)


def _listed(market, exchanges):
    members = {}
    if market == 'US':
        for filename in ('nasdaqlisted.txt', 'otherlisted.txt'):
            nasdaq = filename == 'nasdaqlisted.txt'
            if exchanges and (nasdaq and 'NASDAQ' not in exchanges or not nasdaq and exchanges == {'NASDAQ'}):
                continue
            rows = list(_us_listings(_get(US_DIR + filename, 4_000_000), nasdaq))
            if not rows:
                raise MarketBacktestError('미국 거래소 상장 목록을 읽지 못했습니다. 시장 검증을 다시 시도하세요.')
            members.update((ticker, name) for ticker, name, exchange in rows if not exchanges or exchange in exchanges)
        return members, US_SOURCE
    for board in ('kospi','kosdaq'):
        if exchanges and board.upper() not in exchanges:
            continue
        rows, available = symbol_search.kr_listings(board)
        eligible = {yahoo: name for _, name, yahoo, group in rows if group in ('ST','FS')}
        if not available or not eligible:
            raise MarketBacktestError(f'{board.upper()} 상장 목록을 갱신하지 못했습니다. 시장 검증을 다시 시도하세요.')
        members.update(eligible)
    return members, KR_SOURCE


def resolve_universe(mode, market, inputs, universe=None):
    from .market_universe import filter_industries
    filters = validate_universe(market, {} if universe is None else universe)
    exchanges = set(filters['exchanges'])
    if mode == 'market':
        members, source = _listed(market, exchanges)
    else:
        members = _input_members(market, inputs)
        source = '사용자가 입력한 종목 목록'
        if exchanges:
            listed, directory = _listed(market, exchanges)
            members = {ticker:name for ticker,name in members.items() if ticker in listed}
            source += ' · ' + directory
    if exchanges:
        source += ' · ' + ', '.join(sorted(exchanges))
    if filters['sectors'] or filters['industries']:
        members, detail = filter_industries(market, members, filters)
        source += ' · ' + detail
    if not members:
        raise MarketBacktestError('선택한 거래소·업종에 해당하는 종목이 없습니다. ' + source)
    return members, source


def pine_universe(mode, market, inputs, universe=None):
    """Return exchange-qualified chart identities verified by the listing/classification sources."""
    from .market_universe import classification
    names, source = resolve_universe(mode, market, inputs, universe)
    if market == 'KR':
        return {yahoo:{'name':name,'target_symbol':'KRX:'+yahoo.split('.')[0]} for yahoo,name in names.items()}, source
    try:
        targets = classification('US')['targets']
    except MarketBacktestError as error:
        raise MarketBacktestError(f'Pine 실행 대상의 미국 거래소 심볼을 확인할 수 없습니다. {error}') from None
    return {symbol:{'name':name,'target_symbol':targets.get(symbol)} for symbol,name in names.items()}, source

def _input_members(market, inputs):
    members = {}
    for query in inputs:
        # Explicit price symbols need no listing lookup. Currency is checked on every history.
        symbol = query.strip().upper()
        known = symbol_search._direct(query)
        if market == 'US' and query == symbol and not known and re.fullmatch(r'[A-Z]{1,6}(?:[.-][A-Z])?', symbol):
            members[symbol.replace('.', '-')] = symbol
            continue
        if market == 'KR' and re.fullmatch(r'[A-Z0-9]{6}\.K[SQ]', symbol):
            members[symbol] = symbol
            continue
        try:
            record = known or symbol_search.resolve_symbol(query, 'yahoo')
            symbol = str(record['yahoo'])
        except (ValueError, TypeError, KeyError, OSError):
            raise MarketBacktestError(f'종목을 식별하지 못했습니다: {query}. 종목명이나 거래소 티커를 확인하세요.') from None
        if not symbol or (market == 'KR') != symbol.endswith(('.KS','.KQ')):
            raise MarketBacktestError(f'{query}: 선택한 시장과 일치하는 종목을 입력하세요.')
        members[symbol] = record['name']
    return members


class PriceRows(list):
    """Observed sessions and dates rejected for missing or contradictory source prices."""
    def __init__(self, rows=(), omitted=()):
        super().__init__(rows)
        self.omitted = list(omitted)


def _midnight(day):
    return int(datetime.combine(day, time(), timezone.utc).timestamp())


def read_prices(symbol, start, end, cache_dir=None, *, with_events=False):
    """Read daily prices, optionally adding consistent split-adjusted volume and cash dividend events."""
    # All symbols enter via a fixed provider path. The cache is keyed by symbol and
    # stores one latest interval. Do not reuse intraday observations or stale corrections.
    cache = None
    if cache_dir:
        cache = Path(cache_dir) / (hashlib.sha256((symbol + ('/events-v1' if with_events else '')).encode()).hexdigest() + '.json.gz')
        if cache.exists() and datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < 86400:
            try:
                with gzip.open(cache, 'rt', encoding='utf8') as stream:
                    saved = json.load(stream)
                if saved['symbol'] == symbol and saved['from'] <= start.isoformat() and saved['to'] >= end.isoformat():
                    first, last = start.isoformat(), end.isoformat()
                    return saved['currency'], PriceRows((r for r in saved['rows'] if first <= r[0] <= last),
                                                         (d for d in saved.get('omitted', ()) if first <= d <= last))
            except (KeyError, ValueError, TypeError, OSError, EOFError):
                pass
    query = {'period1': _midnight(start), 'period2': _midnight(end + timedelta(days=1)), 'interval':'1d'}
    if with_events:
        query['events'] = 'div'
    params = urllib.parse.urlencode(query)
    url = YAHOO + urllib.parse.quote(symbol, safe='') + '?' + params
    try:
        payload = json.loads(_get(url, 2_000_000))['chart']['result'][0]
        metadata = payload['meta']
        if metadata['symbol'].upper() != symbol.upper():
            raise MarketBacktestError('반환된 종목 식별자가 요청과 다릅니다.')
        currency = str(metadata['currency']).upper()
        quote = payload['indicators']['quote'][0]
        dividends = {}
        if with_events:
            for record in (payload.get('events') or {}).get('dividends', {}).values():
                ex_day = datetime.fromtimestamp(record['date'], timezone.utc).date().isoformat()
                amount = record['amount']
                if type(amount) not in (int,float) or not math.isfinite(amount) or amount < 0:
                    raise MarketBacktestError('현금배당 금액이 유효하지 않습니다.')
                if record.get('currency', currency) != currency:
                    raise MarketBacktestError('현금배당 통화와 주가 통화가 달라 합산할 수 없습니다.')
                if start.isoformat() <= ex_day <= end.isoformat():
                    dividends[ex_day] = dividends.get(ex_day, 0.) + amount
        rows = PriceRows()
        for i, stamp in enumerate(payload.get('timestamp', [])):
            day = datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
            values = [quote[k][i] for k in ('open','high','low','close')]
            op, high, low, close = values
            if (not all(type(v) in (int,float) and math.isfinite(v) and v > 0 for v in values)
                    or min(op,close) < low * (1-1e-9) or max(op,close) > high * (1+1e-9)):
                if start.isoformat() <= day <= end.isoformat():
                    rows.omitted.append(day)
                continue
            if rows and day <= rows[-1][0]:
                raise MarketBacktestError('OHLC 일자 중복 또는 역순')
            if start.isoformat() <= day <= end.isoformat():
                row = [day, *values]
                if with_events:
                    volumes = quote.get('volume') or []
                    volume = volumes[i] if i < len(volumes) else None
                    if volume is not None and (type(volume) not in (int,float) or not math.isfinite(volume) or volume < 0):
                        raise MarketBacktestError('거래량이 유효하지 않습니다.')
                    row.extend([volume, dividends.pop(day, 0.)])
                rows.append(row)
        if dividends:
            raise MarketBacktestError('현금배당의 배당락일에 대응하는 가격 봉이 없어 배당을 검증할 수 없습니다.')
    except (KeyError, TypeError, IndexError, OverflowError, json.JSONDecodeError):
        raise MarketBacktestError('제공자에서 일봉 이력을 읽지 못했습니다.') from None
    if len(rows) < 2:
        raise MarketBacktestError('관측된 일봉이 2개 미만입니다.')
    if cache:
        temp = None
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=cache.parent, delete=False) as file:
                temp = Path(file.name)
                with gzip.GzipFile(fileobj=file, mode='wb', compresslevel=1) as compressed:
                    result = {'symbol':symbol, 'from':start.isoformat(), 'to':end.isoformat(), 'currency':currency, 'rows':rows, 'omitted':rows.omitted}
                    compressed.write(json.dumps(result, separators=(',',':')).encode('utf8'))
            os.replace(temp, cache)
        except OSError:
            pass
        finally:
            if temp:
                temp.unlink(missing_ok=True)
    return currency, rows
