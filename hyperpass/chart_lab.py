"""Deterministic, long-only chart research. No orders, AI calls or network access.

Indicators use past/current OHLC only. Signals formed at close fill at the next
available open. This is a local OHLC simulator, not TradingView Strategy Tester.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone, timedelta

from .chart_indicators import EXTRA_GROUPS, ema, enrich_chart_indicators


INDICATOR_GROUPS = {
    'sma': ('sma_fast', 'sma_slow'),
    'ema': ('ema',),
    'rsi': ('rsi',),
    'macd': ('macd', 'macd_signal', 'macd_histogram'),
    'bollinger': ('bb_upper', 'bb_middle', 'bb_lower'),
    'atr': ('atr',),
    'volume': ('volume',),
    **EXTRA_GROUPS,
}


class ChartLabError(ValueError):
    pass


DEFAULTS = {
    'strategy': 'trend_breakout', 'fast_period': 20, 'slow_period': 60,
    'breakout_period': 20, 'rsi_period': 14, 'rsi_entry': 30,
    'bb_period': 20, 'bb_std': 2, 'ema_period': 20, 'atr_period': 14,
    'initial_capital': 100000000, 'fee_bps': 5, 'slippage_mode': 'bps',
    'slippage_bps': 5, 'slippage_ticks': 1, 'tick_size': None,
    'train_fraction': .7, 'start_date': '', 'end_date': '',
    'indicators': list(INDICATOR_GROUPS),
}
STRATEGIES = {
    'trend_breakout': '추세 돌파 · SMA20/60 + 직전 20봉 고가 돌파',
    'mean_reversion': '평균 회귀 · Bollinger 하단 + RSI',
    'sma_cross': '이동평균 교차 · 단기/장기 SMA',
    'none': '지표 계산만',
}


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ChartLabError(f'{name}은 숫자여야 합니다.')
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ChartLabError(f'{name}은 {low:g}~{high:g} 범위여야 합니다.')
    return value


def _date(value, name):
    if not isinstance(value, str): raise ChartLabError(f'{name}은 YYYY-MM-DD 형식이어야 합니다.')
    if not value: return None
    try:
        parsed = datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        if parsed.strftime('%Y-%m-%d') != value: raise ValueError()
        return parsed
    except ValueError:
        raise ChartLabError(f'{name}은 YYYY-MM-DD 형식이어야 합니다.') from None


def validate_settings(options=None):
    if options is None: options = {}
    if not isinstance(options, dict) or set(options) - set(DEFAULTS):
        raise ChartLabError('지원하지 않는 차트 설정이 포함되어 있습니다.')
    out = dict(DEFAULTS, **options)
    if not isinstance(out['strategy'], str) or out['strategy'] not in STRATEGIES:
        raise ChartLabError('지원하지 않는 백테스트 전략입니다.')
    for name in ('fast_period', 'slow_period', 'breakout_period', 'rsi_period', 'bb_period', 'ema_period', 'atr_period'):
        if type(out[name]) is not int or not 2 <= out[name] <= 300:
            raise ChartLabError(f'{name}은 2~300 사이 정수여야 합니다.')
    if out['fast_period'] >= out['slow_period']:
        raise ChartLabError('단기 이동평균 기간은 장기 기간보다 작아야 합니다.')
    for name, low, high in (('initial_capital', 1, 1e15), ('fee_bps', 0, 1000),
                            ('slippage_bps', 0, 1000), ('slippage_ticks', 0, 100),
                            ('bb_std', .1, 10), ('rsi_entry', 1, 49), ('train_fraction', .5, .9)):
        out[name] = _number(out[name], name, low, high)
    if out['slippage_mode'] not in ('bps', 'ticks'):
        raise ChartLabError('슬리피지는 bps 또는 ticks를 선택하세요.')
    if out['tick_size'] is not None:
        out['tick_size'] = _number(out['tick_size'], 'tick_size', .00000001, 1000000)
    if out['slippage_mode'] == 'ticks' and out['tick_size'] is None:
        raise ChartLabError('틱 슬리피지에는 종목의 가격 단위(tick_size)를 입력해야 합니다.')
    start, end = _date(out['start_date'], '시작일'), _date(out['end_date'], '종료일')
    if start and end and start > end: raise ChartLabError('시작일은 종료일보다 늦을 수 없습니다.')
    allowed = set(DEFAULTS['indicators'])
    if not isinstance(out['indicators'], list) or any(not isinstance(x, str) or x not in allowed for x in out['indicators']):
        raise ChartLabError('차트 지표 선택을 확인하세요.')
    out['indicators'] = list(dict.fromkeys(out['indicators']))
    return out


def _timestamp(value):
    naive = False
    try:
        if isinstance(value, bool): raise ValueError()
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace('.', '', 1).isdigit()):
            stamp = float(value)
            if stamp >= 100000000000: stamp /= 1000
            date = datetime.fromtimestamp(stamp, timezone.utc)
        elif isinstance(value, str):
            date = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
            if date.tzinfo is None:
                naive = True
                date = date.replace(tzinfo=timezone.utc)
            date = date.astimezone(timezone.utc)
        else: raise ValueError()
        if not 1970 <= date.year <= 2200: raise ValueError()
        return date.timestamp(), date.isoformat(), naive
    except (ValueError, TypeError, OverflowError, OSError):
        raise ChartLabError('봉의 시간은 유효한 ISO 날짜·시각 또는 Unix timestamp여야 합니다.') from None


def normalize_candles(packet):
    if not isinstance(packet, dict) or packet.get('error'):
        raise ChartLabError('성공적으로 수집된 OHLCV 자료가 필요합니다.')
    rows = packet.get('records')
    if not isinstance(rows, list) or not 2 <= len(rows) <= 10000:
        raise ChartLabError('차트 계산에는 시간순 OHLCV 이력 2~10,000봉이 필요합니다. 현재가·스크리너는 사용할 수 없습니다.')
    candles, warnings = [], []
    naive_count = missing_volume = 0
    expected = str(packet.get('symbol') or '').upper()
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict): raise ChartLabError('OHLCV 행 형식이 올바르지 않습니다.')
        if row.get('symbol') and expected and str(row['symbol']).upper() != expected:
            raise ChartLabError('서로 다른 종목의 봉이 섞여 있습니다.')
        raw_time = row.get('timestamp', row.get('time', row.get('date')))
        try:
            stamp, label, naive = _timestamp(raw_time)
        except ChartLabError as error:
            raise ChartLabError(f'{row_index+1}번째 봉의 시간 오류: {error}') from None
        location = f'{row_index+1}번째 봉 ({label})'
        naive_count += int(naive)
        if candles and stamp <= candles[-1]['time']:
            raise ChartLabError('봉의 시간이 중복되거나 역순입니다. 원본을 확인하세요. 자동 정렬·중복 제거하지 않았습니다.')
        bar = {'time': stamp, 'timestamp': label}
        for key in ('open', 'high', 'low', 'close'):
            value = row.get(key)
            if isinstance(value, str):
                try: value = float(value)
                except ValueError: pass
            try:
                bar[key] = _number(value, key, 1e-12, 1e15)
            except ChartLabError as error:
                raise ChartLabError(f'{location}: {error} 누락 가격을 보간하거나 0으로 채우지 않았습니다.') from None
        tolerance = bar['high'] * 1e-10
        if bar['low'] > bar['high'] or min(bar['open'], bar['close']) < bar['low'] - tolerance or max(bar['open'], bar['close']) > bar['high'] + tolerance:
            raise ChartLabError(f'{location}: OHLC 가격 범위가 서로 맞지 않습니다. 고가·저가와 시가·종가를 확인하세요.')
        volume = row.get('volume')
        if volume is None or volume == '':
            bar['volume'] = None
            missing_volume += 1
        else:
            if isinstance(volume, str):
                try: volume = float(volume)
                except ValueError: pass
            try:
                bar['volume'] = _number(volume, 'volume', 0, 1e25)
            except ChartLabError as error:
                raise ChartLabError(f'{location}: {error}') from None
        candles.append(bar)
    if naive_count:
        warnings.append('시간대 없는 날짜·시각은 UTC 표기로 정규화했습니다. 거래소 일자·세션과 원본 시간대를 확인하세요.')
    if missing_volume:
        warnings.append(f'{missing_volume}봉의 거래량이 없습니다. 0으로 채우지 않았으며 거래량 기반 판단은 제한됩니다.')
    return candles, warnings


def sma(values, period):
    result = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period: total -= values[i-period]
        if i >= period-1: result[i] = total / period
    return result


def rsi(values, period=14):
    result = [None] * len(values)
    if len(values) <= period: return result
    changes = [values[i] - values[i-1] for i in range(1, len(values))]
    gain = sum(max(0, x) for x in changes[:period]) / period
    loss = sum(max(0, -x) for x in changes[:period]) / period
    for i in range(period, len(values)):
        if i > period:
            change = changes[i-1]
            gain = (gain * (period-1) + max(0, change)) / period
            loss = (loss * (period-1) + max(0, -change)) / period
        result[i] = 50.0 if gain == loss == 0 else 100.0 if loss == 0 else 100 - 100 / (1 + gain/loss)
    return result


def indicators(candles, settings):
    close = [bar['close'] for bar in candles]
    fast, slow = sma(close, settings['fast_period']), sma(close, settings['slow_period'])
    middle = sma(close, settings['bb_period'])
    upper, lower = [None] * len(close), [None] * len(close)
    for i in range(settings['bb_period']-1, len(close)):
        window = close[i-settings['bb_period']+1:i+1]
        deviation = math.sqrt(sum((x-middle[i])**2 for x in window) / len(window)) * settings['bb_std']
        upper[i], lower[i] = middle[i]+deviation, middle[i]-deviation
    ema12, ema26 = ema(close, 12), ema(close, 26)
    macd = [None if a is None or b is None else a-b for a,b in zip(ema12, ema26)]
    signal = ema(macd, 9)
    tr = [bar['high']-bar['low'] if i == 0 else max(bar['high']-bar['low'], abs(bar['high']-close[i-1]), abs(bar['low']-close[i-1])) for i,bar in enumerate(candles)]
    atr = [None] * len(close)
    period = settings['atr_period']
    if len(close) >= period:
        atr[period-1] = sum(tr[:period]) / period
        for i in range(period, len(close)): atr[i] = (atr[i-1]*(period-1)+tr[i]) / period
    return {'sma_fast':fast, 'sma_slow':slow, 'ema':ema(close,settings['ema_period']),
            'rsi':rsi(close,settings['rsi_period']), 'macd':macd, 'macd_signal':signal,
            'macd_histogram':[None if a is None or b is None else a-b for a,b in zip(macd,signal)],
            'bb_upper':upper, 'bb_middle':middle, 'bb_lower':lower, 'atr':atr,
            'volume':[bar['volume'] for bar in candles]}


def strategy_signals(candles, series, settings):
    entries, exits = [False]*len(candles), [False]*len(candles)
    strategy = settings['strategy']
    for i in range(1, len(candles)):
        close, previous = candles[i]['close'], candles[i-1]['close']
        fast, prev_fast = series['sma_fast'][i], series['sma_fast'][i-1]
        slow, prev_slow = series['sma_slow'][i], series['sma_slow'][i-1]
        if strategy == 'trend_breakout':
            period = settings['breakout_period']
            if fast is not None and slow is not None and i >= period:
                entries[i] = close > fast > slow and close > max(bar['high'] for bar in candles[i-period:i])
            if fast is not None and prev_fast is not None:
                exits[i] = close < fast and previous >= prev_fast
        elif strategy == 'mean_reversion':
            mid, prev_mid = series['bb_middle'][i], series['bb_middle'][i-1]
            lower, oscillator = series['bb_lower'][i], series['rsi'][i]
            if lower is not None and oscillator is not None: entries[i] = close < lower and oscillator < settings['rsi_entry']
            if mid is not None and prev_mid is not None: exits[i] = close > mid and previous <= prev_mid
        elif strategy == 'sma_cross' and all(x is not None for x in (fast, prev_fast, slow, prev_slow)):
            entries[i] = fast > slow and prev_fast <= prev_slow
            exits[i] = fast < slow and prev_fast >= prev_slow
    return entries, exits


def _fill(price, side, settings, cost_multiplier=1):
    slip = (price * settings['slippage_bps']/10000 if settings['slippage_mode'] == 'bps'
            else settings['slippage_ticks'] * settings['tick_size']) * cost_multiplier
    result = price + slip if side == 'buy' else price - slip
    if result <= 0: raise ChartLabError('슬리피지 가정이 가격보다 큽니다. 비용 설정을 확인하세요.')
    return result


def _simulate(candles, entries, exits, settings, start, end, cost_multiplier=1):
    capital = cash = settings['initial_capital']
    quantity, pending, opened = 0.0, None, None
    trades, orders, curve = [], [], []
    fees = turnover = exposed = 0.0
    peak, max_drawdown = capital, 0.0
    end_date = _date(settings['end_date'], '종료일')
    end_stamp = (end_date + timedelta(days=1)).timestamp() if end_date else math.inf
    rate = settings['fee_bps']/10000 * cost_multiplier
    for i in range(start, end+1):
        bar = candles[i]
        window_closed = bar['time'] >= end_stamp
        if window_closed:
            pending = ('sell', i-1, 'end_date') if quantity else None
        if pending:
            side, signal_index, reason = pending
            fill = _fill(bar['open'], side, settings, cost_multiplier)
            if side == 'buy' and not quantity:
                quantity = cash / (fill * (1+rate))
                notional = quantity * fill
                fee = notional * rate
                cash -= notional + fee
                opened = {'entry_time':bar['timestamp'], 'entry_index':i,
                          'entry_signal_time':candles[signal_index]['timestamp'], 'entry_price':fill,
                          'quantity':quantity, 'entry_fee':fee, 'invested':notional+fee}
            elif side == 'sell' and quantity:
                notional = quantity * fill
                fee = notional * rate
                proceeds = notional - fee
                cash += proceeds
                pnl = proceeds - opened['invested']
                trades.append({**opened, 'exit_time':bar['timestamp'], 'exit_index':i,
                               'exit_signal_time':candles[signal_index]['timestamp'], 'exit_price':fill,
                               'exit_fee':fee, 'fees':opened['entry_fee']+fee, 'pnl':pnl,
                               'return_pct':100*pnl/opened['invested'], 'exit_reason':reason})
                quantity = 0.0
                opened = None
            else:
                raise ChartLabError('백테스트 포지션 상태가 일치하지 않습니다.')
            fees += fee
            turnover += notional
            orders.append({'side':side, 'time':bar['time'], 'timestamp':bar['timestamp'],
                           'signal_index':signal_index, 'execution_index':i, 'price':fill,
                           'fee':fee, 'notional':notional, 'reason':reason})
            pending = None
        equity = cash + quantity * bar['close']
        peak = max(peak, equity)
        drawdown = 100*(equity/peak-1)
        max_drawdown = min(max_drawdown, drawdown)
        exposed += bool(quantity)
        curve.append({'time':bar['time'], 'timestamp':bar['timestamp'], 'equity':equity, 'drawdown_pct':drawdown})
        if not window_closed:
            if quantity and exits[i]: pending = ('sell', i, 'signal')
            elif not quantity and entries[i]: pending = ('buy', i, 'signal')
    final = curve[-1]['equity']
    profits = sum(max(0, trade['pnl']) for trade in trades)
    losses = sum(max(0, -trade['pnl']) for trade in trades)
    benchmark_fill = _fill(candles[start]['open'], 'buy', settings, cost_multiplier)
    benchmark_quantity = capital/(benchmark_fill*(1+rate))
    benchmark_final = benchmark_quantity * candles[end]['close']
    metrics = {'initial_capital':capital, 'final_equity':final, 'total_return_pct':100*(final/capital-1),
               'max_drawdown_pct':max_drawdown, 'closed_trades':len(trades),
               'winning_trades':sum(trade['pnl'] > 0 for trade in trades),
               'win_rate_pct':100*sum(trade['pnl'] > 0 for trade in trades)/len(trades) if trades else None,
               'profit_factor':profits/losses if losses else None,
               'fees_paid':fees, 'turnover_multiple':turnover/capital,
               'exposure_pct':100*exposed/len(curve),
               'buy_hold_return_pct':100*(benchmark_final/capital-1),
               'buy_hold_assumption':'같은 평가 구간 첫 시가에 비용을 반영해 진입, 마지막 종가로 미청산 평가',
               'bars':len(curve), 'from':candles[start]['timestamp'], 'to':candles[end]['timestamp'],
               'unrealized_pnl':quantity*candles[end]['close']-opened['invested'] if opened else 0.0}
    return {'metrics':metrics, 'trades':trades, 'orders':orders, 'equity':curve,
            'open_position':{**opened,'mark_price':candles[end]['close'],'market_value':quantity*candles[end]['close']} if opened else None,
            'unexecuted_last_signal':{'side':pending[0], 'timestamp':candles[pending[1]]['timestamp']} if pending else None}


def _backtest(candles, series, settings):
    strategy = settings['strategy']
    if strategy == 'none': return None
    warmup = max(settings['slow_period'], settings['breakout_period']) if strategy == 'trend_breakout' else max(settings['bb_period'], settings['rsi_period']+1) if strategy == 'mean_reversion' else settings['slow_period']+1
    start_date, end_date = _date(settings['start_date'], '시작일'), _date(settings['end_date'], '종료일')
    start_stamp = start_date.timestamp() if start_date else -math.inf
    end_stamp = (end_date+timedelta(days=1)).timestamp() if end_date else math.inf
    first = next((i for i,bar in enumerate(candles) if bar['time'] >= start_stamp), len(candles))
    start = max(warmup-1, first)
    end = next((i for i,bar in enumerate(candles) if bar['time'] >= end_stamp), len(candles)-1)
    if start >= end or candles[start]['time'] >= end_stamp:
        raise ChartLabError(f'선택한 전략·기간에는 지표 준비용 과거 {warmup}봉과 이후 평가 봉이 필요합니다. 기간을 늘리거나 차트 지표만 선택하세요.')
    entries, exits = strategy_signals(candles, series, settings)
    full = _simulate(candles, entries, exits, settings, start, end)
    split = start + int((end-start+1)*settings['train_fraction'])
    sufficient = split-start >= 2 and end-split+1 >= 2
    training = _simulate(candles, entries, exits, settings, start, split-1) if sufficient else None
    heldout = _simulate(candles, entries, exits, settings, split, end) if sufficient else None
    stress = _simulate(candles, entries, exits, settings, start, end, 2)
    return {'strategy':strategy, 'label':STRATEGIES[strategy], **full, 'full_sample':full,
            'in_sample':training, 'out_of_sample':heldout, 'split_index':split if sufficient else None,
            'split_time':candles[split]['timestamp'] if sufficient else None,
            'cost_stress':{'multiplier':2, 'metrics':stress['metrics']},
            'assumptions':{'engine':'local-ohlc-v1', 'execution':'종가 신호 → 다음 관측 봉 시가에 비용 반영',
                           'direction':'long-only', 'position_size':'현금 전액, 수수료 포함, 소수점 수량 허용',
                           'pyramiding':False, 'leverage':1, 'fee_bps_per_order':settings['fee_bps'],
                           'slippage_mode':settings['slippage_mode'], 'slippage_bps':settings['slippage_bps'],
                           'slippage_ticks':settings['slippage_ticks'], 'tick_size':settings['tick_size'],
                           'end_date_exit':'종료일 다음날 이후 첫 관측 시가에서 달력 청산; 마지막 봉 종가 강제 청산 없음',
                           'mark_to_market':'미청산 포지션은 마지막 종가 평가, 가상 청산 비용 제외',
                           'drawdown':'관측 봉의 종가 평가액 기준; 봉 내부의 최대 하락은 포함하지 않음',
                           'capital_currency':'시세와 같은 통화의 가상 자본; 환율 환산 없음',
                           'split':'시간순 고정 비율 분리; 후반은 현금에서 새로 시작. 지표만 이전 봉으로 준비',
                           'parameter_selection':'자동 최적화 없음. 반복 설정 변경 후 후반 성과를 보면 진정한 미관측 검증이 아님',
                           'reference':'https://www.tradingview.com/pine-script-docs/concepts/strategies/'}}


def analyze_chart(packet, options=None):
    settings = validate_settings(options)
    candles, warnings = normalize_candles(packet)
    series = indicators(candles, settings)
    backtest = _backtest(candles, series, settings)
    if any(group in EXTRA_GROUPS for group in settings['indicators']):
        series.update(enrich_chart_indicators(candles))
    selected = {key: series[key] for group in settings['indicators'] for key in INDICATOR_GROUPS[group]}
    warnings.extend([
        '입력 OHLCV로 계산한 연구 결과입니다. TradingView Strategy Tester의 실행 결과와 동일하다고 표시하지 않습니다.',
        '가격 조정·배당·분할·상장폐지·거래정지·호가 잔량·체결 가능성을 완전히 재현하지 않습니다.',
        '최근 봉의 확정 여부와 일반 캔들인지 원본에서 확인하세요. Heikin Ashi·Renko 등의 합성 가격은 체결 가능한 가격이 아닐 수 있습니다.',
        'EMA는 기간 SMA로 초기화하고 RSI/ATR는 Wilder 방식으로 계산합니다. 초기 봉과 로드 범위 차이로 원본 차트와 값이 다를 수 있습니다.',
    ])
    requested_start, requested_end = _date(settings['start_date'], '시작일'), _date(settings['end_date'], '종료일')
    first_date = datetime.fromtimestamp(candles[0]['time'], timezone.utc).date()
    last_date = datetime.fromtimestamp(candles[-1]['time'], timezone.utc).date()
    if requested_start and requested_start.date() < first_date:
        warnings.append('요청 시작일보다 수집 이력이 늦게 시작합니다. 요청 기간 전체를 검증한 결과가 아니며 실제 평가 시작일을 확인하세요.')
    if requested_end and requested_end.date() > last_date:
        warnings.append('수집 이력이 요청 종료일에 도달하지 않았습니다. 요청 기간 전체의 성과·종료일 청산 결과가 아닙니다.')
    if packet.get('warning'): warnings.append(str(packet['warning'])[:2000])
    if settings['slippage_mode'] == 'ticks':
        warnings.append('고정 tick_size 가정입니다. 가격대·시장·시점에 따라 호가 단위가 바뀌는 종목은 실제 체결 비용과 다릅니다.')
    if backtest:
        warnings.append('지표 준비에 필요한 초기 봉은 성과 평가에서 제외됩니다. 전체 시세 기간과 백테스트의 from/to는 다를 수 있습니다.')
        if backtest['metrics']['bars'] < 252: warnings.append('평가 봉이 252개 미만입니다. 짧은 표본·국면 편중으로 성과 일반화가 어렵습니다.')
        if backtest['metrics']['closed_trades'] < 20: warnings.append('완결 거래가 20회 미만입니다. 승률·손익비를 안정된 전략 성과로 해석하지 마세요.')
        if not backtest['out_of_sample']: warnings.append('후반 검증 구간이 너무 짧아 분리 성과를 계산하지 않았습니다.')
        if backtest['open_position']: warnings.append('종료 시 미청산 포지션이 있습니다. 총수익률은 마지막 종가 평가를 포함하며 완결 거래의 실현 손익과 다릅니다.')
        warnings.append('시간순 분할과 비용 2배 검사는 일부 검증일 뿐입니다. 파라미터·시장·국면 검증과 실제 모의 운용은 별도로 필요합니다.')
    provenance = {key:packet.get(key,'unknown') for key in ('provider','symbol','as_of','retrieved_at','source_url','currency','timeframe')}
    provenance.update({'bars':len(candles), 'first_time':candles[0]['timestamp'], 'last_time':candles[-1]['timestamp'],
                       'ohlcv_sha256':hashlib.sha256(json.dumps(candles,sort_keys=True,separators=(',',':')).encode()).hexdigest()})
    latest = {key:values[-1] for key,values in series.items()}
    summary = {'type':'computed_chart_research', 'evidence_class':'derived-from-provided-ohlcv',
               'provenance':provenance, 'settings':settings, 'latest_bar':candles[-1], 'latest_indicators':latest,
               'backtest_metrics':backtest['metrics'] if backtest else None,
               'out_of_sample_metrics':backtest['out_of_sample']['metrics'] if backtest and backtest['out_of_sample'] else None,
               'cost_stress_metrics':backtest['cost_stress']['metrics'] if backtest else None,
               'assumptions':backtest['assumptions'] if backtest else {}, 'warnings':warnings,
               'research_decision':'keep researching; 계산 결과만으로 매매 승인·미래 성과·통계적 유의성을 주장하지 마세요.'}
    return {'symbol':packet.get('symbol','unknown'), 'provider':packet.get('provider','unknown'),
            'timeframe':packet.get('timeframe','unknown'), 'provenance':provenance, 'candles':candles,
            'indicators':selected, 'settings':settings, 'backtest':backtest,
            'warnings':warnings, 'evidence_summary':summary}

def market_index(sources, symbol, cache_dir=None):
    from .index_history import get_index
    return get_index(sources, symbol, cache_dir)
