"""Long-only daily portfolio simulation with one shared cash account, in local currency."""
from __future__ import annotations

import math
import statistics
from array import array
from bisect import bisect_left
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from . import chart_lab, market_rules
from .market_prices import CURRENT_LIST_WARNING, MarketBacktestError, ProviderUnavailable, read_prices, resolve_universe


class BacktestCancelled(MarketBacktestError):
    pass


def validate_request(payload):
    if not isinstance(payload, dict):
        raise MarketBacktestError('전략과 시장 설정을 확인하세요.')
    market = payload.get('market')
    mode = payload.get('mode')
    if market not in ('US','KR') or mode not in ('single','custom','market'):
        raise MarketBacktestError('시장과 검증 범위를 선택하세요.')
    symbols = payload.get('symbols', [])
    if not isinstance(symbols, list) or len(symbols) > 300 or any(not isinstance(s, str) or not s.strip() or len(s) > 80 for s in symbols):
        raise MarketBacktestError('직접 입력할 종목은 최대 300개입니다. 종목명이나 티커를 확인하세요.')
    if mode == 'single' and len(symbols) != 1 or mode == 'custom' and not symbols:
        raise MarketBacktestError('검증할 종목을 입력하세요. 단일 종목 모드는 하나만 입력합니다.')
    max_positions = payload.get('max_positions', 5)
    if type(max_positions) is not int or not 1 <= max_positions <= 100:
        raise MarketBacktestError('최대 보유 종목 수는 1~100 사이 정수여야 합니다.')
    ranking = payload.get('ranking', 'momentum_high')
    lookback = payload.get('lookback', 20)
    if ranking not in ('momentum_high', 'momentum_low') or type(lookback) is not int or not 2 <= lookback <= 252:
        raise MarketBacktestError('후보 우선순위를 선택하고 수익률 비교 기간을 2~252거래일로 설정하세요.')
    raw = payload.get('settings', {})
    if not isinstance(raw, dict):
        raise MarketBacktestError('전략 설정을 확인하세요.')
    # Latest full date across either exchange. Today's incomplete bar is never used.
    latest = datetime.now(timezone.utc).date() - timedelta(days=1)
    default_capital = 100000000 if market == 'KR' else 100000
    try:
        settings = chart_lab.validate_settings({'initial_capital':default_capital, **raw})
        end = date.fromisoformat(settings['end_date']) if settings['end_date'] else latest
        start = date.fromisoformat(settings['start_date']) if settings['start_date'] else end - timedelta(days=364)
    except (ValueError, TypeError, OverflowError) as error:
        raise MarketBacktestError(str(error)) from None
    if end > latest + timedelta(days=1):
        raise MarketBacktestError('미래 날짜로 백테스트할 수 없습니다.')
    end = min(end, latest)
    extended = any(k in payload for k in ('strategy_code', 'rebalance', 'dividends', 'monthly_contribution'))
    years = 15 if extended else 5
    if start >= end or start < date(1980, 1, 1) or (end-start).days > 366 * years:
        raise MarketBacktestError(f'1980년 이후의 기간을 선택하세요. 한 번에 최대 {years}년을 검증합니다.')
    options = {}
    if extended:
        default_code = {'version':1, 'entry':'technical', 'exit':'technical', 'factors':[]}
        code = market_rules.parse_code(payload.get('strategy_code', default_code))
        options.update(strategy_code=code, **market_rules.validate_operations(payload))
    if settings['strategy'] == 'none' and (not extended or code['entry'] == 'technical' or code['exit'] != 'rank_drop'):
        raise MarketBacktestError('기술 신호에 사용할 매수·매도 전략을 선택하세요.')
    if 'universe' in payload:
        from .market_prices import validate_universe
        options['universe'] = validate_universe(market, payload['universe'])
    if 'fundamentals' in payload:
        from .market_factors import validate_fundamentals
        options['fundamentals'] = validate_fundamentals(market, payload['fundamentals'])
    settings['start_date'], settings['end_date'] = start.isoformat(), end.isoformat()
    return {'market':market, 'mode':mode, 'symbols':[] if mode == 'market' else [s.strip() for s in symbols],
            'settings':settings, 'max_positions':1 if mode == 'single' else max_positions,
            'ranking':ranking, 'lookback':lookback, **options}


