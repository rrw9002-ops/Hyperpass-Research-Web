"""Equity classification from the two markets' current TradingView screeners."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from threading import Lock
import time
import urllib.error
import urllib.request

from .market_prices import MarketBacktestError

EXCHANGES = {'KR':{'KOSPI':'코스피', 'KOSDAQ':'코스닥'},
             'US':{'NASDAQ':'나스닥', 'NYSE':'뉴욕증권거래소', 'NYSEAMERICAN':'NYSE American',
                   'NYSEARCA':'NYSE Arca', 'CBOE':'Cboe BZX', 'IEX':'IEX',
                   'TXSE':'텍사스 증권거래소', 'NYSETEXAS':'NYSE Texas'}}
SCANNERS = {'KR':('korea', ['KRX']), 'US':('america', ['NASDAQ','NYSE','AMEX','NYSEARCA','CBOE','IEX','TXSE','NYSETEXAS'])}
SOURCE = 'TradingView 스크리너 · 현재 FactSet 업종 분류'
WARNING = '거래소·업종은 조회 시점 분류입니다. 과거의 업종 변경, 이전상장, 상장폐지는 복원하지 않습니다.'
TTL = 6 * 3600
_cache = {}
_locks = {market:Lock() for market in EXCHANGES}


def validate_universe(market, raw):
    if market not in EXCHANGES or not isinstance(raw, dict) or set(raw) - {'exchanges','sectors','industries'}:
        raise MarketBacktestError('시장·업종 설정을 확인하세요.')
    cleaned = {}
    for key, maximum in [('exchanges', 8), ('sectors', 100), ('industries', 500)]:
        items = raw.get(key, [])
        if not isinstance(items, list) or len(items) > maximum or any(
                not isinstance(v, str) or not v.strip() or len(v) > 140 for v in items):
            raise MarketBacktestError('거래소·업종 선택 값이 올바르지 않습니다.')
        cleaned[key] = sorted({v.strip() for v in items})
    if set(cleaned['exchanges']) - set(EXCHANGES[market]):
        raise MarketBacktestError('선택한 국가에 속하는 거래소를 지정하세요.')
    return cleaned


def _fetch(market):
    region, exchanges = SCANNERS[market]
    body = {'columns':['sector','industry','sector.tr','industry.tr'], 'range':[0,20_000],
            'options':{'lang':'ko'}, 'filter':[{'left':'type','operation':'equal','right':'stock'},
                                               {'left':'exchange','operation':'in_range','right':exchanges}]}
    request = urllib.request.Request(f'https://scanner.tradingview.com/{region}/scan',
                                     data=json.dumps(body).encode(), headers={'Content-Type':'application/json',
                                     'User-Agent':'Mozilla/5.0 (compatible; HyperpassResearch)'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(6_000_001)
        if len(raw) > 6_000_000:
            raise ValueError('scan size')
        result = json.loads(raw)
        if not isinstance(result,dict) or not result.get('data') or len(result['data']) != result['totalCount']:
            raise ValueError('incomplete scan')
        classifications, uncertain, labels = {}, set(), defaultdict(dict)
        sector_labels, venues_by_ticker = {}, defaultdict(set)
        for row in result['data']:
            exchange, symbol = row['s'].split(':',1)
            sector, industry, sector_ko, industry_ko = row['d']
            if exchange not in exchanges:
                continue
            symbol = symbol.replace('.','-').replace('/','-')
            venues_by_ticker[symbol].add(row['s'])
            if not (sector and industry):
                continue
            entry = (sector, industry)
            if symbol in classifications and classifications[symbol] != entry:
                uncertain.add(symbol)
            classifications[symbol] = entry
            sector_labels[sector] = sector_ko or sector
            labels[sector][industry] = industry_ko or industry
        for symbol in uncertain:
            classifications.pop(symbol)
        if not classifications:
            raise ValueError('missing classification')
        sectors = sorted(({'id':s, 'label':sector_labels[s], 'industries':sorted(
                    ({'id':i, 'label':label} for i,label in group.items()),key=lambda item:item['label'])}
                    for s,group in labels.items()),key=lambda item:item['label'])
        return {'by_symbol':classifications, 'sectors':sectors,
                'targets':{k:next(iter(v)) for k,v in venues_by_ticker.items() if len(v)==1},
                'as_of':datetime.now(timezone.utc).isoformat(timespec='seconds')}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        if isinstance(exc, urllib.error.HTTPError):
            exc.close()
        raise MarketBacktestError('TradingView 업종 분류를 읽지 못했습니다. 잠시 후 다시 시도하세요.') from None


def classification(market):
    with _locks[market]:
        item = _cache.get(market)
        if item is None or time.monotonic() >= item[0]:
            item = time.monotonic() + TTL, _fetch(market)
            _cache[market] = item
        return item[1]


def universe_options(market):
    if market not in EXCHANGES:
        raise MarketBacktestError('국내(KR) 또는 미국(US) 시장을 선택하세요.')
    base = {'market':market, 'exchanges':[{'id':k,'label':v} for k,v in EXCHANGES[market].items()],
            'source':SOURCE, 'warning':WARNING}
    try:
        data = classification(market)
        return {**base, 'sectors':data['sectors'], 'as_of':data['as_of']}
    except MarketBacktestError as exc:
        return {**base, 'sectors':[], 'as_of':None, 'warning':f'{exc} 거래소는 계속 선택할 수 있습니다.'}


def filter_industries(market, members, filters):
    data = classification(market)
    sectors, industries = set(filters['sectors']), set(filters['industries'])
    matched, unknown = {}, 0
    for symbol, name in members.items():
        key = symbol.removesuffix('.KS').removesuffix('.KQ') if market == 'KR' else symbol
        row = data['by_symbol'].get(key)
        if not row:
            unknown += 1
        elif row[0] in sectors or row[1] in industries:
            matched[symbol] = name
    provenance = (f"{SOURCE} {data['as_of'][:10]} · 업종 필터 적용 전 {len(members):,}종목, "
                  f"분류 미확인 {unknown:,}종목, 조건 일치 {len(matched):,}종목")
    return matched, provenance
