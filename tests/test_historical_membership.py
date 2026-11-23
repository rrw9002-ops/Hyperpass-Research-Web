import unittest
from datetime import date, timedelta
from unittest.mock import patch

from hyperpass import membership, market_backtest


def event(symbol, effective, public, member):
    return dict(symbol=symbol, effective_date=effective, available_date=public, member=member)


def prices(symbol, start, end, cache, **kwargs):
    price = 10 if symbol == 'AAA' else 20
    rows = []
    while start <= end:
        if start.weekday() < 5:
            rows.append([start.isoformat(), price, price+1, price-1, price, 1000, 0])
        start += timedelta(days=1)
    return 'USD', rows


class HistoricalMembershipTest(unittest.TestCase):
    def test_late_knowledge_never_overrides_newer_effective_event(self):
        series = membership.timelines([
            event('AAA','2024-01-01','2024-01-15','in'),
            event('AAA','2024-01-08','2024-01-05','out'),
            event('AAA','2024-02-02','2024-02-02','in')],
            date(2024,1,1),date(2024,2,29))['AAA']
        for stamp in ['2024-01-03','2024-01-08','2024-01-16','2024-02-02']:
            self.assertFalse(series.active(date.fromisoformat(stamp).toordinal()))
        self.assertTrue(series.active(date(2024,2,3).toordinal()))

    def test_csv_and_filter_validation(self):
        header = 'symbol,effective_date,available_date,member\n'
        row = '005930.KS,2024-01-01,2023-12-29,in\n'
        self.assertEqual(membership.import_csv('KR',header+row)[0]['symbol'],'005930.KS')
        for region, contents in [('KR',header+row+row),('US',header+row),('KR',header+row.replace('in','1'))]:
            with self.subTest(region=region,contents=contents), self.assertRaises(ValueError):
                membership.import_csv(region,contents)

    def test_historical_ranking_uses_known_membership_and_eps_at_signal(self):
        request = dict(mode='market', market='US', symbols=[], max_positions=1, rebalance={'frequency':'daily','month':1},
            settings=dict(strategy='none',start_date='2024-01-02',end_date='2024-01-17',fee_bps=10,slippage_bps=5),
            strategy_code=dict(version=1,entry='ranked',exit='rank_drop',factors=[dict(field='per',order='asc')]),
            membership=[event('AAA','2024-01-01','2023-12-15','in'),event('AAA','2024-01-08','2024-01-04','out'),
                        event('BBB','2024-01-01','2024-01-09','in'),event('LATER','2024-01-25','2024-01-01','in')],
            fundamentals=[dict(symbol='AAA',available_date='2023-12-15',eps=1),
                          dict(symbol='BBB',available_date='2024-01-11',eps=12)])
        with patch.object(market_backtest,'resolve_universe',side_effect=AssertionError('current listings')), \
                patch.object(market_backtest,'read_prices',side_effect=prices):
            res = market_backtest.run_backtest(request)
        self.assertEqual(res['coverage']['used_symbols'],['AAA','BBB'])
        self.assertEqual(res['coverage']['selection_basis'],'historical_membership')
        self.assertIsNone(res['coverage']['as_of'])
        self.assertEqual([(o['side'],o['symbol'],o['signal_date'],o['date']) for o in res['orders']],
                         [('buy','AAA','2024-01-02','2024-01-03'),('sell','AAA','2024-01-08','2024-01-09'),
                          ('buy','BBB','2024-01-12','2024-01-15')])
        self.assertLess(res['metrics']['total_return_pct'],0)
        self.assertEqual(res['coverage']['status'],'partial')
        for invalid in ({'mode':'custom','symbols':['AAA']},{'universe':{'exchanges':['NASDAQ']}}):
            with self.assertRaises(ValueError):
                market_backtest.validate_request(dict(request,**invalid))

    def test_removed_candidate_cannot_buy_on_effective_day(self):
        request = dict(mode='market',market='US',max_positions=1,
            settings=dict(strategy='none',start_date='2024-01-02',end_date='2024-01-08'),
            strategy_code=dict(version=1,entry='ranked',exit='rank_drop',factors=[dict(field='close',order='asc')]),
            rebalance={'frequency':'daily','month':1},
            membership=[event('AAA','2024-01-02','2024-01-01','in'),event('AAA','2024-01-03','2024-01-01','out')])
        with patch.object(market_backtest,'read_prices',side_effect=prices):
            res=market_backtest.run_backtest(request)
        self.assertEqual(res['orders'],[])
        self.assertEqual(res['metrics']['total_return_pct'],0)
        self.assertEqual(res['coverage']['traded'],0)
