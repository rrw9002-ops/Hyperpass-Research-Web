"""Bounded Pine v6 text export. This module never executes or compiles Pine.

The two course strategies are daily-bar research examples. A simple SMA-cross
example is also supported, but is not represented as a course strategy.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
import math


class PineExportError(ValueError):
    pass


def _number(settings, key, default, minimum, maximum, integer=False):
    value = settings.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PineExportError(f'{key}: 숫자 설정을 확인하세요.')
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise PineExportError(f'{key}: 허용 범위를 벗어났습니다.') from None
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise PineExportError(f'{key}: 허용 범위를 벗어났습니다.')
    if integer and value != int(value):
        raise PineExportError(f'{key}: 정수를 입력하세요.')
    return int(value) if integer else float(value)


def _day(settings, key, default):
    value = settings.get(key, default)
    if value is None or value == '':
        value = default
    if not isinstance(value, str) or len(value) != 10:
        raise PineExportError(f'{key}: YYYY-MM-DD 날짜를 입력하세요.')
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise PineExportError(f'{key}: 유효한 날짜를 입력하세요.') from None
    if parsed.isoformat() != value or not 1970 <= parsed.year <= 2099:
        raise PineExportError(f'{key}: 1970~2099년 날짜를 입력하세요.')
    return parsed


def _literal(value):
    # Every value reaching this function has been finite/range checked.
    return format(value, '.12g')


def build_pine(settings):
    """Return a self-contained strategy script, or '' for analysis-only mode.

    settings uses Chart Lab's names. Unsupported strings cannot be interpolated
    as executable code. `start_date`/`end_date` are UTC calendar dates. Because
    TradingView slippage is ticks, bps-mode export explicitly uses the course's
    one-tick assumption instead of inventing a price-dependent conversion.
    """
    if not isinstance(settings, dict):
        raise PineExportError('Pine 내보내기 설정 형식을 확인하세요.')
    strategy = settings.get('strategy', 'none')
    if strategy == 'none':
        return ''
    names = {
        'trend_breakout': 'Hyperpass Course - Trend Breakout',
        'mean_reversion': 'Hyperpass Course - BB RSI Mean Reversion',
        'sma_cross': 'Hyperpass Example - SMA Cross',
    }
    if not isinstance(strategy, str) or strategy not in names:
        raise PineExportError('내보낼 수 없는 전략입니다.')

    capital = _number(settings, 'initial_capital', 100000000, 1, 1e15)
    fee_bps = _number(settings, 'fee_bps', 5, 0, 1000)
    fast = _number(settings, 'fast_period', 20, 2, 500, True)
    slow = _number(settings, 'slow_period', 60, 2, 500, True)
    breakout = _number(settings, 'breakout_period', 20, 2, 500, True)
    rsi_period = _number(settings, 'rsi_period', 14, 2, 500, True)
    rsi_entry = _number(settings, 'rsi_entry', 30, 0, 100)
    bb_period = _number(settings, 'bb_period', 20, 2, 500, True)
    bb_std = _number(settings, 'bb_std', 2, 0.1, 10)
    if strategy in ('trend_breakout', 'sma_cross') and fast >= slow:
        raise PineExportError('짧은 이동평균 기간은 긴 기간보다 작아야 합니다.')
    start = _day(settings, 'start_date', '2020-01-01')
    end = _day(settings, 'end_date', '2099-12-31')
    if start >= end:
        raise PineExportError('Pine의 종료일은 시작일보다 뒤여야 합니다.')
    start_ms = int(datetime.combine(start, time.min, tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.combine(end, time.min, tzinfo=timezone.utc).timestamp() * 1000)
    mode = settings.get('slippage_mode', 'bps')
    if mode == 'ticks':
        ticks = _number(settings, 'slippage_ticks', 1, 0, 1000, True)
        slippage_note = f'Pine slippage: {ticks} tick(s). TradingView uses syminfo.mintick; compare it with the local tick_size.'
    elif mode == 'bps':
        bps = _number(settings, 'slippage_bps', 5, 0, 1000)
        ticks = 1
        slippage_note = (f'LOCAL/PINE DIFFERENCE: local slippage {_literal(bps)} bps is NOT converted. '
                         'Pine export uses the course assumption of 1 tick per fill. Compare costs before interpreting results.')
    else:
        raise PineExportError('슬리피지 방식은 bps 또는 ticks입니다.')

    lines = [
        '//@version=6',
        '// Generated research example. NOT compiled or executed by Hyperpass.',
        '// Apply manually to a standard 1D chart, verify the symbol and Strategy Tester settings.',
        '// No broker connection, alert, webhook, or real-order automation is included.',
        '// ' + slippage_note,
        '// Currency defaults to the selected chart currency; no FX conversion is assumed.',
        '// Generated date defaults are UTC. TradingView displays time inputs in the chart timezone.',
        '// End-date liquidation takes priority over new entries; there is no new entry on the liquidation day.',
        '// A close order is submitted at that daily bar close, then filled on the next available tick.',
        '// If no later bar exists, the terminal order may remain unfilled; do not invent a final close.',
        '// This export is a whole-window test, not the local train/holdout or cost-stress comparison.',
        f'strategy("{names[strategy]}", overlay = true, initial_capital = {_literal(capital)},',
        '     default_qty_type = strategy.percent_of_equity, default_qty_value = 100,',
        f'     pyramiding = 0, commission_type = strategy.commission.percent, commission_value = {_literal(fee_bps / 100)},',
        f'     slippage = {ticks}, margin_long = 100, margin_short = 100,',
        '     calc_on_every_tick = false, calc_on_order_fills = false, process_orders_on_close = false, use_bar_magnifier = false)',
        '',
        f'int entryStart = input.time({start_ms}, "Start instant (default UTC date)")',
        f'int terminalDate = input.time({end_ms}, "Liquidation instant (default UTC date)")',
        'if barstate.isfirst',
        '    if not chart.is_standard or not timeframe.isdaily or timeframe.multiplier != 1',
        '        runtime.error("This export requires a standard 1D chart. Confirm the symbol and chart type first.")',
        '    if entryStart >= terminalDate',
        '        runtime.error("The liquidation date must be later than the start date.")',
        '',
    ]
    if strategy in ('trend_breakout', 'sma_cross'):
        lines += [
            f'int fastLength = input.int({fast}, "Fast SMA", minval = 2, maxval = 500)',
            f'int slowLength = input.int({slow}, "Slow SMA", minval = 2, maxval = 500)',
            'float fastMA = ta.sma(close, fastLength)',
            'float slowMA = ta.sma(close, slowLength)',
            'if barstate.isfirst and fastLength >= slowLength',
            '    runtime.error("Fast SMA must be shorter than slow SMA.")',
        ]
        if strategy == 'trend_breakout':
            lines += [
                f'int breakoutLength = input.int({breakout}, "Prior-high lookback", minval = 2, maxval = 500)',
                '// [1] excludes the current bar from the breakout threshold.',
                'float priorHigh = ta.highest(high, breakoutLength)[1]',
                'bool entrySignal = not na(slowMA) and not na(priorHigh) and close > fastMA and fastMA > slowMA and close > priorHigh',
                'bool exitSignal = ta.crossunder(close, fastMA)',
                'plot(priorHigh, "Prior high (current bar excluded)", color = color.new(color.teal, 30))',
            ]
        else:
            lines += [
                'bool entrySignal = ta.crossover(fastMA, slowMA)',
                'bool exitSignal = ta.crossunder(fastMA, slowMA)',
            ]
        lines += ['plot(fastMA, "Fast SMA", color = color.aqua)', 'plot(slowMA, "Slow SMA", color = color.orange)']
    else:
        lines += [
            f'int bandLength = input.int({bb_period}, "Bollinger period", minval = 2, maxval = 500)',
            f'float bandMult = input.float({_literal(bb_std)}, "Bollinger multiplier", minval = 0.1, maxval = 10)',
            f'int rsiLength = input.int({rsi_period}, "RSI period", minval = 2, maxval = 500)',
            f'float rsiThreshold = input.float({_literal(rsi_entry)}, "RSI entry below", minval = 0, maxval = 100)',
            'float basis = ta.sma(close, bandLength)',
            'float deviation = ta.stdev(close, bandLength, true)',
            'float upper = basis + bandMult * deviation',
            'float lower = basis - bandMult * deviation',
            'float rsiValue = ta.rsi(close, rsiLength)',
            'bool entrySignal = not na(lower) and not na(rsiValue) and close < lower and rsiValue < rsiThreshold',
            'bool exitSignal = ta.crossover(close, basis)',
            'plot(basis, "Bollinger basis", color = color.aqua)',
            'plot(upper, "Upper band", color = color.new(color.purple, 20))',
            'plot(lower, "Lower band", color = color.new(color.purple, 20))',
        ]
    lines += [
        '',
        'bool terminalReached = time >= terminalDate',
        'bool entryWindow = time >= entryStart and time < terminalDate',
        'if barstate.isconfirmed',
        '    if strategy.position_size > 0 and (terminalReached or exitSignal)',
        '        strategy.close("Long", comment = terminalReached ? "Window end" : "Rule exit", immediately = false)',
        '    else if strategy.position_size == 0 and entryWindow and entrySignal',
        '        strategy.entry("Long", strategy.long)',
        '',
    ]
    return '\n'.join(lines)
