"""Korea Investment & Securities KRX listing master, read-only quotes and quote timestamps."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import io
import math
import re
import urllib.error
import urllib.request
import zipfile

from .data_sources import DataSourceError
from .symbol_search import ALIASES, KR_CODE

MASTER_URL = 'https://new.real.download.dws.co.kr/common/master/'
KST = timezone(timedelta(hours=9))
# The two official fixed-width layouts differ after their shared classification fields.
# KIS stocks_info/종목마스터정보(코스피).h and (코스닥).h describe byte offsets, not decoded characters.
BOARD = {
    'kospi': dict(exchange='KOSPI', suffix='.KS', width=288, reference=102, volume=142,
                  revenue=224, profit=233, roe=256, fiscal=265, cap=273),
    'kosdaq': dict(exchange='KOSDAQ', suffix='.KQ', width=282, reference=97, volume=137,
                   revenue=218, profit=227, roe=250, fiscal=259, cap=267),
}
ALIASES_BY_ID = {identity:aliases for identity, _, aliases in ALIASES}


def now():
    return datetime.now(timezone.utc).isoformat()


def _number(value, *, positive=False, nonnegative=False):
    try:
        if isinstance(value, (bytes, str)):
            value = value.strip()
        n = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(n) or positive and n <= 0 or nonnegative and n < 0:
        return None
    return int(n) if n.is_integer() else n


def _date(raw):
    if isinstance(raw, bytes):
        raw = raw.decode('ascii', errors='ignore')
    if not isinstance(raw, str) or not re.fullmatch(r'\d{8}',raw):
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:])).isoformat()
    except ValueError:
        return None


def _master(name):
    filename = name + '.mst'
    req = urllib.request.Request(MASTER_URL + filename + '.zip', headers={'User-Agent':'Hyperpass-Research'})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            binary = response.read(4_000_001)
            modified = response.headers.get('Last-Modified')
        if len(binary) > 4_000_000:
            raise ValueError('large archive')
        with zipfile.ZipFile(io.BytesIO(binary)) as z:
            info = z.getinfo(filename)
            if info.file_size > 8_000_000:
                raise ValueError('large member')
            content = z.read(info)
        published = parsedate_to_datetime(modified).astimezone(timezone.utc).isoformat() if modified else None
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as e:
        if isinstance(e, urllib.error.HTTPError):
            e.close()
        raise DataSourceError('한국투자증권 공식 종목 마스터 파일을 읽을 수 없습니다. 잠시 후 다시 조회하세요.') from None
    return content, published


def _industries(content):
    # idx_div (1 byte), industry code (4), Korean name (40).
    names = {line[1:5]:line[5:45].decode('cp949').strip() for line in content.splitlines() if len(line)>=6}
    if not names:
        raise DataSourceError('KIS 업종 마스터가 비어 있습니다.')
    return names


def _listings(content, board, industries, published):
    layout = BOARD[board]
    rows = []
    for line in content.splitlines():
        if line[61:63] not in (b'ST', b'FS'):
            continue
        if len(line) != layout['width']:
            raise DataSourceError('KIS 상장 마스터의 고정폭 형식이 바뀌어 수치를 확인할 수 없습니다.')
        ticker = line[:9].strip().decode('ascii')
        name = line[21:61].decode('cp949').strip()
        if not KR_CODE.fullmatch(ticker) or not name:
            continue

        def field(key, width):
            offset = layout[key]
            return line[offset:offset+width]

        revenue = _number(field('revenue',9),positive=True)
        profit = _number(field('profit',9))
        fiscal = _date(field('fiscal',8))
        cap = _number(field('cap',9),positive=True)
        sector, middle, detail = (industries.get(line[i:i+4]) if line[i:i+4]!=b'0000' else None for i in (64,68,72))
        identity = 'KRX:' + ticker
        rows.append({'id':identity, 'symbol':ticker, 'name':name, 'yahoo':ticker + layout['suffix'],
                     'aliases':ALIASES_BY_ID.get(identity,''), 'currency':'KRW','income_currency':'KRW',
                     'exchange':layout['exchange'], 'sector':sector, 'industry': detail or middle or sector,
                     'price':_number(field('reference',9),positive=True),
                     'volume':_number(field('volume',12),nonnegative=True),
                     'market_cap':None if cap is None else cap * 100_000_000,
                     'per':None, 'pbr':None, 'roe':_number(field('roe',9)) if fiscal else None,
                     'margin':100 * profit / revenue if fiscal and revenue and profit is not None else None,
                     'income':None,'debt':None,'turnover':None,'fiscal_date':fiscal,
                     'price_date':None, 'price_time':None,'master_at':published,
                     'quote_source':'KIS 종목 마스터', 'quote_mode':'master','quote_received_at':None})
    if not rows:
        raise DataSourceError('KIS 상장 마스터에서 국내 주식 종목을 찾지 못했습니다.')
    return rows


def _quote(code, raw, *, detailed, received):
    if not isinstance(raw,dict):
        return None
    key = 'stck_shrn_iscd' if detailed else 'inter_shrn_iscd'
    if raw.get(key) != code:
        return None
    price = _number(raw.get('stck_prpr' if detailed else 'inter2_prpr'),positive=True)
    if price is None:
        return None
    day = _date(raw.get('stck_bsop_date'))
    clock = raw.get('stck_cntg_hour')
    trade_time = None
    if day and isinstance(clock,str) and re.fullmatch(r'[0-9]{6}',clock):
        try:
            trade_time = datetime.strptime(day+clock,'%Y-%m-%d%H%M%S').replace(tzinfo=KST).isoformat()
        except ValueError:
            pass
    result = {'id':'KRX:'+code,'symbol':code, 'price':price,
              'volume':_number(raw.get('acml_vol'),nonnegative=True),
              'turnover':_number(raw.get('acml_tr_pbmn'),nonnegative=True),
              'price_date':day,'price_time':trade_time,'quote_received_at':received,'quote_mode':'api',
              'quote_source':'KIS 현재가 API' if detailed else 'KIS 복수종목 시세 API'}
    if detailed:
        # The single-symbol endpoint reports market capitalization in 100 million KRW.
        cap = _number(raw.get('hts_avls'),positive=True)
        measured = dict(market_cap=cap * 100_000_000 if cap is not None else None,
                        per=_number(raw.get('per')), pbr=_number(raw.get('pbr')))
        result.update({key:value for key,value in measured.items() if value is not None})
    return result


def _progress(callback, done, total, label):
    if callback:
        callback(done,total,label)


def fetch_snapshot(sources, *, progress=None):
    _progress(progress,0,1,'KIS 공식 상장·업종 마스터 조회')
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {key:pool.submit(_master, name) for key,name in
                [('kospi','kospi_code'),('kosdaq','kosdaq_code'),('industry','idxcode')]}
        industries = _industries(jobs['industry'].result()[0])
        rows = []
        master_times = {}
        for board in BOARD:
            content, published = jobs[board].result()
            rows.extend(_listings(content,board,industries,published))
            master_times[BOARD[board]['exchange']] = published
    configured = sources is not None and sources.status()['kis']['configured']
    quotes = {}
    warnings = []
    if configured:
        total = len(rows)
        for start in range(0,total,30):
            _progress(progress,start,total,'KIS 복수종목 시세 조회')
            codes = [r['symbol'] for r in rows[start:start+30]]
            data = sources.kis_quotes(codes)
            received = now()
            for value in data:
                code = value.get('inter_shrn_iscd') if isinstance(value,dict) else None
                if code in codes:
                    quote = _quote(code,value,detailed=False,received=received)
                    if quote:
                        quotes[code] = quote
        if not quotes:
            raise DataSourceError('KIS 복수종목 API가 검증할 수 있는 현재가를 반환하지 않았습니다.')
        for row in rows:
            if row['symbol'] in quotes:
                row.update(quotes[row['symbol']])
            else:
                row.update(price=None,volume=None,turnover=None,quote_mode='unavailable',quote_source='KIS 시세 미수신')
        if len(quotes) < total:
            warnings.append(f'KIS 현재가 미수신 {total-len(quotes):,}종목은 가격·거래량을 공란으로 표시합니다.')
    _progress(progress,len(rows),len(rows),'국내 종목 수집 완료')
    quote_mode = 'api' if configured else 'master'
    notes = {'price':('한국투자증권 KRX 현재가입니다. API 수신 시각과 거래소 체결 시각은 다를 수 있습니다.' if configured else
                      '종목 마스터의 기준가입니다. 권리락 등으로 직전 종가와 다를 수 있습니다. 데이터 연결에서 KIS 등록 후 갱신하면 현재가를 조회합니다.'),
             'volume':'KIS API 누적 거래량' if configured else '마스터의 전일 거래량',
             'market_cap':'KIS 마스터의 전일 기준 시가총액입니다. 개별 KIS 시세 조회 시 API 시가총액으로 갱신합니다.',
             'turnover':'KIS API의 실제 누적 거래대금입니다. 마스터에는 누적 거래대금이 없습니다.',
             'per':'개별 KIS 시세 갱신 시 PER를 받습니다. 마스터·복수종목 시세에는 없습니다.',
             'pbr':'개별 KIS 시세 갱신 시 PBR를 받습니다. 마스터·복수종목 시세에는 없습니다.',
             'margin':'KIS 마스터의 재무 기준일 매출액과 영업이익으로 계산한 영업이익률입니다.',
             'roe':'KIS 마스터의 재무 기준일 ROE입니다.',
             'debt':'KIS 상장 마스터·시세 응답에 부채비율이 없습니다.',
             'income':'KIS 상장 마스터는 최근 12개월 순이익(TTM)을 제공하지 않습니다.'}
    received_at = now()
    return {'market':'KR','provider':'kis','source':'한국투자증권 KIS','quote_mode':quote_mode,
            'directory':'KIS 코스피·코스닥 상장 마스터 (주권·외국주권)',
            'exchanges':{'KOSPI':'코스피','KOSDAQ':'코스닥'},'listed_count':len(rows),'rows':rows,
            'as_of':received_at,'master_times':master_times,'quoted_count':len(quotes),
            'price_label':'현재가' if configured else '기준가','turnover_label':'누적 거래대금',
            'volume_label':'누적 거래량' if configured else '전일 거래량',
            'field_notes':notes, 'warnings':warnings,
            'latest_time':max((r['price_time'] for r in quotes.values() if r['price_time']), default=None),
            'master_at':max((s for s in master_times.values() if s),default=None)}


def fetch_quotes(sources, symbols, *, progress=None):
    if not isinstance(symbols,list) or not 1<=len(symbols)<=40:
        raise DataSourceError('조회할 국내 주식 종목을 1~40개 선택하세요.')
    codes = []
    for item in symbols:
        if not isinstance(item,str):
            raise DataSourceError('국내 주식 종목 코드를 확인하세요.')
        code = item.removeprefix('KRX:').removesuffix('.KS').removesuffix('.KQ')
        if not KR_CODE.fullmatch(code):
            raise DataSourceError('국내 주식 종목 코드를 확인하세요.')
        if code not in codes:
            codes.append(code)
    if sources is None or not sources.status()['kis']['configured']:
        raise DataSourceError('데이터 연결에서 한국투자증권 KIS App Key와 Secret을 등록한 후 현재가를 조회하세요.')
    result = []
    warnings = []
    for index,code in enumerate(codes):
        _progress(progress,index,len(codes),'KIS 현재가·PER·PBR 조회')
        try:
            raw = sources.kis_quotes([code],detailed=True)
            quote = _quote(code,raw,detailed=True,received=now())
        except DataSourceError as error:
            if not result:
                raise
            warnings.append(f'{len(codes)-index}종목 갱신을 완료하지 못했습니다. {error}')
            break
        if quote:
            result.append(quote)
        else:
            warnings.append(code + '의 현재가 또는 반환 종목 코드를 확인할 수 없습니다.')
    if not result:
        raise DataSourceError('요청한 종목과 일치하는 KIS 현재가 응답이 없습니다.')
    return {'rows':result,'warnings':warnings,'source':'한국투자증권 KIS','provider':'kis','as_of':now(),
            'quote_mode':'api','price_label':'현재가','turnover_label':'누적 거래대금','volume_label':'누적 거래량'}