def _ensure_running(stop):
    if stop is not None and stop.is_set():
        raise BacktestCancelled('백테스트를 취소했습니다.')


def _warmup(settings):
    return {'sma_cross':settings['slow_period'] + 1,
            'trend_breakout':max(settings['slow_period'], settings['breakout_period'] + 1),
            'mean_reversion':max(settings['bb_period'], settings['rsi_period'] + 1)}[settings['strategy']]


@dataclass
class Tape:
    days: array
    opens: array
    closes: array
    entries: list
    exits: list
    missing_warmup: bool
    comparable: bytearray = field(default_factory=bytearray)
    dividends: dict = field(default_factory=dict)
    observed_scores: int = 0
    missing_scores: int = 0
    omitted: tuple = ()

    def index(self, day):
        index = bisect_left(self.days, day)
        return index if index < len(self.days) and self.days[index] == day else None


def _technical(options):
    code = options.get('strategy_code')
    return not code or code['entry'] == 'technical' or code['exit'] in ('technical', 'either')


def _required_bars(options):
    warmup = _warmup(options['settings']) if _technical(options) else 1
    code = options.get('strategy_code')
    momentum = (not code['factors'] or any(f['field'] == 'momentum' for f in code['factors'])) if code else options['mode'] != 'single'
    return max(warmup, options['lookback'] + 1 if momentum else 1)


def _prepare(rows, options, fundamentals=()):
    settings = options['settings']
    start, end = settings['start_date'], settings['end_date']
    code = options.get('strategy_code')
    screener = market_rules.Screener(options, fundamentals) if code else None
    if _technical(options):
        candles = [{'open':r[1], 'high':r[2], 'low':r[3], 'close':r[4], 'volume':None} for r in rows]
        closes = [b['close'] for b in candles]
        if settings['strategy'] == 'mean_reversion':
            series = chart_lab.indicators(candles, settings)
        else:
            series = {'sma_fast':chart_lab.sma(closes, settings['fast_period']),
                      'sma_slow':chart_lab.sma(closes, settings['slow_period'])}
        entries, exits = chart_lab.strategy_signals(candles, series, settings)
    else:
        entries = exits = None
    lookback = options['lookback']
    required = _required_bars(options)
    previous_session = None
    tape = Tape(array('i'), array('d'), array('d'), [], [], False)
    ready = 0
    for i, row in enumerate(rows):
        if not start <= row[0] <= end:
            continue
        ordinal = date.fromisoformat(row[0]).toordinal()
        tape.days.append(ordinal)
        tape.opens.append(row[1])
        tape.closes.append(row[4])
        if screener:
            tape.comparable.append(0)
            decision = market_rules.scheduled(row[0], previous_session, options['rebalance'])
            previous_session = row[0]
            if options['dividends']:
                if len(row) < 7 or not market_rules.finite_number(row[6]) or row[6] < 0:
                    raise MarketBacktestError('배당 자료를 확인할 수 없는 일봉입니다.')
                if row[6]:
                    tape.dividends[ordinal] = row[6]
        if i+1 < required:
            if screener and decision:
                tape.missing_scores += 1
            tape.missing_warmup = True
            continue
        ready += 1
        if screener:
            if decision:
                known, key = screener.score(rows, i)
                tape.comparable[-1] = known
                tape.observed_scores += int(known)
                tape.missing_scores += int(not known)
                if key is not None:
                    tape.entries.append((ordinal, key, bool(entries and entries[i])))
        elif entries[i]:
            score = closes[i]/closes[i-lookback] - 1 if i >= lookback else 0
            tape.entries.append((ordinal, score))
        if exits and exits[i] and (not code or code['exit'] in ('technical', 'either')):
            tape.exits.append(ordinal)
    if ready < 2:
        raise MarketBacktestError(f'지표 준비 {required}봉과 기간 내 평가 일봉 2개가 필요합니다.')
    return tape


