"""Chart indicators on chronological, normalized OHLCV bars, aligned without backfill."""
from math import fsum


EXTRA_GROUPS = {
    "wma": ("wma",),
    "donchian": ("donchian_upper", "donchian_middle", "donchian_lower"),
    "keltner": ("keltner_upper", "keltner_middle", "keltner_lower"),
    "stochastic": ("stoch_k", "stoch_d"),
    "dmi": ("adx", "di_plus", "di_minus"),
    "cci": ("cci",),
    "williams_r": ("williams_r",),
    "roc": ("roc",),
    "obv": ("obv",),
    "mfi": ("mfi",),
    "cmf": ("cmf",),
}


def ema(values, period):
    """SMA-seeded EMA. Leading None values keep alignment, never backfilled."""
    result, buffer, previous = [None] * len(values), [], None
    alpha = 2 / (period + 1)
    for i, value in enumerate(values):
        if value is None:
            continue
        if previous is None:
            buffer.append(value)
            if len(buffer) == period:
                previous = sum(buffer) / period
                result[i] = previous
        else:
            previous += alpha * (value - previous)
            result[i] = previous
    return result


def _wilder(values, period, start):
    """Seed with the first complete window beginning at start."""
    result = [None] * len(values)
    seed = start + period - 1
    if seed < len(values):
        result[seed] = sum(values[start:seed + 1]) / period
        for i in range(seed + 1, len(values)):
            result[i] = (result[i - 1] * (period - 1) + values[i]) / period
    return result


def _complete_sma(values, period):
    result = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i + 1 - period:i + 1]
        if None not in window:
            result[i] = fsum(window) / period
    return result


def _directional(candles, true_ranges):
    """DMI starts with 14 observed price changes; ADX needs 14 valid DX values."""
    length = len(candles)
    up_dm, down_dm = [0.0] * length, [0.0] * length
    for i in range(1, length):
        up = candles[i]["high"] - candles[i - 1]["high"]
        down = candles[i - 1]["low"] - candles[i]["low"]
        if up > down and up > 0:
            up_dm[i] = up
        if down > up and down > 0:
            down_dm[i] = down
    tr = _wilder(true_ranges, 14, 1)
    plus = _wilder(up_dm, 14, 1)
    minus = _wilder(down_dm, 14, 1)
    dx = [None] * length
    for i in range(14, length):
        plus[i] = 100 * plus[i] / tr[i] if tr[i] else 0.0
        minus[i] = 100 * minus[i] / tr[i] if tr[i] else 0.0
        total = plus[i] + minus[i]
        dx[i] = 100 * abs(plus[i] - minus[i]) / total if total else 0.0
    return {"di_plus": plus, "di_minus": minus, "adx": _wilder(dx, 14, 14)}


def _volume_indicators(candles, typical):
    length = len(candles)
    obv, mfi, cmf = ([None] * length for _ in range(3))
    positive, negative, money_volume = ([None] * length for _ in range(3))
    volumes = [bar.get("volume") for bar in candles]
    for i, bar in enumerate(candles):
        volume = volumes[i]
        if volume is None:
            continue
        # Each contiguous volume segment has its own explicit zero baseline.
        if i == 0 or obv[i - 1] is None:
            obv[i] = 0.0
        else:
            difference = bar["close"] - candles[i - 1]["close"]
            signed_volume = volume if difference > 0 else -volume if difference < 0 else 0.0
            obv[i] = obv[i - 1] + signed_volume
        if i:
            flow = typical[i] * volume
            positive[i] = flow if typical[i] > typical[i - 1] else 0.0
            negative[i] = flow if typical[i] < typical[i - 1] else 0.0
        spread = bar["high"] - bar["low"]
        multiplier = ((bar["close"] - bar["low"]) - (bar["high"] - bar["close"])) / spread if spread else 0.0
        money_volume[i] = max(-1.0, min(1.0, multiplier)) * volume
        if i >= 14:
            pos_window = positive[i - 13:i + 1]
            if None not in pos_window:
                pos_sum = fsum(pos_window)
                total = pos_sum + fsum(negative[i - 13:i + 1])
                if total:
                    mfi[i] = 100 * pos_sum / total
        if i >= 19:
            volume_window = volumes[i - 19:i + 1]
            if None not in volume_window:
                total = fsum(volume_window)
                if total:
                    cmf[i] = fsum(money_volume[i - 19:i + 1]) / total
    return {"obv": obv, "mfi": mfi, "cmf": cmf}


def enrich_chart_indicators(candles):
    """Return the supplementary display series, each with one entry per input bar."""
    close = [bar["close"] for bar in candles]
    high = [bar["high"] for bar in candles]
    low = [bar["low"] for bar in candles]
    length = len(candles)
    typical = [(h + l + c) / 3 for h, l, c in zip(high, low, close)]
    true_ranges = [h - l if i == 0 else max(h, close[i - 1]) - min(l, close[i - 1])
                   for i, (h, l) in enumerate(zip(high, low))]

    result = {key: [None] * length for group in ("wma", "donchian", "keltner", "cci", "williams_r", "roc")
              for key in EXTRA_GROUPS[group]}
    result["keltner_middle"] = ema(close, 20)
    atr10 = _wilder(true_ranges, 10, 0)
    raw_k = [None] * length
    for i in range(length):
        if i >= 12:
            result["roc"][i] = 100 * (close[i] / close[i - 12] - 1)
        if i >= 13:
            highest, lowest = max(high[i - 13:i + 1]), min(low[i - 13:i + 1])
            if highest > lowest:
                raw_k[i] = max(0.0, min(100.0, 100 * (close[i] - lowest) / (highest - lowest)))
                result["williams_r"][i] = raw_k[i] - 100
        if i >= 19:
            start = i - 19
            prices = close[start:i + 1]
            result["wma"][i] = fsum(weight * price for weight, price in enumerate(prices, 1)) / 210
            highest, lowest = max(high[start:i + 1]), min(low[start:i + 1])
            result["donchian_upper"][i] = highest
            result["donchian_middle"][i] = (highest + lowest) / 2
            result["donchian_lower"][i] = lowest
            middle = result["keltner_middle"][i]
            result["keltner_upper"][i] = middle + 2 * atr10[i]
            result["keltner_lower"][i] = middle - 2 * atr10[i]
            tp = typical[start:i + 1]
            mean = fsum(tp) / 20
            deviation = fsum(abs(price - mean) for price in tp) / 20
            result["cci"][i] = (typical[i] - mean) / (0.015 * deviation) if min(tp) != max(tp) and deviation else 0.0

    result["stoch_k"] = _complete_sma(raw_k, 3)
    result["stoch_d"] = _complete_sma(result["stoch_k"], 3)
    result.update(_directional(candles, true_ranges))
    result.update(_volume_indicators(candles, typical))
    return result
