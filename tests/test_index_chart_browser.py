"""Verify chart research's independent market index and aligned volatility pane."""
from contextlib import ExitStack
from datetime import date, timedelta
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from hyperpass.server import Application, serve


@unittest.skipUnless(os.getenv("HYPERPASS_TEST_BROWSER") == "1", "opt-in Chrome integration")
class MarketIndexBrowserTest(unittest.TestCase):
    def test_candles_atr_crosshair_and_close_only_fallback(self):
        from playwright.sync_api import expect, sync_playwright

        with ExitStack() as stack:
            base = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            app = Application(base/"data", team_dir=base/"team")
            today = date.today()
            start = today - timedelta(days=19)
            bars = [{"timestamp": (start+timedelta(days=i)).isoformat(), "open": 100+i, "high": 102+i,
                     "low": 98+i, "close": 101+i} for i in range(20)]

            def prices(symbol, period, interval):
                if symbol == "005930.KS":
                    from test_chart_lab import packet
                    return dict(packet(range(100, 185)), symbol=symbol, provider="yahoo",
                                currency="KRW", timeframe="1d")
                if symbol != "^KS11":
                    raise ValueError("Yahoo offline")
                return {"symbol": symbol, "source_url": "https://query1.finance.yahoo.com/", "records": bars}

            stack.enter_context(patch.object(app.sources, "chart_history", side_effect=prices))
            saved = app.chart({"source": "yahoo", "symbol": "005930.KS"})
            fred = f"observation_date,NASDAQCOM\n{start},25400\n{today},25500\n".encode()
            stack.enter_context(patch("hyperpass.index_history._read", return_value=fred))
            server = serve(app, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            stack.callback(thread.join)
            stack.callback(server.server_close)
            stack.callback(server.shutdown)
            browser = stack.enter_context(sync_playwright()).chromium.launch(channel="chrome")
            stack.callback(browser.close)
            page = browser.new_page(viewport={"width": 1250, "height": 850})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            page.locator('nav [data-workspace="chart"]').click()
            page.evaluate("(id) => window.HyperpassChart.open(id)", saved["id"])
            expect(page.locator("#chart-title")).to_contain_text("005930")
            price = page.locator("#market-index-curve")
            atr = page.locator("#market-index-atr")
            value = page.locator("#market-index-atr-value")
            expect(atr).to_be_visible()
            expect(value).to_contain_text("4.00 pt")
            # Both panes move the same trading-day cursor.
            atr.press("Home")
            expect(page.locator("#market-index-values")).to_contain_text(start.isoformat())
            expect(value).to_contain_text("14개")
            price.press("End")
            expect(value).to_contain_text(today.isoformat())
            stock_title = page.locator("#chart-title").inner_text()
            page.locator('[data-index-region="us"]').click()
            expect(page.locator("#market-index-info")).to_contain_text("FRED")
            expect(price).to_be_visible()
            expect(atr).to_be_hidden()
            expect(value).to_contain_text("종가만 제공")
            expect(page.locator("#chart-title")).to_have_text(stock_title)
            self.assertEqual(page.evaluate("window.HyperpassChart.lastResult().id"), saved["id"])
            page.set_viewport_size({"width": 375, "height": 812})
            self.assertLessEqual(price.bounding_box()["width"], 375)
            self.assertEqual(errors, [])