def _download_universe(members, options, start, end, cache, report, stop, book=None, fundamentals=None):
    # Keep memory and queued HTTP work bounded even for all US listings.
    tapes, excluded = {}, []
    seen = consecutive_limits = 0
    iterator = iter(members)
    expected_currency = 'KRW' if options['market'] == 'KR' else 'USD'

    def download(symbol):
        _ensure_running(stop)
        need_events = options.get('dividends') or any(f['field'] == 'volume' for f in options.get('strategy_code', {}).get('factors', []))
        if need_events:
            currency, bars = read_prices(symbol, start, end, cache, with_events=True)
        else:
            currency, bars = read_prices(symbol, start, end, cache)
        if currency != expected_currency:
            raise MarketBacktestError(f'가격 통화 {currency} · 시장 기준 {expected_currency}와 다름')
        tape = _prepare(bars, options, (fundamentals or {}).get(symbol, ()))
        tape.omitted = tuple(getattr(bars, 'omitted', ()))
        return tape

    with ThreadPoolExecutor(max_workers=5, thread_name_prefix='market-prices') as pool:
        jobs = {}
        def next_job():
            symbol = next(iterator, None)
            if symbol is not None:
                jobs[pool.submit(download, symbol)] = symbol
        for _ in range(5):
            next_job()
        while jobs:
            _ensure_running(stop)
            finished, _ = wait(jobs, timeout=.5, return_when=FIRST_COMPLETED)
            for future in finished:
                symbol = jobs.pop(future)
                try:
                    tape = future.result()
                    if book:
                        book.add(symbol, tape)
                    tapes[symbol] = tape
                    consecutive_limits = 0
                except BacktestCancelled:
                    raise
                except (chart_lab.ChartLabError, MarketBacktestError) as error:
                    excluded.append({'symbol':symbol, 'name':members[symbol], 'reason':str(error)})
                    consecutive_limits = consecutive_limits + 1 if isinstance(error, ProviderUnavailable) else 0
                    if consecutive_limits >= 12:
                        raise MarketBacktestError('가격 제공자 연결 실패·호출 제한이 12건 연속 발생해 중단했습니다. 확보한 일봉은 캐시에 보관했습니다. 잠시 후 다시 시도하세요.') from None
                seen += 1
                if seen == 1 or seen == len(members) or seen % max(1,len(members)//200) == 0:
                    report(5 + int(75 * seen/len(members)), f'일봉 수집·신호 계산 {seen:,}/{len(members):,}종목 · 사용 가능 {len(tapes):,}개')
                next_job()
    if not tapes:
        reason = excluded[0]['reason'] if excluded else '빈 종목 목록'
        raise MarketBacktestError(f'계산 가능한 종목이 없습니다 ({reason}). 기간과 종목을 확인하세요.')
    if options['mode'] == 'market' and len(tapes) * 2 < len(members):
        raise MarketBacktestError(f'시장 후보 {len(members):,}개 중 {len(tapes):,}개만 검증 가능합니다. 과반의 데이터가 누락되어 시장 결과를 계산하지 않았습니다. 기간·연결을 확인하세요.')
    return tapes, sorted(excluded, key=lambda item:item['symbol'])


def _iso(day):
    return date.fromordinal(day).isoformat()


def _portfolio(tapes, names, sessions, entries, exits, options, stop, multiplier=1, *, leaders=None, orders=None):
    settings = options['settings']
    capital = cash = settings['initial_capital']
    capacity = options['max_positions']
    rate = settings['fee_bps'] * multiplier / 10000
    holdings, pending_exits = {}, {}
    candidates = []
    curve, trades = [], []
    turnover = fees = slippage = exposed = 0.0
    code = options.get('strategy_code')
    contributions = dividend_income = new_cash = 0.0
    previous_equity = nav = peak = capital
    changes = []
    max_dd = 0.0
    dd_days = longest_dd = 0
    for index, day in enumerate(sessions):
        _ensure_running(stop)
        stamp = _iso(day)
        deposit = options.get('monthly_contribution', 0) if index and stamp[:7] != curve[-1]['date'][:7] else 0
        cash += deposit
        new_cash += deposit
        contributions += deposit
        if options.get('dividends'):
            # Ex-date cash approximation: only shares held before today's open are entitled.
            for symbol, pos in holdings.items():
                credit = pos['quantity'] * tapes[symbol].dividends.get(day, 0)
                cash += credit
                pos['dividend_income'] += credit
                dividend_income += credit
                new_cash += credit
        retained = set(holdings) - pending_exits.keys() if code else set()
        for symbol, sig_day in list(pending_exits.items()):
            tape = tapes[symbol]
            i = tape.index(day)
            if i is None:
                continue
            pos = holdings.pop(symbol)
            raw_price = tape.opens[i]
            price = chart_lab._fill(raw_price, 'sell', settings, multiplier)
            notional = price * pos['quantity']
            fee = notional * rate
            slip = (raw_price-price) * pos['quantity']
            cash += notional - fee
            turnover += notional
            fees += fee
            slippage += slip
            net = notional - fee - pos['entry_cost'] + pos.get('dividend_income', 0)
            if orders is not None:
                orders.append({'symbol':symbol, 'side':'sell', 'signal_date':_iso(sig_day), 'date':stamp,
                               'quantity':pos['quantity'], 'price':price, 'fee':fee, 'slippage':slip})
            trades.append({'symbol':symbol, 'name':names[symbol], 'entry_date':pos['entry_date'],
                           'entry_signal_date':pos['entry_signal_date'], 'entry_price':pos['entry_price'],
                           'exit_date':_iso(day), 'exit_signal_date':_iso(sig_day), 'exit_price':price,
                           'quantity':pos['quantity'], 'net_pnl':net, 'return_pct':net/pos['entry_cost']*100,
                           'fees':pos['entry_fee'] + fee, 'slippage':pos['entry_slippage'] + slip})
            if code:
                trades[-1]['dividend_income'] = pos['dividend_income']
                trades[-1]['entry_factors'] = pos['entry_factors']
            del pending_exits[symbol]

        for score, symbol in candidates:
            slots = capacity - len(holdings)
            if not slots:
                break
            if symbol in holdings or cash <= 0:
                continue
            tape = tapes[symbol]
            i = tape.index(day)
            if i is None:
                continue
            raw_price = tape.opens[i]
            price = chart_lab._fill(raw_price, 'buy', settings, multiplier)
            budget = cash/slots
            quantity = budget / (price * (1 + rate))
            fee = quantity * price * rate
            slip = (price-raw_price) * quantity
            holdings[symbol] = {'symbol':symbol, 'name':names[symbol], 'entry_date':_iso(day),
                                'entry_signal_date':_iso(sessions[index-1]), 'entry_price':price,
                                'entry_cost':budget, 'entry_fee':fee, 'entry_slippage':slip,
                                'quantity':quantity,'last_price':raw_price,'last_mark':_iso(day)}
            if code:
                pos = holdings[symbol]
                pos['dividend_income'] = 0.0
                factors = code['factors'] or [{'field':'momentum','order':'desc' if options['ranking'] == 'momentum_high' else 'asc'}]
                pos['entry_factors'] = {f['field']: value if f['order'] == 'asc' else -value for f,value in zip(factors,score)}
                new_cash = max(0.0, new_cash - budget)
            if orders is not None:
                orders.append({'symbol':symbol, 'side':'buy', 'signal_date':_iso(sessions[index-1]), 'date':stamp,
                               'quantity':quantity, 'price':price, 'fee':fee, 'slippage':slip,
                               'factors':holdings[symbol].get('entry_factors', {})})
            cash -= budget
            turnover += price * quantity
            fees += fee
            slippage += slip

        if new_cash > 0 and code and code['entry'] == 'ranked' and len(holdings) == capacity:
            # A full portfolio can deploy new deposits/dividends to retained targets on rebalance.
            topups = [symbol for _, symbol in candidates if symbol in retained and tapes[symbol].index(day) is not None]
            budget = min(new_cash, cash) / len(topups) if topups else 0
            for symbol in topups:
                if budget <= 0:
                    break
                pos, tape = holdings[symbol], tapes[symbol]
                raw_price = tape.opens[tape.index(day)]
                price = chart_lab._fill(raw_price, 'buy', settings, multiplier)
                quantity = budget / (price * (1+rate))
                fee, slip = quantity*price*rate, quantity*(price-raw_price)
                pos['entry_price'] = (pos['entry_price']*pos['quantity'] + price*quantity)/(pos['quantity']+quantity)
                pos['entry_cost'] += budget
                pos['quantity'] += quantity
                pos['entry_fee'] += fee
                pos['entry_slippage'] += slip
                cash -= budget
                new_cash -= budget
                turnover += quantity*price
                fees += fee
                slippage += slip
                if orders is not None:
                    orders.append({'symbol':symbol,'side':'buy','reason':'cash_reinvestment','date':stamp,
                                   'signal_date':_iso(sessions[index-1]),'quantity':quantity,'price':price,'fee':fee,'slippage':slip})
        equity = cash
        held_value = 0.0
        for symbol, pos in holdings.items():
            tape = tapes[symbol]
            i = tape.index(day)
            if i is not None:
                pos['last_price'] = tape.closes[i]
                pos['last_mark'] = _iso(day)
            held_value += pos['quantity'] * pos['last_price']
        equity += held_value
        exposed += held_value / equity
        daily_return = equity/(previous_equity + deposit) - 1
        if index:
            changes.append(daily_return)
        nav = nav*(1+daily_return) if contributions else equity
        previous_equity = equity
        peak = max(peak, nav)
        drawdown = 100 * (nav/peak - 1)
        max_dd = min(max_dd, drawdown)
        dd_days = dd_days + 1 if drawdown < -1e-10 else 0
        longest_dd = max(longest_dd, dd_days)
        curve.append({'date':_iso(day), 'equity':equity, 'drawdown_pct':drawdown})
        if code:
            curve[-1].update(contribution=deposit, return_index=nav/capital*100)
        if leaders is not None and day in leaders:
            for symbol in holdings.keys() - leaders[day]:
                i = tapes[symbol].index(day)
                if i is not None and tapes[symbol].comparable[i]:
                    pending_exits.setdefault(symbol, day)
        for symbol in exits.get(day, ()):
            if symbol in holdings:
                pending_exits.setdefault(symbol, day)
        candidates = entries.get(day, ())
        if code and pending_exits:
            candidates = [item for item in candidates if item[1] not in pending_exits]

    volatility = statistics.stdev(changes) if len(changes) > 1 else None
    winners = [t['net_pnl'] for t in trades if t['net_pnl'] > 0]
    losses = -sum(t['net_pnl'] for t in trades if t['net_pnl'] < 0)
    total = nav/capital - 1
    metrics = {'initial_capital':capital, 'ending_equity':curve[-1]['equity'], 'total_return_pct':100*total,
               'max_drawdown_pct':max_dd, 'longest_drawdown_sessions':longest_dd, 'closed_trades':len(trades),
               'win_rate_pct':100*len(winners)/len(trades) if trades else None,
               'profit_factor':sum(winners)/losses if losses else None,
               'fees':fees,'slippage':slippage,'turnover_pct':100*turnover/capital,
               'annualized_volatility_pct':volatility * math.sqrt(252) * 100 if volatility is not None else None,
               'sharpe':statistics.mean(changes)*math.sqrt(252)/volatility if volatility else None,
               'average_exposure_pct':100*exposed/len(curve), 'sessions':len(curve), 'cash':cash}
    if code:
        metrics.update(contributions=contributions, dividend_income=dividend_income,
                       net_invested=capital+contributions, net_profit=equity-capital-contributions)
        metrics['turnover_pct'] = 100*turnover/(capital+contributions)
    open_positions = [{**p, 'market_value':p['quantity']*p['last_price'],
                       'unrealized_pnl':p['quantity']*p['last_price']-p['entry_cost']} for p in holdings.values()]
    return metrics, trades, open_positions, curve


def _benchmark(options, start, end, dates, cache):
    symbol = '^KS11' if options['market'] == 'KR' else '^GSPC'
    benchmark = {'symbol':symbol, 'name':'KOSPI' if options['market']=='KR' else 'S&P 500',
                 'return_pct':None, 'basis':'평가 첫날 시가 → 마지막 날 종가, 비용·배당 제외 지수'}
    try:
        _, rows = read_prices(symbol, start, end, cache)
        prices = {r[0]:r for r in rows}
        first, last = prices[_iso(dates[0])], prices[_iso(dates[-1])]
        benchmark['return_pct'] = 100 * (last[4]/first[1] - 1)
        if options.get('monthly_contribution'):
            amount = options['monthly_contribution']
            shares = options['settings']['initial_capital']/first[1]
            previous, last_price, nav, deposits = _iso(dates[0]), first[1], 1.0, 0.0
            for day in dates:
                stamp = _iso(day)
                deposit = amount if stamp[:7] != previous[:7] else 0
                if deposit or stamp in prices:
                    row = prices[stamp]
                    opening_equity = shares*last_price + deposit
                    shares += deposit/row[1]
                    nav *= shares*row[4]/opening_equity
                    last_price = row[4]
                    deposits += deposit
                previous = stamp
            benchmark.update(return_pct=100*(nav-1), ending_equity=shares*last[4], contributions=deposits,
                             basis='같은 초기자금과 월 적립금을 지수 시가에 매수한 시간가중 수익률, 비용·배당 제외')

    except (MarketBacktestError, KeyError):
        benchmark['return_pct'] = None
        benchmark['warning'] = '같은 평가 구간의 시작·종료 지수 가격을 구하지 못했습니다.'
    return benchmark


def run_backtest(payload, progress_callback=None, stop_event=None, *, cache_dir=None):
    options = validate_request(payload)
    report = progress_callback or (lambda percent, message: None)
    _ensure_running(stop_event)
    report(1, '대상 종목 목록 확인 중')
    settings = options['settings']
    start, end = date.fromisoformat(settings['start_date']), date.fromisoformat(settings['end_date'])
    code = options.get('strategy_code')
    requires_per = bool(code and any(f['field'] == 'per' for f in code['factors']))
    fundamentals = defaultdict(list)
    for record in options.get('fundamentals', []):
        if record['available_date'] < settings['end_date']:
            fundamentals[record['symbol']].append(record)
    if requires_per and not fundamentals:
        raise MarketBacktestError('PER 조건에는 검증 기간 종료 전 공시된 종목별 EPS 자료가 필요합니다.')
    universe_args = (options['mode'], options['market'], options['symbols'])
    members, source = resolve_universe(*universe_args, universe=options['universe']) if options.get('universe') else resolve_universe(*universe_args)
    if not members:
        raise MarketBacktestError('대상 종목 목록이 비어 있습니다.')
    targets = {s:n for s,n in members.items() if s in fundamentals} if requires_per else members
    if not targets:
        raise MarketBacktestError('선택한 대상과 일치하는 과거 공시 EPS가 없습니다. 종목과 공시일을 확인하세요.')
    warm = _required_bars(options)
    history_start = start - timedelta(days=warm * 2 + 30)
    report(4, f'후보 {len(members):,}종목 · 일봉 준비 중')
    download_args = (targets, options, history_start, end, cache_dir, report, stop_event)
    book = market_rules.RankBook(options) if code else None
    if book:
        tapes, excluded = _download_universe(*download_args, book=book, fundamentals=fundamentals)
    else:
        tapes, excluded = _download_universe(*download_args)
    if requires_per:
        excluded.extend({'symbol':s,'name':members[s],'reason':'기간 종료 전 공시 EPS 없음'} for s in sorted(members.keys() - targets.keys()))
    report(82, '공유 자금으로 시장 신호와 체결 계산 중')
    sessions = set()
    entries, exits = defaultdict(list), defaultdict(list)
    for symbol in sorted(tapes):
        tape = tapes[symbol]
        sessions.update(tape.days)
        for day, score in tape.entries:
            entries[day].append((-score if options['ranking'] == 'momentum_high' else score, symbol))
        for day in tape.exits:
            exits[day].append(symbol)
        tape.entries.clear()
        tape.exits.clear()
    ordered = sorted(sessions)
    for candidates in entries.values():
        candidates.sort()  # signal-date rank and stable alphabetical tie-break
    leaders = None
    orders = [] if book else None
    if book:
        entries, leaders = book.decisions(ordered, options['rebalance'])
        if not any(t.observed_scores for t in tapes.values()) and any(t.missing_scores for t in tapes.values()):
            raise MarketBacktestError('리밸런싱 시점에 관측 가능한 조건값이 없습니다. EPS·거래량·가격 자료와 기간을 확인하세요.')
    metrics, trades, opened, curve = _portfolio(tapes, members, ordered, entries, exits, options, stop_event, leaders=leaders, orders=orders)
    report(91, '거래비용 민감도 및 시간순 검증 계산 중')
    stressed = _portfolio(tapes, members, ordered, entries, exits, options, stop_event, 2, leaders=leaders)[0]
    split = int(len(ordered)*settings['train_fraction'])
    holdout = None
    if split >= 2 and len(ordered) - split >= 2:
        hmetrics = _portfolio(tapes, members, ordered[split:], entries, exits, options, stop_event, leaders=leaders)[0]
        holdout = {'start':_iso(ordered[split]), 'end':_iso(ordered[-1]), 'metrics':hmetrics,
                   'basis':'시간순 후반 구간, 보유 없이 현금에서 재시작. 이전 관측치로 지표만 준비.'}
    report(97, '벤치마크 일봉 및 수집 범위 확인 중')
    _ensure_running(stop_event)
    benchmark = _benchmark(options, start, end, ordered, cache_dir)
    reference = benchmark['return_pct']
    metrics['benchmark_return_pct'] = reference
    metrics['excess_return_pct'] = None if reference is None else metrics['total_return_pct'] - reference
    late = sum(t.missing_warmup for t in tapes.values())
    warnings = ['일봉의 관측 OHLC와 단일 통화로 계산합니다. 배당·세금·시장충격·거래량 제약은 포함하지 않습니다.',
                '가격 없는 날에는 신규 매수를 건너뛰며, 보유 종목은 마지막 종가로 평가합니다. 미청산 포지션은 종료일에 강제 매도하지 않습니다.']
    if options.get('dividends'):
        warnings[0] = '배당은 제공자의 배당락일에 전일 보유 수량만큼 세전 현금으로 적립합니다. 실제 지급일·원천세·시장충격·체결량 제한은 반영하지 않습니다. 벤치마크는 배당 제외 가격 지수입니다.'
    if options.get('monthly_contribution'):
        warnings.append('시작 월 이후 매월 첫 관측 세션 시가 전에 적립합니다. 신규 진입 예산에 사용하며, 순위 전략의 보유 슬롯이 모두 차면 다음 선정 시 유지 종목에도 추가 투자합니다.')
    if requires_per:
        warnings.append('PER은 종가 / 직전까지 공개된 최근 EPS입니다. 공개 당일은 제외하며 공시 후 550일 초과, EPS 공백이나 0은 비교에서 제외합니다. EPS와 주가는 같은 통화·주식분할 기준이어야 합니다.')
    omitted = {s:list(t.omitted) for s,t in tapes.items() if t.omitted}
    if omitted:
        warnings.append(f'가격 범위 오류·결측 등으로 {sum(map(len,omitted.values())):,}개 일봉을 제외했습니다. 종목별 일자는 결과 JSON에 있습니다.')
    if options['mode'] == 'market':
        warnings.insert(0, CURRENT_LIST_WARNING)
    if excluded:
        warnings.append(f'가격 이력·통화·준비 기간 문제로 {len(excluded)}개 종목을 제외했습니다. 제외 사유와 검증된 범위를 확인하세요.')
    if late:
        warnings.append(f'{late}개 종목은 시작일 이후에 지표 준비를 마쳤습니다. 준비가 끝난 날부터 종목 선정을 적용했습니다.')
    if metrics['closed_trades'] < 20:
        warnings.append('완결 거래가 20회 미만으로 승률·손익 통계의 표본이 작습니다.')
    if benchmark.get('warning'):
        warnings.append(benchmark['warning'])
    stale = sum(p['last_mark'] != _iso(ordered[-1]) for p in opened)
    if stale:
        warnings.append(f'미청산 {stale}종목의 최종 가격이 평가 마지막 날보다 오래되었습니다.')
    traded = {t['symbol'] for t in trades} | {p['symbol'] for p in opened}
    coverage = {'requested':len(members),'used':len(tapes),'traded':len(traded),'excluded':excluded,
                'used_symbols':sorted(tapes),
                'status':'partial' if excluded else 'complete','coverage_pct':100*len(tapes)/len(members),
                'source':source, 'as_of':datetime.now(timezone.utc).date().isoformat(), 'market':options['market'],
                'price_source':'Yahoo Finance 일봉 OHLC (비공식 공개 차트)', 'first_session':_iso(ordered[0]),
                'last_session':_iso(ordered[-1]), 'late_warmup':late}
    coverage['omitted_price_bars'] = omitted
    if omitted:
        coverage['status'] = 'partial'
    if code:
        observed = sum(t.observed_scores for t in tapes.values())
        missing = sum(t.missing_scores for t in tapes.values())
        coverage['factor_data'] = {'scored_observations':observed, 'missing_observations':missing,
                                   'symbols_with_comparable_factors':sum(t.observed_scores > 0 for t in tapes.values()),
                                   'as_of_eps_symbols':len(targets) if requires_per else None}
        if missing:
            warnings.append(f'지표 준비·EPS·거래량 등 조건값이 없는 {missing:,}개 종목별 평가 시점은 순위에서 제외했습니다.')
        if not entries or not any(entries.values()):
            warnings.append('선택 기간에 조건을 만족하는 매수 후보가 없었습니다.')
    rank_label = '높은' if options['ranking'] == 'momentum_high' else '낮은'
    result = {'mode':options['mode'], 'market':options['market'], 'settings':settings, 'max_positions':options['max_positions'],
            'ranking':options['ranking'], 'lookback':options['lookback'],
            'metrics':metrics, 'trades':trades, 'open_positions':opened, 'equity_curve':curve, 'coverage':coverage,
            'benchmark':benchmark, 'warnings':warnings, 'cost_stress':{'multiplier':2, 'metrics':stressed},
            'holdout':holdout, 'currency':'KRW' if options['market']=='KR' else 'USD',
            'method':f'당일 종가 신호를 다음 시장 세션 시가에 체결합니다. 직전 {options["lookback"]}거래일 가격수익률이 {rank_label} 순, 동률이면 티커 순으로 매수합니다. 매도 후 남은 현금을 빈 슬롯에 동일 배분하며 소수점 수량을 허용합니다.',
            'risk_basis':'MDD는 종가 평가액 기준입니다. 변동성과 샤프는 일별 수익률, 연 252일, 무위험 금리 0% 가정입니다.'}
    if code:
        result.update(strategy_code=code, rebalance=options['rebalance'], monthly_contribution=options['monthly_contribution'],
                      dividends=options['dividends'], universe=options.get('universe'), orders=orders)
        result['method'] = ('선택한 평가 월의 첫 관측 세션(일별은 매 세션) 종가 기준으로 범위 조건과 정렬을 차례로 적용하며 동률은 티커순입니다. '
                            '선정·매도 신호는 다음 세션 시가에 체결하고, 신규 종목에 남은 현금을 빈 보유 슬롯 수로 나눠 배분합니다. '
                            '순위 이탈은 선정일에 유효한 조건값이 있는 보유 종목에만 판단하며, 기술 매도 신호는 매일 확인합니다. '
                            '선정이 유지된 종목은 기본 보유 수량을 유지합니다.')
        result['risk_basis'] = '수익률·MDD는 외부 적립금을 제외한 종가 시간가중 수익률 기준입니다. 변동성과 샤프는 연 252일, 무위험 금리 0% 가정입니다.'
    return result
