import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hyperpass.research_desk import ResearchDesk
from hyperpass.market_backtest import BacktestCancelled
from hyperpass.server import Store


class ResearchDeskTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = Store(Path(folder.name))
        self.desk = ResearchDesk(self.store)
        self.request = {'name':'첫 연구','market':'US','mode':'custom','symbols':['AAPL','MSFT'],
                        'settings':{'strategy':'sma_cross','start_date':'2024-01-01','end_date':'2024-12-31'}}

    def wait(self, job):
        for _ in range(200):
            row = self.desk.job(job['id'])
            if row['status'] not in ('running','queued'):
                return row
            time.sleep(.01)
        self.fail('backtest did not finish')

    def test_watchlist_keeps_report_and_chart_across_restart_and_quote_failure(self):
        self.store.put({'id':'a','status':'completed'})
        self.store.put_chart({'id':'b'})
        self.desk.follow({'symbol':'애플','run_id':'a'})
        self.desk.follow({'symbol':'NASDAQ:AAPL','chart_id':'b'})
        sources = Mock()
        sources.chart_history.return_value = {'currency':'USD','records':[
            {'close':100,'timestamp':'2024-01-02'}, {'close':110,'timestamp':'2024-01-03'}]}
        q = self.desk.quote('NASDAQ:AAPL',sources)
        self.assertAlmostEqual(q['change_pct'],10)
        sources.chart_history.side_effect = ValueError('unavailable')
        with self.assertRaises(ValueError): self.desk.quote('NASDAQ:AAPL',sources)
        rows = ResearchDesk(self.store).watchlist()
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['run_id'],rows[0]['chart_id'],rows[0]['quote']),('a','b',q))
        self.desk.unfollow('NASDAQ:AAPL')
        self.assertEqual(self.desk.watchlist(),[])

    def test_watch_selection_and_first_judgment_survive_later_edits(self):
        from copy import deepcopy
        snap=dict(version=1,kind='screener_fixed_basket',market='KR',provider='KIS',
                  selected_at='2026-11-01T09:30:00+09:00',data_as_of='2026-11-01T09:29:00+09:00',
                  filters={'exchanges':['KOSPI'],'ranges':[dict(field='per',min=0,max=15)]},
                  counts=dict(scope=3,evaluable=2,passed=1,failed=1,missing=1),
                  members=[dict(id='KRX:005930',name='삼성전자',symbol='005930',exchange='KOSPI',
                                yahoo='005930.KS',price=91_000,currency='KRW',price_label='기준가',
                                price_source='KIS 마스터',metrics={'per':10},metric_sources={'per':'KIS'})])
        identity='KRX:005930'
        self.desk.follow({'symbol':'삼성전자'})
        self.assertIsNone(self.desk.watchlist()[0]['selection_snapshot'])
        self.desk.follow({'symbol':identity,'selection_snapshot':snap})
        changed=deepcopy(snap);changed['members'][0]['price']=95_000
        self.desk.follow({'symbol':identity,'selection_snapshot':changed})
        self.desk.update_watch_decision(dict(symbol=identity,thesis='이익 개선',invalidation='영업적자'))
        self.desk.update_watch_decision(dict(symbol=identity,thesis='새 관점',invalidation='배당 감소'))
        saved=ResearchDesk(self.store).watchlist()[0]
        self.assertEqual(saved['selection_snapshot']['members'][0]['price'],91_000)
        self.assertEqual(saved['first_note']['invalidation'],'영업적자')
        self.assertEqual(saved['invalidation'],'배당 감소')
        with self.assertRaises(ValueError):
            self.desk.follow({'symbol':'NASDAQ:AAPL','selection_snapshot':snap})
        changed['members'][0]['yahoo']='005930.KQ'
        with self.assertRaises(ValueError):
            self.desk.follow({'symbol':identity,'selection_snapshot':changed})
        self.desk.unfollow(identity)
        with self.assertRaises(ValueError):
            self.desk.update_watch_decision(dict(symbol=identity,thesis='수정',invalidation=''))
        self.desk.follow({'symbol':identity})
        self.assertIsNone(self.desk.watchlist()[0]['first_note'])

    def test_yahoo_only_watchlist_does_not_merge_two_unlisted_symbols(self):
        for s in ('EURUSD=X','GBPUSD=X'):
            self.desk.follow({'symbol':s})
        self.assertEqual({row['symbol'] for row in self.desk.watchlist()},{'EURUSD=X','GBPUSD=X'})

    def test_watch_candidates_prefer_longer_name_and_preserve_share_classes(self):
        from hyperpass.research_desk import report_symbols
        self.assertEqual([p['symbol'] for p in report_symbols({'question':'삼성전자우선주를 분석해줘'})],['KRX:005935'])
        self.assertEqual({p['symbol'] for p in report_symbols({'question':'구글의 사업 분석'})},
                         {'NASDAQ:GOOG','NASDAQ:GOOGL'})
        self.assertEqual(report_symbols({'question':'금리 분석'}),[])

    def test_invalid_reference_does_not_write(self):
        with self.assertRaises(ValueError): self.desk.follow({'symbol':'삼성전자','run_id':'missing'})
        self.assertEqual(self.desk.watchlist(),[])

    def test_strategy_storage_is_typed_and_reopens_exact_pine(self):
        code='//@version=6\nstrategy("예제")\nplot(close)'
        row=self.desk.save_strategy(dict(name='원문',kind='pine',definition={'code':code,'timeframe':'1D'},source='사용자 입력'))
        self.desk.save_strategy(dict(row,name='새 이름'))
        saved=ResearchDesk(self.store).strategies()[0]
        self.assertEqual((saved['name'],saved['definition']['code'],saved['source']),('새 이름',code,'사용자 입력'))
        for kind,definition in [('chart',{'settings':{'strategy':'unavailable'}}),
                                ('pine',{'code':'indicator("X")'}),('market',{'mode':'bad'})]:
            with self.assertRaises(ValueError): self.desk.save_strategy(dict(name='검사',kind=kind,definition=definition))
        self.assertEqual(len(self.desk.strategies()),1)

    def test_job_state_and_duplicate_start_and_cancel(self):
        entered=threading.Event()
        def run(options, progress, stop, *, cache_dir):
            entered.set()
            stop.wait(timeout=3)
            raise BacktestCancelled('cancelled')
        with patch('hyperpass.market_backtest.run_backtest',run):
            job=self.desk.start(self.request)
            self.assertTrue(entered.wait(timeout=2))
            with self.assertRaises(ValueError): self.desk.start(self.request)
            self.desk.cancel(job['id'])
            self.assertEqual(self.wait(job)['status'],'cancelled')
        with patch('hyperpass.market_backtest.run_backtest',return_value={'metrics':{'sessions':2}}):
            done=self.wait(self.desk.start(self.request))
        self.assertEqual((done['result']['metrics']['sessions'],done['progress']['percent']),(2,100))
        self.assertEqual(len(ResearchDesk(self.store).list_jobs()),2)
        self.assertNotIn('result',self.desk.list_jobs()[0])
