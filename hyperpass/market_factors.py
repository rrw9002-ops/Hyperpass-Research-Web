"""Point-in-time trailing earnings supplied by the student, in listing currency per share."""
from __future__ import annotations

import csv
from datetime import date
import io
import math
import re

from .market_prices import MarketBacktestError

MAX_ROWS = 350_000
MAX_CSV_BYTES = 24 * 1024 * 1024
FIELDS = ('symbol', 'available_date', 'eps')


def validate_fundamentals(market, records):
    if market not in ('US', 'KR') or not isinstance(records, list) or len(records) > MAX_ROWS:
        raise MarketBacktestError('시장과 과거 EPS 표를 확인하세요. 최대 350,000행입니다.')
    cleaned, seen = [], set()
    for n, entry in enumerate(records, start=2):
        if not isinstance(entry, dict) or set(entry) != set(FIELDS):
            raise MarketBacktestError(f'EPS {n}행의 열을 확인하세요: symbol,available_date,eps')
        sym, published, eps = (entry[key] for key in FIELDS)
        sym = sym.strip().upper() if isinstance(sym, str) else ''
        if market == 'KR':
            valid = re.fullmatch(r'[A-Z0-9]{6}\.K[SQ]', sym)
        else:
            valid = re.fullmatch(r'[A-Z]{1,6}(?:[./-][A-Z]{1,2})?', sym)
            sym = sym.replace('.', '-').replace('/', '-')
        if not valid:
            raise MarketBacktestError(f'EPS {n}행의 종목은 선택 시장의 가격 티커여야 합니다. 국내 예: 005930.KS, 미국 예: AAPL.')
        try:
            if not isinstance(published, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', published.strip()):
                raise ValueError()
            published = date.fromisoformat(published.strip()).isoformat()
            if isinstance(eps, bool):
                raise ValueError()
            eps = float(eps)
            if not math.isfinite(eps) or abs(eps) > 1e15:
                raise ValueError()
        except (AttributeError, ValueError, TypeError, OverflowError):
            raise MarketBacktestError(f'EPS {n}행의 공개일(YYYY-MM-DD)과 숫자 EPS를 확인하세요.') from None
        key = sym, published
        if key in seen:
            raise MarketBacktestError(f'EPS {n}행: 같은 종목·공개일이 두 번 들어 있습니다 ({sym}, {published}).')
        seen.add(key)
        cleaned.append({'symbol':sym, 'available_date':published, 'eps':eps})
    return sorted(cleaned, key=lambda row:(row['symbol'], row['available_date']))


def import_fundamentals(market, content):
    if not isinstance(content, str) or not content or len(content.encode('utf-8')) > MAX_CSV_BYTES:
        raise MarketBacktestError('24 MiB 이하의 UTF-8 EPS CSV 파일을 선택하세요.')
    reader = csv.DictReader(io.StringIO(content.removeprefix('\ufeff')), strict=True)
    try:
        if not reader.fieldnames or len(reader.fieldnames) != len(FIELDS) or set(reader.fieldnames) != set(FIELDS):
            raise MarketBacktestError('첫 줄에 symbol,available_date,eps 열이 필요합니다.')
        rows = []
        for row in reader:
            if len(rows) >= MAX_ROWS:
                raise MarketBacktestError('과거 EPS CSV는 최대 350,000행입니다.')
            rows.append(row)
    except csv.Error as exc:
        raise MarketBacktestError('EPS CSV의 따옴표와 열 구분자를 확인하세요.') from exc
    if not rows:
        raise MarketBacktestError('공개일과 TTM EPS가 있는 종목 행을 추가하세요.')
    cleaned = validate_fundamentals(market, rows)
    return {'market':market, 'fundamentals':cleaned, 'row_count':len(cleaned),
            'symbol_count':len({row['symbol'] for row in cleaned})}
