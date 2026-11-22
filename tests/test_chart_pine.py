"""Contract checks for the exporter, not a TradingView compilation claim."""
from datetime import datetime, timezone
import math
import re
import unittest

from hyperpass.chart_pine import build_pine, PineExportError


class PineExportTests(unittest.TestCase):
    def test_analysis_only_emits_no_strategy(self):
        self.assertEqual(build_pine({'strategy': 'none'}), '')

    def test_commission_units_are_converted_and_initial_capital_preserved(self):
        for bps in (0, 1, 5, 12.5, 1000):
            with self.subTest(bps=bps):
                output = build_pine({'strategy': 'trend_breakout', 'fee_bps': bps, 'initial_capital': 123456})
                commission = float(re.search(r'commission_value = ([0-9.e+-]+)', output)[1])
                capital = float(re.search(r'initial_capital = ([0-9.e+-]+)', output)[1])
                self.assertAlmostEqual(commission, bps / 100)
                self.assertEqual(capital, 123456)

    def test_bps_slippage_is_not_silently_presented_as_ticks(self):
        output = build_pine({'strategy': 'mean_reversion', 'slippage_bps': 15})
        self.assertIn('local slippage 15 bps is NOT converted', output)
        self.assertEqual(int(re.search(r'\n     slippage = (\d+)', output)[1]), 1)
        explicit = build_pine({'strategy': 'mean_reversion', 'slippage_mode': 'ticks', 'slippage_ticks': 3})
        self.assertEqual(int(re.search(r'\n     slippage = (\d+)', explicit)[1]), 3)

    def test_calendar_dates_are_exact_utc_instants(self):
        output = build_pine({'strategy': 'trend_breakout', 'start_date': '2024-02-29', 'end_date': '2026-07-03'})
        stamps = [int(v) for v in re.findall(r'input.time\((\d+)', output)]
        days = [datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat() for ms in stamps]
        self.assertEqual(days, ['2024-02-29T00:00:00+00:00', '2026-07-03T00:00:00+00:00'])

    def test_export_rejects_invalid_or_executable_input(self):
        bad = [None, [], {'strategy': ['trend_breakout']}, {'strategy': 'x\nstrategy.entry("X", strategy.short)'},
               {'strategy': 'trend_breakout', 'initial_capital': True},
               {'strategy': 'trend_breakout', 'fee_bps': math.nan},
               {'strategy': 'trend_breakout', 'initial_capital': 10 ** 500},
               {'strategy': 'trend_breakout', 'fast_period': 20.5},
               {'strategy': 'trend_breakout', 'fast_period': 80, 'slow_period': 20},
               {'strategy': 'mean_reversion', 'bb_std': float('inf')},
               {'strategy': 'mean_reversion', 'rsi_entry': 101},
               {'strategy': 'trend_breakout', 'slippage_mode': 'ticks', 'slippage_ticks': 1.5},
               {'strategy': 'trend_breakout', 'slippage_mode': 'unknown'},
               {'strategy': 'trend_breakout', 'start_date': '2024-02-30'},
               {'strategy': 'trend_breakout', 'start_date': '2025-01-01', 'end_date': '2024-01-01'},
               {'strategy': 'trend_breakout', 'start_date': '2024-01-01', 'end_date': '2024-01-01'},
               {'strategy': 'trend_breakout', 'start_date': '2024-1-1'},
               {'strategy': 'trend_breakout', 'start_date': False},
               {'strategy': 'trend_breakout', 'end_date': '2100-01-01'}]
        for settings in bad:
            with self.subTest(settings=settings), self.assertRaises(PineExportError):
                build_pine(settings)

    def test_course_exports_keep_distinct_rules_and_research_boundary(self):
        trend = build_pine({'strategy': 'trend_breakout'})
        mean = build_pine({'strategy': 'mean_reversion'})
        cross = build_pine({'strategy': 'sma_cross'})
        # These are the externally promised rules and safety boundary of the artifact.
        self.assertIn('ta.highest(high, breakoutLength)[1]', trend)
        self.assertIn('close > fastMA and fastMA > slowMA and close > priorHigh', trend)
        self.assertIn('ta.crossunder(close, fastMA)', trend)
        self.assertIn('close < lower and rsiValue < rsiThreshold', mean)
        self.assertIn('ta.crossover(close, basis)', mean)
        self.assertIn('ta.crossover(fastMA, slowMA)', cross)
        for script in (trend, mean, cross):
            self.assertTrue(script.startswith('//@version=6\n'))
            self.assertIn('NOT compiled or executed', script)
            self.assertIn('process_orders_on_close = false', script)
            self.assertIn('immediately = false', script)
            self.assertNotIn('strategy.short', script)
            self.assertNotIn('alert(', script)
            self.assertNotIn('request.security(', script)


if __name__ == '__main__':
    unittest.main()
