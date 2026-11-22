"""Validated declarative screening and ranking rules, evaluated at observed closes."""
from bisect import bisect_left, insort
from datetime import date
import json
import math

from .market_prices import MarketBacktestError


FIELDS = ('per', 'momentum', 'close', 'volume')


def finite_number(value):
    return type(value) in (float, int) and -1e300 <= value <= 1e300 and math.isfinite(value)


def parse_code(code):
    if isinstance(code, str):
        try:
            if len(code) > 16000:
                raise ValueError()
            code = json.loads(code)
        except (ValueError, RecursionError):
            raise MarketBacktestError('전략 코드를 JSON 형식으로 입력하세요.') from None
    if not isinstance(code, dict) or set(code) != {'version', 'entry', 'exit', 'factors'}:
        raise MarketBacktestError('전략 코드에는 version, entry, exit, factors가 필요합니다.')
    if type(code['version']) is not int or code['version'] != 1:
        raise MarketBacktestError('전략 코드 version은 1을 사용하세요.')
    if code['entry'] not in ('ranked', 'technical') or code['exit'] not in ('rank_drop', 'technical', 'either'):
        raise MarketBacktestError('전략 코드의 매수·매도 규칙을 확인하세요.')
    if not isinstance(code['factors'], list) or len(code['factors']) > len(FIELDS):
        raise MarketBacktestError('매수 조건은 서로 다른 네 가지 이내로 지정하세요.')
    factors, seen = [], set()
    for factor in code['factors']:
        if not isinstance(factor, dict) or set(factor) - {'field', 'order', 'min', 'max'}:
            raise MarketBacktestError('매수 조건의 필드와 범위를 확인하세요.')
        field, order = factor.get('field'), factor.get('order')
        if field not in FIELDS or field in seen or order not in ('asc', 'desc'):
            raise MarketBacktestError('각 조건에 서로 다른 지표와 정렬 방향 asc 또는 desc를 지정하세요.')
        seen.add(field)
        item = {'field': field, 'order': order}
        for key in ('min', 'max'):
            value = factor.get(key)
            if value is not None:
                if not finite_number(value):
                    raise MarketBacktestError('지표 범위는 유한한 숫자로 입력하세요.')
                item[key] = value
        if 'min' in item and 'max' in item and item['min'] > item['max']:
            raise MarketBacktestError('매수 조건의 최솟값이 최댓값보다 큽니다.')
        factors.append(item)
    return {'version': 1, 'entry': code['entry'], 'exit': code['exit'], 'factors': factors}


def validate_operations(payload):
    schedule = payload.get('rebalance', {'frequency': 'daily'})
    if not isinstance(schedule, dict) or set(schedule) - {'frequency', 'month'}:
        raise MarketBacktestError('리밸런싱 주기와 기준 월을 확인하세요.')
    frequency, month = schedule.get('frequency'), schedule.get('month', 1)
    if frequency not in ('daily', 'monthly', 'quarterly', 'annual') or type(month) is not int or not 1 <= month <= 12:
        raise MarketBacktestError('리밸런싱 주기와 1~12월 사이의 기준 월을 지정하세요.')
    amount = payload.get('monthly_contribution', 0)
    if not finite_number(amount) or not 0 <= amount <= 1e15:
        raise MarketBacktestError('월 적립금은 0~10¹⁵ 사이의 금액을 입력하세요.')
    dividends = payload.get('dividends', False)
    if type(dividends) is not bool:
        raise MarketBacktestError('배당 반영 여부를 선택하세요.')
    return {'rebalance': {'frequency': frequency, 'month': month},
            'monthly_contribution': amount, 'dividends': dividends}


def scheduled(day, previous_day, rule):
    frequency = rule['frequency']
    if frequency == 'daily':
        return True
    if previous_day and day[:7] == previous_day[:7]:
        return False
    month = int(day[5:7])
    if frequency == 'monthly':
        return True
    return (month - rule['month']) % (3 if frequency == 'quarterly' else 12) == 0


class Screener:
    def __init__(self, options, fundamentals):
        code = options['strategy_code']
        self.lookback = options['lookback']
        self.rules = code['factors'] or [{'field':'momentum', 'order':'desc' if options['ranking'] == 'momentum_high' else 'asc'}]
        self.dates = [row['available_date'] for row in fundamentals]
        self.public_days = [date.fromisoformat(d).toordinal() for d in self.dates]
        self.eps = [row['eps'] for row in fundamentals]

    def score(self, rows, index):
        """Return (comparable, rank key). Missing factors and an out-of-range value differ."""
        row = rows[index]
        key = []
        eligible = True
        for factor in self.rules:
            field = factor['field']
            if field == 'per':
                # Publication at an unknown time becomes usable on a later session.
                at = bisect_left(self.dates, row[0]) - 1
                recent = at >= 0 and date.fromisoformat(row[0]).toordinal() - self.public_days[at] <= 550
                value = row[4] / self.eps[at] if recent and self.eps[at] != 0 else None
            elif field == 'volume':
                value = row[5] if len(row) > 5 else None
            elif field == 'close':
                value = row[4]
            else:
                value = (row[4] / rows[index-self.lookback][4] - 1) * 100 if index >= self.lookback else None
            if value is None or not math.isfinite(value):
                return False, None
            if ('min' in factor and value < factor['min']) or ('max' in factor and value > factor['max']):
                eligible = False
            key.append(value if factor['order'] == 'asc' else -value)
        return True, tuple(key) if eligible else None


class RankBook:
    """Keep the N ranked targets, and N entry signals, per decision date for all tickers."""
    def __init__(self, options):
        self.capacity = options['max_positions']
        self.entries, self.leaders = {}, {}
        self.tech_entry = options['strategy_code']['entry'] == 'technical'
        self.rank_exit = options['strategy_code']['exit'] in ('rank_drop', 'either')

    def _insert(self, group, day, key, symbol):
        top = group.setdefault(day, [])
        item = (key, symbol)
        if len(top) >= self.capacity and item >= top[-1]:
            return
        insort(top, item)
        if len(top) > self.capacity:
            top.pop()

    def add(self, symbol, tape):
        for day, key, triggered in tape.entries:
            if self.rank_exit:
                self._insert(self.leaders, day, key, symbol)
            if triggered or not self.tech_entry:
                self._insert(self.entries, day, key, symbol)
        tape.entries.clear()

    def decisions(self, sessions, rule):
        prior = None
        entries, leaders = {}, {}
        for day in sessions:
            stamp = date.fromordinal(day).isoformat()
            if scheduled(stamp, prior, rule):
                targets = self.leaders.get(day, [])
                if self.rank_exit:
                    leaders[day] = {symbol for _, symbol in targets}
                picks = self.entries.get(day, [])
                if self.rank_exit:
                    picks = [item for item in picks if item[1] in leaders[day]]
                entries[day] = picks
            prior = stamp
        return entries, leaders
