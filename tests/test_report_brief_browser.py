import os
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path

from hyperpass.report_brief import student_brief, SECTIONS
from hyperpass.server import Application, serve


class BriefTest(unittest.TestCase):
    def test_observation_from_accepted_input_when_head_paraphrases_it(self):
        source = {"id": "technical-analyst-v1", "report": "SMA 100원 · 제공된 실습 CSV · 2025-03-07",
                  "observations": [{"statement": "SMA 100원", "source": "제공된 실습 CSV", "as_of": "2025-03-07"}]}
        brief, _ = student_brief("## 관측 사실\n- 평균값 100원 [[technical-analyst-v1|2025-03-07]]", [source])
        self.assertIn("SMA 100원 · 제공된 실습 CSV · 관측일 2025-03-07", brief)
        self.assertIn("(#technical-analyst-v1)", brief)
        self.assertIn("보류", brief)
        self.assertNotIn("평균값 100원", brief)

    def test_matches_exact_producer_text_and_only_its_observation_date(self):
        source = {"id": "technical-analyst-v1", "report": "2025-03-07 실습자료 종가 100원\n2025-03-10 거래량 1,000주"}
        candidate = """## 관측 사실
- 실습자료 종가 100원 [[technical-analyst-v1|2025-03-07]]
- 거래량 1,000주 [[technical-analyst-v1|2025-03-07]]
- 종가 500원 [[technical-analyst-v1|2025-03-07]]
- 거래량 1,000주 [[technical-analyst-v2|2025-03-10]]
## 해석
- 거래량을 더 확인합니다.
## 기타 분석
원래 본문"""
        brief, body = student_brief(candidate, [source])
        self.assertIn("관측일 2025-03-07", brief)
        self.assertIn("거래량 1,000주 · 관측일 미확인", brief)
        self.assertNotIn("v2", brief)
        self.assertNotIn("500원", brief)
        self.assertIn("보류", brief)
        self.assertTrue(all("## " + title in brief for title in SECTIONS))
        self.assertEqual(body, "## 기타 분석\n원래 본문")


@unittest.skipUnless(os.getenv("HYPERPASS_TEST_BROWSER") == "1", "opt-in Chrome integration")
class BriefBrowserTest(unittest.TestCase):
    def test_report_evidence_navigation_and_export(self):
        from playwright.sync_api import expect, sync_playwright
        with ExitStack() as stack:
            root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            app = Application(root / "data", team_dir=root / "team")
            server = serve(app, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            stack.callback(thread.join)
            stack.callback(server.server_close)
            stack.callback(server.shutdown)
            browser = stack.enter_context(sync_playwright()).chromium.launch(channel="chrome")
            stack.callback(browser.close)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}")
            page.locator("#demo-button").click()
            expect(page.locator("#tab-report")).to_have_text("최종 보고서", timeout=20000)
            page.locator("#tab-report").click()
            report = page.locator("#report-content")
            expect(report.get_by_role("heading", name="관측 사실", exact=True)).to_be_visible()
            expect(report).to_contain_text("관측일 미확인")
            for title in SECTIONS:
                expect(report.get_by_role("heading", name=title, exact=True)).to_be_visible()
            report.get_by_role("link", name="근거 fundamental-analyst-v1").click()
            card = page.locator("#artifact-fundamental-analyst-v1")
            expect(card).to_have_attribute("open", "")
            expect(card.locator(".artifact-body")).to_be_visible()
            export_path = page.locator("#export-button").get_attribute("href")
            response = page.request.get(f"http://127.0.0.1:{server.server_port}{export_path}")
            self.assertTrue(response.ok)
            output = response.text()
            self.assertIn("(#fundamental-analyst-v1)", output)
            self.assertIn("### fundamental-analyst-v1", output)
            self.assertIn("다음 확인 날짜 및 자료", output)
