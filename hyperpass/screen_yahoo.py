"""US exchange-listed equities, with regular-session Yahoo quotes and Yahoo financials."""
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
import json
import math
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request

from .market_prices import MarketBacktestError, US_DIR, _get, _us_listings
from .market_universe import EXCHANGES
from .symbol_search import ALIASES

API = 'https://query1.finance.yahoo.com'
HEADERS = {'User-Agent':'Mozilla/5.0 (compatible; HyperpassResearch)', 'Accept':'*/*'}
BATCH_SIZE = 250
QUOTE_FIELDS = ('symbol', 'longName', 'shortName', 'quoteType', 'currency', 'financialCurrency',
                'regularMarketTime', 'regularMarketPrice', 'regularMarketVolume', 'marketCap',
                'exchange', 'gmtOffSetMilliseconds', 'exchangeDataDelayedBy', 'marketState',
                'quoteSourceName', 'sector', 'industry', 'trailingPE', 'priceToBook')
FUND_FIELDS = ('ticker', 'exchange', 'sector', 'industry', 'peratio.lasttwelvemonths',
               'pricebookratio.quarterly', 'returnonequity.lasttwelvemonths',
               'totaldebtequity.lasttwelvemonths', 'netincomeis.lasttwelvemonths',
               'totalrevenues.lasttwelvemonths', 'operatingincome.lasttwelvemonths')
VENUES = {'NMS':'NASDAQ','NGM':'NASDAQ','NCM':'NASDAQ','NAS':'NASDAQ',
          'NYQ':'NYSE','NYS':'NYSE','ASE':'NYSEAMERICAN','AMX':'NYSEAMERICAN',
          'PCX':'NYSEARCA','BTS':'CBOE','BATS':'CBOE','IEX':'IEX','NYT':'NYSETEXAS','TXS':'TXSE'}
NAMES = {key:(name,terms) for key,name,terms in ALIASES}
SOURCE_QUOTE = 'Yahoo Finance · 정규장 시세'
SOURCE_FUND = 'Yahoo Finance · 기업 재무 스크리너'
FIELD_SOURCES = {**dict.fromkeys(('price','volume','market_cap','price_date','price_time'), SOURCE_QUOTE),
                 **dict.fromkeys(('sector','industry','per','pbr','roe','debt','income'), 'Yahoo Finance'),
                 'turnover':'Yahoo Finance 정규장 가격 × 누적 거래량',
                 'margin':'Yahoo Finance · 최근 12개월 영업이익 ÷ 매출 × 100'}


def _number(value):
    return value if type(value) in (int,float) and math.isfinite(value) else None


def _timestamp(value):
    if _number(value) is not None and 0 < value < 8_000_000_000:
        return datetime.fromtimestamp(value, timezone.utc)
    return None


def _listed():
    members = {}
    for file, nasdaq in (('nasdaqlisted.txt', True), ('otherlisted.txt', False)):
        listings = list(_us_listings(_get(US_DIR + file, 4_000_000), nasdaq, screen_candidates=True))
        if not listings:
            raise MarketBacktestError('Nasdaq Trader 미국 상장 목록을 읽지 못했습니다.')
        for ticker, name, venue in listings:
            if venue in EXCHANGES['US']:
                members[ticker] = (name, venue)
    return members


