"""Validate the recorded, present-day screener selection for watchlists and backtests."""
import math
import re
from datetime import datetime


FIELDS = {'price', 'market_cap', 'turnover', 'per', 'pbr', 'roe', 'margin', 'debt', 'volume', 'income'}


def _text(value, limit=256):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('선정 기록의 텍스트를 확인하세요.')
    return value.strip()


def _date(value, *, required=False):
    if not value and not required:
        return ''
    value = _text(value, 48)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if required and not parsed.tzinfo:
            raise ValueError()
    except ValueError:
        raise ValueError('선정 기록에 유효한 기준 시각이 필요합니다.') from None
    return value


def _number(value):
    if value is not None and (type(value) not in (float, int) or abs(value) > 1e100 or not math.isfinite(value)):
        raise ValueError('선정 기록의 숫자를 확인하세요.')
    return value


def _mapping(value):
    if not isinstance(value, dict):
        raise ValueError('선정 기록의 형식을 확인하세요.')
    return value


def _items(value, limit):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError('선정 목록의 크기와 형식을 확인하세요.')
    return value


def normalize_selection(snapshot, market=None, symbols=None):
    raw = _mapping(snapshot)
    region = raw.get('market')
    if (raw.get('version') != 1 or raw.get('kind') != 'screener_fixed_basket' or
            region not in ('KR', 'US') or (market is not None and market != region)):
        raise ValueError('선정 기록의 시장과 형식을 확인하세요.')
    selected = _date(raw.get('selected_at'), required=True)
    received = _date(raw.get('data_as_of'), required=True)
    provider = _text(raw.get('provider'))
    if not provider:
        raise ValueError('선정 기록에 데이터 제공자가 필요합니다.')
    filters = _mapping(raw.get('filters'))
    criteria = {k: _text(filters.get(k, '')) for k in ('query', 'sector', 'industry')}
    criteria['exchanges'] = [_text(x, 48) for x in _items(filters.get('exchanges', []), 20)]
    criteria['ranges'] = []
    for entry in _items(filters.get('ranges', []), 80):
        item = _mapping(entry)
        field = _text(item.get('field'), 24)
        low, high = _number(item.get('min')), _number(item.get('max'))
        if field not in FIELDS or (low is None and high is None) or (None not in (low, high) and low > high):
            raise ValueError('선정 지표 범위를 확인하세요.')
        criteria['ranges'].append(dict(field=field, min=low, max=high))
    counts = _mapping(raw.get('counts'))
    counts = {k: counts.get(k) for k in ('scope', 'evaluable', 'passed', 'failed', 'missing')}
    if (any(type(x) is not int or not 0 <= x <= 10000000 for x in counts.values()) or
            counts['scope'] != counts['evaluable'] + counts['missing'] or
            counts['evaluable'] != counts['passed'] + counts['failed']):
        raise ValueError('선정 기록의 평가 종목 수를 확인하세요.')
    members = []
    pattern = r'KRX:[0-9][0-9A-Z]{5}' if region == 'KR' else r'(?:NASDAQ|NYSE|AMEX|NYSEARCA|BATS|CBOE|IEX|TXSE|NYSETEXAS):[0-9A-Z][A-Z0-9.-]{0,23}'
    for entry in _items(raw.get('members'), 256):
        item = _mapping(entry)
        identity = _text(item.get('id'), 48)
        if not re.fullmatch(pattern, identity):
            raise ValueError('선정 종목의 시장과 거래소 코드를 확인하세요.')
        row = {k: _text(item.get(k) or '') for k in ('name', 'symbol', 'currency', 'price_label', 'price_source', 'exchange')}
        venue, ticker = identity.split(':', 1)
        board = row['exchange']
        allowed_board = {'KOSPI': '.KS', 'KOSDAQ': '.KQ'}
        if region == 'KR':
            if board not in allowed_board:
                raise ValueError('국내 종목의 거래소 구분을 확인하세요.')
            expected = ticker + allowed_board[board]
        else:
            if board != ('NYSEAMERICAN' if venue == 'AMEX' else venue):
                raise ValueError('미국 종목의 거래소 구분을 확인하세요.')
            expected = ticker.replace('.', '-')
        if item.get('yahoo') != expected or row['symbol'] != ticker:
            raise ValueError('선정 기록에 저장한 거래소 ID와 가격 심볼이 일치하지 않습니다.')
        row.update(id=identity, yahoo=expected, price=_number(item.get('price')))
        for k in ('price_as_of', 'price_received_at', 'master_at', 'fiscal_date', 'supplement_fiscal_date'):
            row[k] = _date(item.get(k))
        row['metrics'] = {k: _number(v) for k, v in _mapping(item.get('metrics', {})).items() if k in FIELDS}
        row['metric_sources'] = {k: _text(v, 768) for k, v in _mapping(item.get('metric_sources', {})).items() if k in FIELDS}
        members.append(row)
    ids = [row['id'] for row in members]
    if (not members or len(ids) > counts['passed'] or len(set(ids)) != len(ids) or
            (symbols is not None and (not isinstance(symbols, (list, tuple)) or len(ids) != len(symbols) or
                                      any(not isinstance(s, str) for s in symbols) or set(ids) != set(symbols)))):
        raise ValueError('선정 시점에 저장한 종목과 현재 종목 목록이 일치하지 않습니다.')
    return dict(version=1, kind='screener_fixed_basket', market=region, provider=provider,
                selected_at=selected, data_as_of=received, filters=criteria, counts=counts, members=members)
