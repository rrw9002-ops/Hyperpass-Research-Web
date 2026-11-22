"""Opt-in browser integration checks. Set HYPERPASS_TEST_BROWSER=1 with Chrome and Playwright installed."""
from contextlib import ExitStack
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from hyperpass.server import Application, serve


@unittest.skipUnless(os.getenv("HYPERPASS_TEST_BROWSER") == "1", "opt-in Chrome integration")
class ChartStudioBrowserTest(unittest.TestCase):
    def test_indicator_and_strategy_workflows(self):
        from playwright.sync_api import expect, sync_playwright

        with ExitStack() as stack:
            root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            app = Application(root / "data", team_dir=root / "team")
            old = app.indicators.save({
                "name": "저장한 평균", "code": '//@version=6\nindicator("old")\nplot(ta.sma(close, 30))'
            })
            desktop = FixtureDesktop()
            for method in ("status", "configure_chart", "run_indicator", "run_strategy"):
                stack.enter_context(patch("hyperpass.tradingview_control." + method, getattr(desktop, method)))
            stack.enter_context(patch("hyperpass.symbol_search.search_symbols", return_value={"results": []}))
            # These controls also start automatic chart previews. Keep the indicator
            # workflow independent of real quote services or a user's Desktop.
            stack.enter_context(patch.object(app.sources,"chart_history",side_effect=ValueError("fixture quote offline")))
            stack.enter_context(patch("hyperpass.tradingview_chart.fetch_selected_chart",side_effect=ValueError("fixture chart offline")))
            server = serve(app, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            stack.callback(thread.join)
            stack.callback(server.server_close)
            stack.callback(server.shutdown)
            playwright = stack.enter_context(sync_playwright())
            browser = playwright.chromium.launch(channel="chrome")
            stack.callback(browser.close)
            page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
            page.set_default_timeout(8000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/api/market-index?*", lambda route: route.fulfill(
                status=503, json={"error": "지수 데이터는 화면 검증에서 사용하지 않습니다."}))
            page.goto(f"http://127.0.0.1:{server.server_port}")

            def workspace(name):
                page.locator(f'nav [data-workspace="{name}"]').click()

            chart = page.locator("#workspace-chart")
            pine = page.locator("#workspace-tradingview")
            workspace("chart")
            expect(chart.locator("#tv-personal-code")).to_be_visible()
            expect(pine.locator("#tv-personal-code")).to_have_count(0)
            self.assertFalse(page.locator("#tv-code").is_visible())
            self.assertTrue(chart.locator("#tv-configure").count())
            indicators = chart.locator("#tv-personal-list")
            indicators.select_option(old["id"])
            expect(chart.locator("#tv-personal-code")).to_have_value(old["code"])
            chart.locator("#tv-personal-example").click()
            code = chart.locator("#tv-personal-code").input_value()
            self.assertIn("ta.pivothigh", code)
            self.assertIn("line.new", code)
            # The example requires neither a model connection nor a running Desktop instance.
            chart.locator("#tv-personal-name").fill("주봉 고점 연구")
            chart.locator("#tv-personal-save").click()
            expect(chart.locator("#tv-personal-feedback")).to_contain_text("저장")
            stored = next(item for item in app.indicators.list() if item["name"] == "주봉 고점 연구")
            self.assertEqual(stored["code"], code)
            page.reload()
            workspace("chart")
            indicators.select_option(stored["id"])
            expect(chart.locator("#tv-personal-code")).to_have_value(code)

            # A Yahoo chart still requires an identified Desktop chart for personal Pine.
            chart.locator("#chart-source").select_option("yahoo")
            chart.locator("#chart-symbol").fill("삼성전자")
            chart.locator("#chart-interval").select_option("1wk")
            apply = chart.locator("#tv-personal-apply")
            with page.expect_response(lambda r: "/api/tradingview/status?" in r.url):
                apply.click()
            expect(chart.locator("#chart-tv-job-message")).to_contain_text("Desktop")
            self.assertEqual(app.tv_jobs.list(), [])

            desktop.connected = True
            apply.click()
            expect(chart.locator("#chart-tv-job-badge")).to_have_text("개인 지표 적용 완료", timeout=12000)
            job = app.tv_jobs.list()[0]
            expected = {"action": "indicator", "target_id": "desk-a", "port": 9222,
                        "symbol": "KRX:005930", "timeframe": "1W", "code": code, "indicators": []}
            self.assertEqual(job["request"], expected)
            self.assertEqual(desktop.indicator_chart, ("desk-a", "KRX:005930", "1W"))
            expect(chart.locator("#chart-tv-history")).to_contain_text("개인 지표")
            expect(chart.locator("#chart-tv-result-summary")).to_contain_text("Hyperpass")

            # The selected Desktop window and its own interval also survive the status preflight.
            desktop.tabs["desk-b"] = {"symbol": "NASDAQ:MSFT", "timeframe": "60"}
            chart.locator("#chart-source").select_option("tradingview")
            original_query = chart.locator("#chart-symbol").input_value()
            chart.locator("#chart-target").select_option("desk-b")
            expect(chart.locator("#chart-symbol")).to_have_value(original_query)
            chart.locator("#chart-use-desktop").click()
            expect(chart.locator("#chart-symbol")).to_have_value("NASDAQ:MSFT")
            chart.locator("details.tv-builtins > summary").click()
            chart.locator("#tv-queue-indicator").click()
            chart.locator("#tv-configure").click()
            expect(chart.locator("#chart-tv-job-badge")).to_have_text("차트 적용 완료", timeout=12000)
            config = app.tv_jobs.list()[0]["request"]
            self.assertEqual((config["action"], config["target_id"], config["symbol"], config["timeframe"]),
                             ("configure", "desk-b", "NASDAQ:MSFT", "60"))
            self.assertEqual(len(config["indicators"]), 1)
            expect(chart.locator("#chart-tv-history")).to_contain_text("차트 설정")

            chart.locator("#chart-tv-settings").click()
            chart.locator("#chart-tv-timeframe").select_option("15")
            expect(chart.locator("#chart-tv-destination")).to_contain_text("15분")
            with page.expect_response(lambda r: r.url.endswith("/api/tradingview/jobs") and r.request.method == "POST"):
                chart.locator("#tv-configure").click()
            expect(chart.locator("#chart-tv-job-badge")).to_have_text("차트 적용 완료", timeout=12000)
            override = app.tv_jobs.list()[0]["request"]
            self.assertEqual((override["target_id"], override["symbol"], override["timeframe"]),
                             ("desk-b", "NASDAQ:MSFT", "15"))

            workspace("tradingview")
            for engine in ("portfolio", "pine"):
                pine.locator("#bt-engine").select_option(engine)
                for mode in ("market", "single", "custom"):
                    pine.locator("#bt-scope").select_option(mode)
                    self.assertFalse(apply.is_visible(), (engine, mode))
            self.assertEqual(pine.locator("#tv-configure").count(), 0)

            # Seed the previous single-chart job format and reopen it through its history.
            strategy_code = '//@version=6\nstrategy("QA strategy")\nstrategy.entry("long", strategy.long)'
            request = {"action": "backtest", "target_id": "desk-a", "symbol": "NASDAQ:AAPL",
                       "port": 9222, "timeframe": "1D", "indicators": [], "code": strategy_code}
            previous = desktop.run_strategy(port=9222, target_id="desk-a", code=strategy_code, timeout=75,
                                            on_progress=None, expected_chart={"symbol": "NASDAQ:AAPL", "timeframe": "1D"})
            strategy = {"id": "b" * 32, "status": "completed", "created_at": "2025-11-30T00:00:00+00:00",
                        "request": request, "result": previous, "stage": "finished"}
            app.tv_jobs.put(strategy)
            pine.locator(".bt-legacy-history > summary").click()
            pine.locator("#tv-history-refresh").click()
            pine.locator("#tv-history button").filter(has_text="전략 백테스트").click()
            expect(pine.locator("#tv-metrics")).to_contain_text("123.45")
            expect(pine.locator("#tv-history")).not_to_contain_text("개인 지표")
            workspace("chart")
            expect(chart.locator("#chart-tv-history")).not_to_contain_text("전략 백테스트")
            chart.locator("#chart-tv-history button").filter(has_text="개인 지표").click()
            expect(chart.locator("#chart-tv-result-summary")).to_contain_text("Hyperpass")
            self.assertFalse(pine.is_visible())

            workspace("brain")
            page.locator("#brain-records .brain-record").filter(has_text="NASDAQ:AAPL").click()
            expect(pine.locator("#tv-metrics")).to_contain_text("123.45")
            expect(pine.locator("#tv-metrics")).to_be_visible()
            self.assertFalse(chart.is_visible())

            workspace("chart")
            page.set_viewport_size({"width": 375, "height": 850})
            expect(apply).to_be_visible()
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
            duplicates = page.evaluate("""() => {
                const ids = [...document.querySelectorAll('[id]')].map(el => el.id);
                return ids.filter((id, index) => ids.indexOf(id) !== index);
            }""")
            self.assertEqual(duplicates, [])
            self.assertEqual(errors, [])
            self.assertEqual(next(item for item in app.indicators.list() if item["id"] == old["id"]), old)
            self.observed = {
                "browser": browser.version,
                "fixture": "isolated HTTP application and persistent SQLite, two simulated Desktop tabs",
                "old_saved_indicator_reopened": True, "example_saved_and_reopened_after_reload": True,
                "unavailable_desktop_created_jobs": 0, "chart_indicator_target": list(desktop.indicator_chart),
                "desktop_source_target": [config["target_id"], config["symbol"], config["timeframe"]],
                "explicit_study_period": override["timeframe"],
                "strategy_symbol": strategy["request"]["symbol"], "strategy_report_fixture_net_profit": 123.45,
                "isolated_backtest_modes": ["market", "single", "custom"], "engines": ["pine", "portfolio"],
                "chart_history_reopened": True, "second_brain_strategy_reopened": True,
                "page_errors": errors, "duplicate_ids": duplicates, "widths_px": [375, 1440],
                "live_desktop_modified": False,
            }


