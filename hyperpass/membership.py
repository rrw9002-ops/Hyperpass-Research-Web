"""Dated, publicly knowable membership changes for historical portfolio selection."""
from bisect import bisect_right
from collections import defaultdict
import csv
from datetime import date
from io import StringIO
import re

from .market_prices import MarketBacktestError


FIELDS = ('symbol', 'effective_date', 'available_date', 'member')
MAX_EVENTS = 100000


def validate(market, records):
    if market not in ('US', 'KR') or not isinstance(records, list) or not 1 <= len(records) <= MAX_EVENTS:
        raise MarketBacktestError('과거 구성 종목 편입·편출 자료는 1~100,000행이어야 합니다.')
    cleaned, seen = [], set()
    for n, row in enumerate(records, 2):
        if not isinstance(row, dict) or set(row) != set(FIELDS):
            raise MarketBacktestError(f'구성 이력 {n}행의 열을 확인하세요.')
        symbol = str(row['symbol']).strip().upper()
        valid = r'[A-Z0-9]{6}\.K[SQ]' if market == 'KR' else r'[A-Z]{1,6}(?:[.-][A-Z]{1,2})?'
        if not re.fullmatch(valid, symbol):
            raise MarketBacktestError(f'구성 이력 {n}행의 시장과 가격 티커를 확인하세요.')
        if market == 'US':
            symbol = symbol.replace('.', '-')
        dates = {}
        for k in ('effective_date', 'available_date'):
            raw = row[k]
            try:
                if not isinstance(raw, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
                    raise ValueError()
                dates[k] = date.fromisoformat(raw).isoformat()
            except ValueError:
                raise MarketBacktestError(f'구성 이력 {n}행의 {k}는 YYYY-MM-DD 날짜여야 합니다.') from None
        key = symbol, dates['effective_date']
        member = str(row['member']).strip().lower()
        if member not in ('in', 'out') or key in seen:
            raise MarketBacktestError(f'구성 이력 {n}행의 member 값(in/out)과 종목·효력일 중복을 확인하세요.')
        seen.add(key)
        cleaned.append(dict(symbol=symbol, member=member, **dates))
    return sorted(cleaned, key=lambda r:(r['symbol'], r['effective_date']))


def import_csv(market, content):
    if not isinstance(content, str) or len(content.encode('utf-8')) > 6 * 1024 * 1024:
        raise MarketBacktestError('6 MiB 이하 UTF-8 구성 이력 CSV를 선택하세요.')
    reader = csv.DictReader(StringIO(content.removeprefix('\ufeff')), strict=True)
    try:
        if not reader.fieldnames or sorted(reader.fieldnames) != sorted(FIELDS):
            raise MarketBacktestError('필수 열은 symbol,effective_date,available_date,member입니다.')
        rows = []
        for row in reader:
            if len(rows) >= MAX_EVENTS:
                raise MarketBacktestError('구성 이력은 최대 100,000행입니다.')
            rows.append(row)
        return validate(market, rows)
    except csv.Error:
        raise MarketBacktestError('구성 이력 CSV의 따옴표와 구분자를 확인하세요.') from None


class Timeline:
    def __init__(self, events):
        self.days, self.states = [], []
        latest_effective = -1
        for first_known, effective, member in sorted(events):
            if effective <= latest_effective:
                continue
            latest_effective = effective
            if self.days and first_known == self.days[-1]:
                self.states[-1] = member
            else:
                self.days.append(first_known)
                self.states.append(member)

    def active(self, day):
        idx = bisect_right(self.days, day) - 1
        return idx >= 0 and self.states[idx]

    def overlaps(self, start, end):
        return self.active(start) or any(self.states[bisect_right(self.days,start):bisect_right(self.days,end)])


def timelines(rows, start, end):
    events = defaultdict(list)
    for row in rows:
        effective = date.fromisoformat(row['effective_date']).toordinal()
        available = date.fromisoformat(row['available_date']).toordinal()
        events[row['symbol']].append((max(effective, available+1), effective, row['member']=='in'))
    all_series = {s:Timeline(changes) for s,changes in events.items()}
    return {s:t for s,t in all_series.items() if t.overlaps(start.toordinal(), end.toordinal())}
