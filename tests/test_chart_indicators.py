import copy
import json
import math
import unittest
from unittest.mock import patch

from hyperpass.chart_indicators import EXTRA_GROUPS, enrich_chart_indicators
from hyperpass.chart_lab import INDICATOR_GROUPS, analyze_chart, indicators, validate_settings


def bars(closes, volume=100):
    return [{"timestamp": 1_600_000_000 + i * 86400, "open": c, "high": c + 1,
             "low": c - 1, "close": c, "volume": volume}
            for i, c in enumerate(closes)]


class DisplayIndicatorTests(unittest.TestCase):
    def test_linear_prices_give_known_trend_momentum_and_channel_values(self):
        candles = bars(range(10, 90))
        result = enrich_chart_indicators(candles)
        self.assertEqual(set(result), {key for keys in EXTRA_GROUPS.values() for key in keys})
        self.assertTrue(all(len(line) == len(candles) for line in result.values()))
        expected = {
            "wma": (19, 10 + 2 * 19 / 3), "donchian_upper": (19, 30),
            "donchian_lower": (19, 9), "donchian_middle": (19, 19.5),
            "keltner_middle": (19, 19.5), "keltner_upper": (19, 23.5), "keltner_lower": (19, 15.5),
            "stoch_k": (15, 100 * 14 / 15), "stoch_d": (17, 100 * 14 / 15),
            "di_plus": (14, 50), "di_minus": (14, 0), "adx": (27, 100),
            "cci": (19, 9.5 / (.015 * 5)), "williams_r": (13, -100 / 15),
            "roc": (12, 120), "mfi": (14, 100), "cmf": (19, 0), "obv": (0, 0),
        }
        for key, (start, value) in expected.items():
            with self.subTest(series=key):
                self.assertTrue(all(point is None for point in result[key][:start]))
                self.assertAlmostEqual(result[key][start], value)
        self.assertEqual(result["obv"][-1], (len(candles) - 1) * 100)

    def test_gaps_and_outside_bars_follow_true_range_and_directional_tie_rules(self):
        candles = bars([100] * 28 + [110, 110])
        # At bar 29 high and low both expand by 1 so neither DM contributes.
        candles[29].update(high=112, low=108)
        r = enrich_chart_indicators(candles)
        tr10 = (2 * 9 + 11) / 10
        tr14 = (2 * 13 + 11) / 14
        self.assertAlmostEqual(r['keltner_upper'][28] - r['keltner_middle'][28], 2 * tr10)
        self.assertAlmostEqual(r['di_plus'][28], 100 * (10 / 14) / tr14)
        self.assertAlmostEqual(r['adx'][28], 100 / 14)
        self.assertAlmostEqual(r['di_plus'][29], 100 * (10 / 14 * 13) / (tr14 * 13 + 4))
        self.assertEqual(r['di_minus'][29], 0)

    def test_volume_and_money_flow_with_missing_zero_and_mixed_direction(self):
        prices = [10 + i % 2 for i in range(50)]
        candles = bars(prices)
        # Typical price equals close. On down days, volume is 200 vs 100 on up days.
        for i, bar in enumerate(candles):
            bar['volume'] = 200 if i % 2 == 0 else 100
        mixed = enrich_chart_indicators(candles)
        self.assertAlmostEqual(mixed['mfi'][14], 100 * 11 * 100 / (11 * 100 + 10 * 200))
        self.assertEqual(mixed['obv'][2], -100)
        # A close at 75% of the high/low range has a CMF multiplier of +0.5.
        for bar in candles:
            bar['low'] = bar['close'] - 3
        candles[16]['volume'] = None
        r = enrich_chart_indicators(candles)
        self.assertIsNone(r['obv'][16])
        self.assertEqual(r['obv'][17], 0)
        self.assertEqual(r['obv'][18], -200)
        self.assertTrue(all(x is None for x in r['mfi'][16:30]))
        self.assertIsNotNone(r['mfi'][30])
        self.assertTrue(all(x is None for x in r['cmf'][19:36]))
        self.assertAlmostEqual(r['cmf'][36], .5)
        for bar in candles:
            bar['volume'] = 0
        r = enrich_chart_indicators(candles)
        self.assertIsNone(r['cmf'][-1]); self.assertIsNone(r['mfi'][-1])
        self.assertEqual(r['obv'][-1], 0)

    def test_flat_prices_and_short_or_volume_free_samples_are_finite_or_null(self):
        candles = bars([10] * 35)
        for bar in candles:
            bar['high'] = bar['low'] = bar['close']
        r = enrich_chart_indicators(candles)
        for key in ('cci','adx','di_plus','di_minus','cmf','roc'):
            self.assertEqual(r[key][-1], 0, key)
        for key in ('stoch_k','stoch_d','williams_r','mfi'):
            self.assertIsNone(r[key][-1], key)
        self.assertEqual(r['keltner_upper'][-1], 10)
        for bar in candles:
            bar['volume'] = None
        r = enrich_chart_indicators(candles)
        for key in ('obv','mfi','cmf'):
            self.assertTrue(all(value is None for value in r[key]))
        for size in (0, 1, 4, len(candles)):
            short = enrich_chart_indicators(candles[:size])
            json.dumps(short, allow_nan=False)
            self.assertTrue(all(len(x) == size for x in short.values()))

    def test_all_bars_are_prefix_invariant_and_input_is_untouched(self):
        candles = bars([120 + 25 * math.sin(i/7) + 4 * math.sin(i/2.2) for i in range(120)])
        candles[34]['volume'] = None
        original = copy.deepcopy(candles)
        full = enrich_chart_indicators(candles)
        for length in (14, 27, 35, 50, 107):
            prefix = enrich_chart_indicators(candles[:length])
            for key in full:
                self.assertEqual(full[key][:length], prefix[key], (key, length))
        self.assertEqual(candles, original)

    def test_default_chart_and_explicit_selection_without_changing_strategy_series(self):
        candles = bars([100 + i % 19 for i in range(100)])
        packet = {'symbol':'TEST', 'records':candles}
        with patch("hyperpass.chart_lab.enrich_chart_indicators", side_effect=AssertionError("chart-only")):
            # The portfolio simulator calls this original function with its own arrays.
            self.assertNotIn('adx', indicators(candles, validate_settings()))
            baseline = analyze_chart(packet, {'indicators':['sma','rsi']})
        default = analyze_chart(packet)
        self.assertEqual(default['backtest'], baseline['backtest'])
        self.assertEqual(set(default['indicators']), {key for keys in INDICATOR_GROUPS.values() for key in keys})
        filtered = analyze_chart(packet, {'strategy':'none','indicators':['dmi','wma']})
        self.assertEqual(set(filtered['indicators']), {'di_plus','di_minus','adx','wma'})
        self.assertEqual(filtered['evidence_summary']['latest_indicators']['adx'], filtered['indicators']['adx'][-1])
