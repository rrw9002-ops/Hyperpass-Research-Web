"""Exercise the student screener, including the expanded desktop select."""
from contextlib import ExitStack
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from hyperpass.server import Application, serve


def fixture(market):
    rows = []
    count = 44 if market == 'KR' else 1
    for i in range(count):
        korean = market == 'KR'
        ticker = 'AAPL' if not korean else f'{5930+i:06d}'
        name = '애플' if not korean else ('삼성전자' if i == 0 else f'종목 {i}')
        rows.append(dict(name=name, id=('KRX:' if korean else 'NASDAQ:')+ticker, symbol=ticker,
                         yahoo=ticker+('.KS' if korean else ''), exchange='KOSPI' if korean else 'NASDAQ',
                         sector='기술', industry='반도체', currency='KRW' if korean else 'USD',
                         price=120+i, market_cap=1e10-i, turnover=1e8, per=10 if i!=1 else None,
                         pbr=2, roe=i, margin=10, debt=0.4, volume=500, income=None,
                         price_date='2026-11-20', fiscal_date='2026-09-30'))
    return dict(rows=rows, market=market, as_of='2026-11-21T12:00:00Z', listed_count=len(rows),
                exchanges={'KOSPI':'코스피'} if market=='KR' else {'NASDAQ':'나스닥'})


@unittest.skipUnless(os.getenv('HYPERPASS_TEST_BROWSER')=='1', 'opt-in Chrome integration')
class ScreenerStudioBrowserTest(unittest.TestCase):
    def test_filter_compare_export_and_switch_market(self):
        from playwright.sync_api import sync_playwright, expect
        with ExitStack() as stack:
            root=Path(stack.enter_context(tempfile.TemporaryDirectory()))
            app=Application(root/'data',team_dir=root/'team')
            stack.enter_context(patch('hyperpass.equity_screen.snapshot', side_effect=fixture))
            server=serve(app,0)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            stack.callback(thread.join); stack.callback(server.server_close); stack.callback(server.shutdown)
            browser=stack.enter_context(sync_playwright()).chromium.launch(channel='chrome')
            stack.callback(browser.close)
            page=browser.new_page(viewport={'width':1440,'height':960})
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}')
            page.locator('nav [data-workspace="screener"]').click()
            expect(page.locator('#sc-count')).to_have_text('44 종목')
            expect(page.locator('#sc-rows tr')).to_have_count(40)
            page.locator('#sc-presets').get_by_text('저평가',exact=True).click()
            expect(page.locator('#sc-count')).to_have_text('43 종목')
            with page.expect_download() as download:
                page.locator('#sc-csv').click()
            with download.value.path().open(encoding='utf-8-sig') as f:
                lines=f.read().splitlines()
            self.assertEqual(len(lines),44)
            self.assertIn('삼성전자',lines[1])
            page.locator('#sc-rows input').first.check()
            page.locator('#sc-compare').click()
            expect(page.locator('#sc-matrix')).to_contain_text('삼성전자 · 005930')
            page.locator('#sc-query').fill('005930')
            page.locator('#sc-search').click()
            expect(page.locator('#sc-count')).to_have_text('1 종목')
            page.locator('#sc-venues input').uncheck()
            page.locator('#sc-search').click()
            expect(page.locator('#sc-count')).to_have_text('0 종목')
            page.locator('#sc-market').click()
            if page.evaluate("CSS.supports('appearance','base-select')"):
                self.assertEqual(page.locator('#sc-market').evaluate("(s)=>getComputedStyle(s,'::picker(select)').backgroundColor"),'rgb(33, 30, 25)')
            page.keyboard.press('Escape')
            page.locator('#sc-market').select_option('US')
            expect(page.locator('#sc-rows')).to_contain_text('애플')
            expect(page.locator('#sc-rows')).to_contain_text('AAPL · NASDAQ')
            page.locator('#sc-rows input').first.check()
            page.locator('#sc-backtest').click()
            expect(page.locator('#bt-symbol')).to_have_value('NASDAQ:AAPL')
            self.assertEqual(errors,[])
