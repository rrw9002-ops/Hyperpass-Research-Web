"""Exercise the student screener, including the expanded desktop select."""
from contextlib import ExitStack
import csv
from datetime import datetime, timedelta, timezone
import os
import re
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
    return dict(rows=rows, market=market,source='한국투자증권 KIS' if market=='KR' else 'Yahoo Finance',quote_mode='master' if market=='KR' else 'api', as_of='2026-11-21T12:00:00Z', listed_count=len(rows),
                exchanges={'KOSPI':'코스피'} if market=='KR' else {'NASDAQ':'나스닥'})


@unittest.skipUnless(os.getenv('HYPERPASS_TEST_BROWSER')=='1', 'opt-in Chrome integration')
class ScreenerStudioBrowserTest(unittest.TestCase):
    def test_filter_compare_export_and_switch_market(self):
        from playwright.sync_api import sync_playwright, expect
        with ExitStack() as stack:
            root=Path(stack.enter_context(tempfile.TemporaryDirectory()))
            app=Application(root/'data',team_dir=root/'team')
            stack.enter_context(patch.object(app.screener, 'snapshot', side_effect=lambda market, **_: fixture(market)))
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
            expect(page.locator('#sc-provider')).to_have_text('한국투자증권 KIS')
            expect(page.locator('#sc-connect')).to_be_visible()
            expect(page.locator('#sc-rows tr')).to_have_count(40)
            page.locator('#sc-presets').get_by_text('저평가',exact=True).click()
            expect(page.locator('#sc-count')).to_have_text('43 종목')
            with page.expect_download() as download:
                page.locator('#sc-csv').click()
            with download.value.path().open(encoding='utf-8-sig') as f:
                lines=f.read().splitlines()
            self.assertEqual(len(lines),44)
            self.assertIn('삼성전자',lines[1])
            with download.value.path().open(encoding='utf-8-sig',newline='') as f:
                row=next(csv.DictReader(f))
            self.assertEqual([row[k] for k in ('대상','평가 가능','통과','조건 탈락','자료 부족')],['44','43','43','0','1'])
            self.assertIn('PER 미제공 1종목',row['누락 사유·출처·기준일'])
            page.locator('#sc-missing summary').click()
            expect(page.locator('#sc-missing-fields')).to_contain_text('한국투자증권 KIS')
            page.locator('#sc-ranges input').last.fill('5')
            page.locator('#sc-search').click()
            expect(page.locator('#sc-count')).to_have_text('0 종목')
            with page.expect_download() as empty_export: page.locator('#sc-csv').click()
            with empty_export.value.path().open(encoding='utf-8-sig',newline='') as f: summary=list(csv.DictReader(f))
            self.assertEqual(len(summary),1)
            self.assertEqual((summary[0]['행 유형'],summary[0]['종목명'],summary[0]['조건 탈락'],summary[0]['자료 부족']),
                             ('검색 요약','','43','1'))
            with page.expect_download() as audit: page.locator('#sc-audit').click()
            with audit.value.path().open(encoding='utf-8-sig',newline='') as f: decisions=list(csv.DictReader(f))
            self.assertEqual(len(decisions),44)
            for decision in decisions:
                per=decision['PER']
                expected='자료 부족' if not per else '통과' if 1<=float(per)<=5 else '조건 탈락'
                self.assertEqual(decision['판정'],expected)
                self.assertEqual(decision['자료 부족 지표'],'' if per else 'PER')
            self.assertEqual(sum(r['판정']=='조건 탈락' for r in decisions),int(summary[0]['조건 탈락']))
            self.assertEqual(sum(r['판정']=='자료 부족' for r in decisions),int(summary[0]['자료 부족']))
            page.locator('#sc-presets').get_by_text('저평가',exact=True).click()
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
            expect(page.locator('#sc-provider')).to_have_text('Yahoo Finance')
            expect(page.locator('#sc-rows')).to_contain_text('AAPL · NASDAQ')
            page.locator('#sc-rows input').first.check()
            page.locator('#sc-backtest').click()
            expect(page.locator('#bt-symbol')).to_have_value('NASDAQ:AAPL')
            self.assertEqual(errors,[])

    def test_watch_selection_persists_and_comparison_becomes_research_evidence(self):
        from playwright.sync_api import sync_playwright, expect
        with ExitStack() as stack:
            root=Path(stack.enter_context(tempfile.TemporaryDirectory()))
            app=Application(root/'data',team_dir=root/'team')
            packet=fixture('KR')
            packet['rows'][0].update(quote_source='KIS 종목 마스터',quote_mode='master')
            selected_day=datetime.now(timezone.utc)-timedelta(days=7)
            latest=datetime.now(timezone.utc).date().isoformat()
            stack.enter_context(patch.object(app.screener,'snapshot',return_value=packet))
            stack.enter_context(patch.object(app.sources,'chart_history',return_value={'currency':'KRW','records':[
                {'timestamp':latest,'close':132}]}))
            server=serve(app,0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            stack.callback(thread.join);stack.callback(server.server_close);stack.callback(server.shutdown)
            browser=stack.enter_context(sync_playwright()).chromium.launch(channel='chrome')
            stack.callback(browser.close)
            page=browser.new_page()
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}')
            page.clock.set_fixed_time(selected_day)
            page.locator('nav [data-workspace="screener"]').click()
            page.locator('#sc-presets').get_by_text('저평가',exact=True).click()
            expect(page.locator('#sc-count')).to_have_text('43 종목')
            page.locator('#sc-rows tr').first.get_by_text('관심 +').click()
            expect(page.locator('#sc-status')).to_contain_text('삼성전자')
            page.locator('#sc-reset').click()
            page.locator('#sc-rows tr').first.get_by_text('관심 +').click()
            expect(page.locator('#sc-status')).to_contain_text('삼성전자')
            page.clock.set_fixed_time(datetime.now(timezone.utc))
            page.locator('nav [data-workspace="brain"]').click()
            card=page.locator('.watch-card').first
            expect(card).to_contain_text('132 KRW')
            card.locator('summary').click()
            expect(card).to_contain_text('기준가 120 KRW')
            expect(card).to_contain_text('PER 1 ~ 15')
            expect(card).to_contain_text('선정 가격 대비 +10.00%')
            card.get_by_text('판단 기록',exact=True).click()
            page.locator('#watch-thesis').fill('이익률 회복')
            page.locator('#watch-invalidation').fill('다음 분기 이익률 감소')
            page.get_by_text('판단 저장',exact=True).click()
            page.reload()
            page.locator('nav [data-workspace="brain"]').click()
            card.locator('summary').click()
            expect(card).to_contain_text('다음 분기 이익률 감소')
            card.get_by_text('이전 판단 다시 검토').click()
            expect(page.locator('#question')).to_have_value(re.compile('삼성전자.*반증 조건'))
            expect(page.locator('#evidence')).to_have_value(re.compile(r'KIS 종목 마스터[\s\S]+선정 가격 대비 \+10.00%[\s\S]+공시 · 미확인'))
            expect(page.locator('#memory')).to_have_value(re.compile('다음 분기 이익률 감소'))
            expect(page.locator('#symbol')).to_have_value('005930.KS')
            self.assertFalse(errors)
