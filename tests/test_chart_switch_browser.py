import os
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from hyperpass.server import Application, serve
from test_chart_lab import packet


class ChartPreviewStorageTest(unittest.TestCase):
    def test_preview_save_keeps_exact_data_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Application(Path(folder)/'data', team_dir=Path(folder)/'team')
            data = dict(packet(range(10,90)), provider='yahoo', symbol='005930.KS', timeframe='1d')
            with patch.object(app.sources, 'chart_history', return_value=data) as load:
                chart = app.chart({'source':'yahoo','symbol':'005930.KS','preview':True})
                self.assertEqual(app.store.list_charts(), [])
                self.assertTrue(chart['preview'])
                for _ in range(2):
                    self.assertTrue(app.save_chart_preview(chart['id'])['saved'])
            self.assertEqual(load.call_count,1)
            self.assertEqual(app.store.get_chart(chart['id'])['provenance'],chart['provenance'])
            self.assertEqual(len(app.store.list_charts()),1)


@unittest.skipUnless(os.getenv('HYPERPASS_TEST_BROWSER')=='1','opt-in Chrome integration')
class ChartSwitchBrowserTest(unittest.TestCase):
    def test_source_and_symbol_switch_without_submit(self):
        from playwright.sync_api import expect,sync_playwright
        with ExitStack() as stack:
            root=Path(stack.enter_context(tempfile.TemporaryDirectory()))
            app=Application(root/'data',team_dir=root/'team')
            slow_yahoo,release_yahoo=threading.Event(),threading.Event()
            def prices(symbol,period,interval):
                if period=='5y':
                    slow_yahoo.set()
                    if not release_yahoo.wait(10):
                        raise ValueError('test Yahoo timed out')
                return dict(packet(range(50,135)),provider='yahoo',symbol=symbol,period=period,timeframe=interval)
            stack.enter_context(patch.object(app.sources,'chart_history',side_effect=prices))
            archive=app.chart({'source':'yahoo','symbol':'005930.KS'})
            slow_started,release=threading.Event(),threading.Event()
            offline=False
            calls=[]
            def bars(port,symbol,count,target,timeframe):
                calls.append((symbol,timeframe))
                if symbol=='KRX:005930' and not slow_started.is_set():
                    slow_started.set()
                    if not release.wait(10):
                        raise ValueError('test preview timed out')
                return dict(packet(range(200,285)),timeframe=timeframe,currency='KRW',observed_symbol=symbol)
            def status(port,target_id=None):
                if offline:
                    return {'connected':False,'targets':[],'message':'Desktop 연결이 끊어졌습니다.'}
                return {'connected':True,'target_id':'desk','targets':[{'id':'desk','title':'차트'}],
                        'chart':{'symbol':'KRX:005930','timeframe':'1D'}}
            stack.enter_context(patch('hyperpass.tradingview_control.status',side_effect=status))
            stack.enter_context(patch('hyperpass.tradingview_chart.fetch_selected_chart',side_effect=bars))
            stack.enter_context(patch('hyperpass.symbol_search.search_symbols',return_value={'results':[
                {'id':'KRX:000660','name':'SK하이닉스','ticker':'000660','exchange':'KRX'}]}))
            server=serve(app,0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            stack.callback(thread.join);stack.callback(server.server_close);stack.callback(server.shutdown)
            browser=stack.enter_context(sync_playwright()).chromium.launch(channel='chrome')
            stack.callback(browser.close);stack.callback(release.set);stack.callback(release_yahoo.set)
            page=browser.new_page()
            page.set_default_timeout(8000)
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.route('**/api/market-index?*',lambda r:r.fulfill(status=503,json={'error':'test'}))
            page.goto(f'http://127.0.0.1:{server.server_port}')
            page.locator('nav [data-workspace="chart"]').click()
            page.evaluate('(id)=>window.HyperpassChart.open(id)',archive['id'])
            expect(page.locator('#chart-title')).to_have_text('삼성전자 · 005930 / 일봉')
            page.locator('#chart-source').select_option('tradingview')
            self.assertTrue(slow_started.wait(4))
            expect(page.locator('#chart-provenance')).to_contain_text('TradingView Desktop')
            expect(page.locator('#chart-conclusion')).to_be_hidden()
            page.locator('#chart-symbol').fill('SK하이닉스')
            page.locator('#chart-symbol-matches button').first.click()
            expect(page.locator('#chart-title')).to_have_text('TradingView Desktop · SK하이닉스')
            release.set()
            expect(page.locator('#chart-title')).to_have_text('SK하이닉스 · 000660 / 일봉')
            expect(page.locator('#chart-provenance')).to_contain_text('TradingView Desktop · 85봉')
            self.assertEqual(calls,[('KRX:005930','1D'), ('KRX:000660','1D')])
            self.assertEqual(len(app.store.list_charts()),1)
            page.locator('#chart-save-preview').click()
            expect(page.locator('#chart-saved-status')).to_have_text('Second Brain에 저장됨')
            self.assertEqual(len(app.store.list_charts()),2)
            page.locator('#chart-tv-timeframe').select_option('1W')
            expect(page.locator('#chart-title')).to_have_text('SK하이닉스 · 000660 / 주봉')
            page.locator('#chart-source').select_option('yahoo')
            expect(page.locator('#chart-provenance')).to_contain_text('Yahoo Finance · 85봉')
            page.locator('#chart-period').select_option('5y')
            self.assertTrue(slow_yahoo.wait(4))
            page.locator('#chart-source').select_option('tradingview')
            expect(page.locator('#chart-provenance')).to_contain_text('TradingView Desktop · 85봉')
            with page.expect_response(lambda response: '/api/charts' in response.url and
                                      response.request.method=='POST' and response.request.post_data_json.get('period')=='5y'):
                release_yahoo.set()
            expect(page.locator('#chart-provenance')).to_contain_text('TradingView Desktop · 85봉')
            offline=True
            page.locator('#chart-tv-timeframe').select_option('1M')
            expect(page.locator('#chart-provenance')).to_have_text('Desktop 연결이 끊어졌습니다.')
            expect(page.locator('#chart-empty')).to_be_visible()
            self.assertIsNone(page.evaluate('window.HyperpassChart.lastResult()'))
            page.locator('#chart-source').select_option('csv')
            expect(page.locator('#chart-provenance')).to_contain_text('CSV 파일')
            expect(page.locator('#chart-symbol')).to_have_value('')
            page.locator('#chart-symbol').fill('삼성전자')
            page.locator('#chart-csv-file').set_input_files({'name':'prices.csv','mimeType':'text/csv',
                'buffer':b'time,open,high,low,close,volume\n2020-01-01,1,2,1,2,10'})
            expect(page.locator('#chart-symbol')).to_have_value('')
            expect(page.locator('#chart-empty')).to_contain_text('종목명')
            self.assertEqual(len(app.store.list_charts()),2)
            self.assertEqual(errors,[])