class FixtureDesktop:
    def __init__(self):
        self.connected = False
        self.indicator_chart = None
        self.tabs = {"desk-a": {"symbol": "NASDAQ:AAPL", "timeframe": "1D"}}

    def status(self, port, target_id=None):
        if not self.connected:
            return {"connected": False, "port": port, "error": "TradingView Desktop에 연결할 수 없습니다."}
        targets = [{"id": key, "title": tab["symbol"]} for key, tab in self.tabs.items()]
        if not target_id and len(targets) > 1:
            return {"connected": False, "port": port, "targets": targets,
                    "message": "TradingView 차트가 여러 개 열려 있습니다. 사용할 차트 탭을 선택하세요."}
        target = target_id or targets[0]["id"]
        return {"connected": True, "port": port, "target_id": target,
                "chart": self.tabs[target], "targets": targets}

    def configure_chart(self, *, port, target_id, symbol, timeframe, indicators):
        target = target_id or "desk-a"
        chart = {"symbol": symbol, "timeframe": timeframe, "studies": []}
        self.tabs[target] = chart
        return {"target_id": target, "status": "configured", "chart": chart}

    def run_indicator(self, *, port, target_id, code, timeout, on_progress, expected_chart):
        self.indicator_chart = (target_id, expected_chart["symbol"], expected_chart["timeframe"])
        return {"status": "applied", "chart": expected_chart, "target_id": target_id,
                "indicator": {"title": "Hyperpass · 1Y Pivot Highs", "id": "fixture-study"}}

    def run_strategy(self, *, port, target_id, code, timeout, on_progress, expected_chart):
        return {"status": "completed", "target_id": target_id, "chart": expected_chart,
                "report": {"study_id": "fixture-strategy", "strategy": "QA strategy", "currency": "TEST",
                           "metrics": {"net_profit": 123.45}, "settings": {}, "trades": []}}
