"""Opt-in browser integration through the installed application's HTTP API and SQLite."""
from contextlib import ExitStack
from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from hyperpass.server import Application, serve


class FixtureDesktop:
    def __init__(self, request, backup):
        self.backup = backup

    def start(self):
        self.backup("saved chart text", "NASDAQ:AAPL", "1D", "test-target")

    def execute(self, symbol):
        return {"status": "completed", "chart": {"symbol": symbol, "timeframe": "1D"},
                "report": {"strategy": "Fixture test", "currency": "USD",
                           "metrics": {"net_profit_percent": 8.25, "max_drawdown_percent": 2.5, "total_trades": 5}}}

    def close(self):
        return {"status": "restored", "message": "테스트 Desktop 상태 복원"}


def fake_bars(symbol, start, end, cache=None, **_):
    day = date.fromisoformat(str(start))
    last = date.fromisoformat(str(end))
    data = []
    while day <= last:
        if day.weekday() < 5:
            price = (55000 if symbol == "005930.KS" else 70000) + len(data) * 5
            data.append([day.isoformat(), price, price + 1, price - 1, price, 800, 0])
        day += timedelta(days=1)
    return "KRW", data


@unittest.skipUnless(os.getenv("HYPERPASS_TEST_BROWSER") == "1", "opt-in Chrome integration")
class BacktestConditionsBrowserTest(unittest.TestCase):
    def test_pine_scopes_and_portfolio_conditions(self):
        from playwright.sync_api import expect, sync_playwright

        code = '//@version=6\nstrategy("Browser test")\nstrategy.entry("L", strategy.long)'
        scopes = []

        def pine_universe(mode, market, symbols, filters):
            scopes.append(mode)
            names = symbols if mode != "market" else ["AAPL", "MSFT"]
            return {name: {"name":name, "target_symbol":"NASDAQ:" + name} for name in names}, "Fixture"

        with ExitStack() as stack:
            folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            app = Application(folder / "data", team_dir=folder / "team")
            stack.enter_context(patch("hyperpass.pine_batch.Desktop", FixtureDesktop))
            stack.enter_context(patch("hyperpass.market_prices.pine_universe", side_effect=pine_universe))
            stack.enter_context(patch("hyperpass.market_backtest.resolve_universe",
                                      side_effect=lambda mode, market, symbols, **kwargs: ({s:s for s in symbols}, "Fixture")))
            stack.enter_context(patch("hyperpass.market_backtest.read_prices", side_effect=fake_bars))
            stack.enter_context(patch("hyperpass.symbol_search.search_symbols", return_value={"results":[]}))
            stack.enter_context(patch("hyperpass.market_universe.classification", return_value={
                "as_of":"2025-01-01", "sectors":[{"id":"Finance","label":"금융","industries":[
                {"id":"Major Banks","label":"은행"},{"id":"Insurance","label":"보험"}]}],"by_symbol":{}}))
            server = serve(app, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            stack.callback(thread.join)
            stack.callback(server.server_close)
            stack.callback(server.shutdown)
            pw = stack.enter_context(sync_playwright())
            browser = pw.chromium.launch(channel="chrome")
            stack.callback(browser.close)
            page = browser.new_page(viewport={"width":1440,"height":920}, reduced_motion="reduce")
            errors = []
            page.on("pageerror",lambda error:errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            page.locator('nav [data-workspace="tradingview"]').click()
            get = lambda name:page.locator("#"+name)
            expect(get("bt-engine")).to_have_value("pine")
            expect(get("bt-library")).to_be_hidden()
            get("bt-market").select_option("US")
            get("bt-symbol").fill("AAPL")
            get("tv-code-file").set_input_files({"name":"class.pine","mimeType":"text/plain","buffer":code.encode()})
            expect(get("tv-code")).to_have_value(code)
            get("bt-pine-template").locator("summary").click()
            page.on("dialog",lambda dialog:dialog.accept())
            get("bt-pine-generate").click()
            expect(get("bt-pine-template-feedback")).to_contain_text("USD")
            self.assertIn("currency.USD",get("tv-code").input_value())
            get("tv-code").fill(code)

            for scope in ("single","custom","market"):
                get("bt-scope").select_option(scope)
                if scope=="custom":
                    get("bt-symbols").fill("AAPL, MSFT")
                get("bt-pine-preview").click()
                expect(get("bt-pine-run")).to_be_enabled()
                if scope=="single":
                    get("tv-code").fill(code+"\n// revised")
                    expect(get("bt-pine-run")).to_be_disabled()
                    get("tv-code").fill(code)
                    get("bt-pine-preview").click()
                with page.expect_response(lambda r:r.url.endswith("/api/backtests") and r.request.method=="POST"):
                    get("bt-pine-run").click()
                expect(get("bt-status")).to_have_text("완료",timeout=15000)
                expect(get("bt-batch-rows")).to_contain_text("8.25%")
                self.assertEqual(app.desk.job(app.desk.list_jobs()[0]["id"])["request"]["mode"],scope)
            self.assertEqual(scopes, ["single","custom","market"])
            get("bt-pine-tested-name").fill("확인한 시장 전략")
            get("bt-save-tested-pine").click()
            expect(get("bt-pine-result-feedback")).to_contain_text("저장")
            saved=app.desk.strategies()[0]
            self.assertEqual((saved["definition"]["code"],saved["definition"]["market"],saved["definition"]["mode"]),
                             (code,"US","market"))
            get("bt-saved").select_option(saved["id"]);get("bt-load").click()
            expect(get("tv-code")).to_have_value(code)
            expect(get("bt-scope")).to_have_value("market")

            get("bt-engine").select_option("portfolio")
            get("bt-market").select_option("KR")
            get("bt-example-load").click()
            expect(get("bt-scope")).to_have_value("custom")
            expect(get("bt-eps-count")).to_have_text("2행")
            get("bt-scope-details").locator("summary").click()
            get("bt-exchanges").get_by_label("코스닥").uncheck()
            get("bt-frequency").select_option("annual");get("bt-month").select_option("3")
            get("bt-contribution").fill("100000")
            get("bt-dividends").check()
            rules=json.loads(get("bt-strategy-code").input_value())
            rules["factors"][0]["max"]=18
            get("bt-strategy-code").fill(json.dumps(rules))
            get("bt-code-apply").click()
            get("bt-preview").click()
            expect(get("bt-preview-summary")).to_contain_text("KOSPI")
            with page.expect_response(lambda r:r.url.endswith("/api/backtests") and r.request.method=="POST"):
                get("bt-run").click()
            expect(get("bt-result-title")).to_contain_text("국내 PER 실습")
            expect(get("bt-status")).to_have_text("완료",timeout=15000)
            expect(get("bt-metrics")).to_contain_text("배당 수입")
            get("bt-save-tested").click()
            expect(get("bt-result-feedback")).to_contain_text("내 전략")
            local=next(r["definition"] for r in app.desk.strategies() if r["kind"]=="market")
            self.assertEqual(local["strategy_code"],rules)
            self.assertEqual(local["rebalance"],{"frequency":"annual","month":3})
            self.assertEqual(local["universe"]["exchanges"],["KOSPI"])
            self.assertEqual(local["monthly_contribution"],100000)
            self.assertTrue(local["dividends"])

            page.set_viewport_size({"width":375,"height":850})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
            self.assertEqual(errors, [])