class _YahooSession:
    """An anonymous Yahoo web session. Its guest cookie and crumb live only in memory."""
    def __init__(self):
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self.crumb = ''
        # Yahoo's public guest endpoint normally issues the cookie with a 404.
        try:
            self._read('https://fc.yahoo.com', limit=65536)
        except HTTPError as error:
            if error.code != 404:
                raise
            error.close()
        data = self._read(API+'/v1/test/getcrumb', limit=512)
        self.crumb = data.decode('ascii').strip()
        if not self.crumb or len(self.crumb)>128 or any(ord(c)<=32 or c in '<>' for c in self.crumb):
            raise MarketBacktestError('Yahoo Finance 익명 조회 세션을 시작하지 못했습니다.')

    def _read(self, url, body=None, *, limit=4_000_000):
        headers = dict(HEADERS)
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with self.opener.open(request, timeout=12) as response:
            raw = response.read(limit+1)
        if len(raw)>limit:
            raise MarketBacktestError('Yahoo Finance 응답이 허용한 크기를 초과했습니다.')
        return raw

    def _json(self, path, params, body=None):
        params = dict(params, formatted='false', lang='en-US', region='US', crumb=self.crumb)
        raw = self._read(API+path+'?'+urlencode(params), body)
        try:
            data = json.loads(raw)
        except (ValueError,UnicodeError):
            raise MarketBacktestError('Yahoo Finance JSON 응답을 확인할 수 없습니다.') from None
        if not isinstance(data,dict):
            raise MarketBacktestError('Yahoo Finance 응답 형식이 변경되었습니다.')
        return data

    def quotes(self, symbols):
        data = self._json('/v7/finance/quote', {'symbols':','.join(symbols),'fields':','.join(QUOTE_FIELDS)})
        result = data.get('quoteResponse') or {}
        if not isinstance(result,dict) or result.get('error') or not isinstance(result.get('result'),list):
            raise MarketBacktestError('Yahoo Finance가 미국 정규장 시세를 반환하지 않았습니다.')
        return result['result']

    def fundamentals(self, symbols):
        # Select explicit tickers so changes in a live market-cap ranking cannot skip or duplicate a page.
        query = {'operator':'or','operands':[{'operator':'eq','operands':['ticker',s]} for s in symbols]}
        body = {'size':len(symbols), 'offset':0, 'sortField':'ticker', 'sortType':'ASC',
                'quoteType':'EQUITY', 'query':query, 'includeFields':list(FUND_FIELDS)}
        data = self._json('/v1/finance/screener', {'useRecordsResponse':'true'}, body)
        finance = data.get('finance') or {}
        matches = finance.get('result') if isinstance(finance,dict) and not finance.get('error') else None
        if not isinstance(matches,list) or not matches or not isinstance(matches[0],dict) or not isinstance(matches[0].get('records'),list):
            raise MarketBacktestError('Yahoo Finance가 기업 재무 스크리너 응답을 반환하지 않았습니다.')
        return {row['ticker']:row for row in matches[0]['records'] if isinstance(row,dict) and row.get('ticker')}


def _observation(quote, fundamentals, members):
    ticker = quote.get('symbol')
    if ticker not in members or quote.get('quoteType') != 'EQUITY' or quote.get('currency') != 'USD':
        return None
    directory_name, board = members[ticker]
    if VENUES.get(quote.get('exchange')) != board:
        return None
    price, observed = _number(quote.get('regularMarketPrice')), _timestamp(quote.get('regularMarketTime'))
    if price is None or price<=0 or not observed:
        return None
    if VENUES.get(fundamentals.get('exchange')) != board:
        fundamentals = {}
    code = ticker.replace('-','.')
    identity = ('AMEX' if board=='NYSEAMERICAN' else board)+':'+code
    alias, terms = NAMES.get(identity, (None,''))
    issuer = quote.get('longName') or quote.get('shortName') or directory_name
    volume = _number(quote.get('regularMarketVolume'))
    debt_pct = _number(fundamentals.get('totalDebtEquityPercentLtm'))
    income = _number(fundamentals.get('netIncomeIsLtm'))
    sales, profit = _number(fundamentals.get('totalRevenueLtm')), _number(fundamentals.get('operatingIncomeLtm'))
    reporting_currency = quote.get('financialCurrency')
    offset = _number(quote.get('gmtOffSetMilliseconds'))
    market_date = observed + timedelta(milliseconds=offset) if offset and abs(offset)<=14*3600000 else observed
    per = _number(fundamentals.get('peRatioLtm'))
    pbr = _number(fundamentals.get('priceBookRatioQuarterly'))
    return {'id':identity, 'symbol':code, 'yahoo':ticker, 'name':alias or issuer, 'aliases':' '.join((issuer,terms)),
            'exchange':board, 'sector':fundamentals.get('sector') or quote.get('sector'),
            'industry':fundamentals.get('industry') or quote.get('industry'), 'currency':'USD',
            'price':price,'volume':volume,'turnover':None if volume is None else price*volume,
            'market_cap':_number(quote.get('marketCap')), 'per':per if per is not None else _number(quote.get('trailingPE')),
            'pbr':pbr, 'roe':_number(fundamentals.get('returnOnEquityPercentLtm')),
            'margin':100*profit/sales if sales is not None and sales>0 and profit is not None else None,
            'debt':debt_pct/100 if debt_pct is not None else None, 'income':income if reporting_currency else None,
            'income_currency':reporting_currency, 'price_time':observed.isoformat(timespec='seconds'),
            'price_date':market_date.date().isoformat(), 'fiscal_date':None,
            'delay_minutes':_number(quote.get('exchangeDataDelayedBy')), 'quote_state':quote.get('marketState'),
            'quote_source':quote.get('quoteSourceName')}


