"""Historical attachment calculations use the original chart and its capture time."""
from pathlib import Path
import unittest

from hyperpass.chart_lab import analyze_chart
from hyperpass.chart_overlay import overlay_snapshot
from test_chart_lab import packet


def snapshot(prices, code, observed):
    chart = analyze_chart(packet(prices), {"strategy": "none"})
    chart["created_at"] = observed
    request = {"name": "확정 시차 검증", "code": code, "ohlcv_sha256": chart["provenance"]["ohlcv_sha256"]}
    return overlay_snapshot(chart, request)


class OverlayCalculationTests(unittest.TestCase):
    def test_recent_last_bar_does_not_confirm_a_pivot_early(self):
        module = (Path(__file__).resolve().parents[1]/"static"/"local-indicators.js").read_text(encoding="utf8")
        example = module.split("const pivotCode = `")[1].split("`")[0].replace("pivotBars = input.int(5,", "pivotBars = input.int(1,")
        values = [10, 11, 20, 12]
        provisional = snapshot(values, example, "2020-01-04T12:00:00+00:00")
        self.assertFalse(provisional["summary"]["latest_bar_confirmed"])
        self.assertEqual(provisional["summary"]["recent_pivots"], [])
        closed = snapshot(values, example, "2020-01-06T00:00:00+00:00")
        point = closed["summary"]["recent_pivots"][0]
        self.assertEqual((point["pivot_time"][:10], point["confirmation_bar_time"][:10]), ("2020-01-03","2020-01-04"))
        self.assertEqual(closed["display"]["points"][0]["high"], 21)

    def test_nested_plot_warmup_and_ema_seed(self):
        code = ('indicator("테스트", overlay=true)\nn=input.int(2)\n'
                'plot(ta.lowest(ta.sma(close,n),n), color=color.blue)\nplot(ta.ema(close,n), "EMA")')
        stored = snapshot([10,20,30,40], code, "2020-01-06T00:00:00+00:00")
        self.assertEqual(stored["display"]["lines"][0]["values"], [None,None,15,25])
        ema = stored["display"]["lines"][1]
        self.assertEqual(ema["values"][0], 10)
        self.assertAlmostEqual(ema["values"][1], 10+20/3)