def _safe_error(error):
    if isinstance(error,HTTPError):
        status=error.code
        error.close()
        return f'Yahoo Finance가 조회를 제한했습니다 (HTTP {status}).' if status in (401,403,429) else f'Yahoo Finance가 HTTP {status}를 반환했습니다.'
    if isinstance(error,MarketBacktestError):
        return str(error)
    return 'Yahoo Finance 연결 또는 응답을 확인할 수 없습니다.'


def fetch_snapshot(*, progress=None):
    if progress:
        progress(0,0,'Nasdaq Trader 미국 상장 목록을 조회합니다.')
    members = _listed()
    try:
        session = _YahooSession()
    except (OSError, ValueError) as error:
        raise MarketBacktestError(_safe_error(error)) from None
    rows, warnings, processed = {}, [], 0
    symbols = sorted(members)
    use_financials = True
    for start in range(0,len(symbols),BATCH_SIZE):
        batch = symbols[start:start+BATCH_SIZE]
        if progress:
            progress(processed,len(symbols),f'Yahoo Finance 미국 정규장 시세·재무 지표 {processed:,} / {len(symbols):,}종목 조회')
        try:
            quotes = session.quotes(batch)
        except (ValueError,OSError) as error:
            reason = _safe_error(error)
            if not rows:
                raise MarketBacktestError(reason) from None
            warnings.append(f'{processed:,}개 종목 요청 후 시세 수집을 중단했습니다. {reason}')
            break
        fundamentals = {}
        stop_after_batch = False
        if use_financials:
            try:
                fundamentals = session.fundamentals(batch)
            except (ValueError,OSError) as error:
                status = error.code if isinstance(error,HTTPError) else None
                warnings.append('이후 종목의 재무 지표를 조회하지 못했습니다. '+_safe_error(error))
                use_financials = False
                # When Yahoo explicitly limits requests, stop after the quotes already received.
                if status in (401,403,429):
                    stop_after_batch = True
                    warnings.append('Yahoo 요청 제한으로 추가 종목 조회를 중단했습니다.')
        requested = set(batch)
        for item in quotes:
            if not isinstance(item,dict) or item.get('symbol') not in requested:
                continue
            row = _observation(item,fundamentals.get(item['symbol'],{}),members)
            if row:
                rows[row['yahoo']] = row
        processed += len(batch)
        if stop_after_batch:
            break
    if not rows:
        raise MarketBacktestError('미국 상장 목록과 일치하는 Yahoo 정규장 시세·관측 시각이 없습니다.')
    if progress:
        progress(processed,len(symbols),f'Yahoo Finance에서 실제 시세 {len(rows):,}종목을 받았습니다.')
    return {'market':'US','source':'Yahoo Finance','directory':'Nasdaq Trader · 미국 거래소 상장 목록과 Yahoo EQUITY 교집합','as_of':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'rows':list(rows.values()), 'listed_count':len(members), 'exchanges':EXCHANGES['US'],
            'field_sources':FIELD_SOURCES,'warnings':warnings, 'requested_count':processed,
            'note':'시세 시각은 종목별 정규장 마지막 체결 시각입니다. 거래소별 지연 시간이 다릅니다. '
                   '재무 지표는 Yahoo 최근 12개월 기준이며 PBR은 직전 분기 기준입니다. 종목별 결산일은 응답에 없습니다.'}
