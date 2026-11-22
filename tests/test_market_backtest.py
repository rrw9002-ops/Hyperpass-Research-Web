import json
import math
import tempfile
import threading
import unittest
from array import array
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from hyperpass import market_backtest as engine
from hyperpass import market_prices as prices


def tape(days, opens, closes):
    return engine.Tape(array('i', days), array('d', opens), array('d', closes), [], [], False)


def options(**kwargs):
    return engine.validate_request({'mode':'custom','market':'US','symbols':['AAA','BBB'],
                                    'settings':{'initial_capital':1000,'fee_bps':0,'slippage_bps':0,
                                                'start_date':'2023-02-01','end_date':'2023-03-11'}, **kwargs})


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.days = list(range(date(2023,2,1).toordinal(), date(2023,2,5).toordinal()))
        self.names = {'AAA':'First','BBB':'Second'}
        self.tapes = {'AAA':tape(self.days, [90,100,70,85], [91,80,75,82]),
                      'BBB':tape(self.days, [91,300,310,310], [92,330,300,315])}

    def test_shared_cash_rank_previous_close_costs_and_real_drawdown(self):
        opts = options(max_positions=1)
        opts['settings'].update(fee_bps=100,slippage_bps=100)
        d = self.days
        candidates = {d[0]:[(-.2,'AAA'),(-.1,'BBB')]}
        exits = {d[1]:['AAA']}
        metrics, trades, opened, curve = engine._portfolio(self.tapes,self.names,d,candidates,exits,opts,None)
        q = 1000 / (101 * 1.01)
        final = q * (70 * .99) * .99
        self.assertAlmostEqual(metrics['ending_equity'],final)
        self.assertEqual(metrics['closed_trades'],1)
        self.assertAlmostEqual(metrics['fees'],q * (101 + 69.3) * .01)
        self.assertAlmostEqual(metrics['slippage'],q * (1 + .7))
        self.assertAlmostEqual(metrics['max_drawdown_pct'],(final/1000 - 1) * 100)
        self.assertAlmostEqual(trades[0]['net_pnl'],final - 1000)
        self.assertEqual((trades[0]['symbol'], trades[0]['entry_signal_date'], trades[0]['entry_date'],trades[0]['exit_date']),
                         ('AAA','2023-02-01','2023-02-02','2023-02-03'))
        self.assertFalse(opened)
        self.assertEqual(curve[0]['equity'],1000)

    def test_exit_waits_for_real_open_and_no_fabricated_terminal_trade(self):
        d = self.days
        t = {'AAA':tape([d[0],d[1],d[3]], [90,100,65], [91,80,70])}
        m, trades, _, curve = engine._portfolio(t,self.names,d,{d[0]:[(0,'AAA')]},{d[1]:['AAA']},options(max_positions=1),None)
        self.assertEqual([r['equity'] for r in curve], [1000,800,800,650])
        self.assertEqual(trades[0]['exit_date'],'2023-02-04')
        _, trades, opened, _ = engine._portfolio(t,self.names,d[:3],{d[0]:[(0,'AAA')]},{d[1]:['AAA']},options(max_positions=1),None)
        self.assertFalse(trades)
        self.assertEqual(opened[0]['last_mark'],'2023-02-02')
        self.assertEqual(opened[0]['unrealized_pnl'],-200)

    def test_slot_allocation_and_sells_release_cash_before_buys(self):
        d = self.days
        m, trades, opened, _ = engine._portfolio(self.tapes,self.names,d,{d[0]:[(0,'AAA')],d[1]:[(0,'BBB')]},
                                                  {d[1]:['AAA']},options(max_positions=1),None)
        self.assertEqual(trades[0]['exit_date'],opened[0]['entry_date'])
        self.assertAlmostEqual(opened[0]['entry_cost'],700)
        self.assertEqual(m['cash'],0)

    def test_single_and_market_request_validation(self):
        self.assertEqual(options(mode='single',symbols=['AAA'])['max_positions'],1)
        self.assertEqual(options(mode='market',symbols=[])['symbols'],[])
        for invalid in ({'symbols':[]},{'mode':'single'},{'max_positions':False},{'ranking':'x'},{'lookback':1},{'lookback':253},
                        {'settings':{'start_date':'2000-01-01','end_date':'2020-01-01'}},
                        {'settings':{'strategy':'none'}},{'settings':{'fee_bps':float('nan')}}):
            with self.subTest(invalid=invalid), self.assertRaises(engine.MarketBacktestError):
                options(**invalid)

    def test_cancellation_checked_before_network(self):
        stop = threading.Event()
        stop.set()
        with patch.object(engine,'resolve_universe') as source, self.assertRaises(engine.BacktestCancelled):
            engine.run_backtest(options(),stop_event=stop)
        source.assert_not_called()

    def test_ascending_and_descending_ranking_select_opposite_symbols(self):
        def signals(*args):
            tapes = {s: tape(self.days,[100]*4,[100]*4) for s in self.names}
            tapes['AAA'].entries=[(self.days[0],.1)]
            tapes['BBB'].entries=[(self.days[0],.4)]
            return tapes,[]
        for direction, winner in [('momentum_high','BBB'),('momentum_low','AAA')]:
            with patch.object(engine,'_download_universe',side_effect=signals), patch.object(engine,'_benchmark',return_value={'return_pct':None}):
                result=engine.run_backtest(options(max_positions=1,ranking=direction,lookback=7))
            self.assertEqual(result['open_positions'][0]['symbol'],winner)
            self.assertEqual(result['lookback'],7)
            self.assertEqual(result['ranking'],direction)


class SourceTests(unittest.TestCase):
    def test_names_and_tickers_form_one_symbol(self):
        members,_ = prices.resolve_universe('custom','US',['애플','Apple','AAPL','APPLE'])
        self.assertEqual(set(members),{'AAPL'})
        members,_ = prices.resolve_universe('custom','KR',['삼성전자','005930','005930.KS'])
        self.assertEqual(set(members),{'005930.KS'})

    def test_us_directory_filters_and_translates_share_classes(self):
        rows=b'ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\nBRK.B|Berkshire Class B Common Stock|N|BRK.B|N|100|N|BRK.B\nAAA|AAA ETF Common Shares|P|AAA|Y|100|N|AAA\nZZZ|Common Shares|N|ZZZ|N|100|Y|ZZZ\nTST|Warrants on Common Stock|N|TST|N|100|N|TST\nFile Creation Time|foo\n'
        self.assertEqual(list(prices._us_stocks(rows)),[('BRK-B','Berkshire Class B Common Stock')])

    def test_korean_market_requires_both_current_lists_and_explicit_groups(self):
        def directory(board):
            return ((('KRX:005930','Samsung','005930.KS','ST'),('KRX:000001','Fund','000001.KS','EF')),True) if board=='kospi' else ((('KRX:247540','Eco','247540.KQ','ST'),),True)
        with patch.object(prices.symbol_search,'kr_listings',side_effect=directory):
            members, _ = prices.resolve_universe('market','KR',[])
        self.assertEqual(set(members),{'005930.KS','247540.KQ'})
        with patch.object(prices.symbol_search,'kr_listings',return_value=((),False)), self.assertRaises(engine.MarketBacktestError):
            prices.resolve_universe('market','KR',[])

    def test_cache_and_dates_never_fill_a_missing_open(self):
        raw={'meta':{'symbol':'AAA','currency':'USD'},'timestamp':[1675209600+i*86400 for i in range(4)],
             'indicators':{'quote':[{'open':[1,None,2,3],'high':[2,2,3,4],'low':[.5,1,1,2],'close':[2,2,2,3]}]}}
        payload=json.dumps({'chart':{'result':[raw]}}).encode()
        with tempfile.TemporaryDirectory() as tmp, patch.object(prices,'_get',return_value=payload) as retrieve:
            start, end=date(2023,2,1), date(2023,2,4)
            currency, rows=prices.read_prices('AAA',start,end,tmp)
            _, shorter=prices.read_prices('AAA',start+timedelta(days=1),end,tmp)
            self.assertEqual(retrieve.call_count,1)
            self.assertEqual(currency,'USD')
            self.assertEqual([r[0] for r in rows],['2023-02-01','2023-02-03','2023-02-04'])
            self.assertEqual([r[0] for r in shorter],['2023-02-03','2023-02-04'])
            self.assertEqual(len(list(Path(tmp).glob('*.json.gz'))),1)

    def test_end_to_end_coverage_warmup_cost_stress_benchmark_and_holdout(self):
        def observed(symbol,start,end,cache):
            if symbol == 'BBB':
                raise prices.MarketBacktestError('no bars')
            data=[]
            for i in range((end-start).days+1):
                day=start+timedelta(days=i)
                base=50 + math.sin(day.toordinal()/3)*8
                data.append([day.isoformat(),base,base+1,base-1,base+.1])
            return 'USD', data
        request=options()
        request['settings'].update(strategy='sma_cross',fast_period=2,slow_period=4,fee_bps=3,slippage_bps=4)
        with patch.object(engine,'read_prices',side_effect=observed):
            result=engine.run_backtest(request)
        self.assertEqual(result['coverage']['status'],'partial')
        self.assertEqual(result['coverage']['used'],1)
        self.assertEqual(result['coverage']['used_symbols'],['AAA'])
        self.assertEqual(result['coverage']['excluded'][0]['symbol'],'BBB')
        self.assertTrue(result['trades'])
        self.assertEqual(result['equity_curve'][0]['date'],'2023-02-01')
        self.assertEqual(result['equity_curve'][-1]['date'],'2023-03-11')
        self.assertTrue(all(t['entry_signal_date'] < t['entry_date'] and t['exit_signal_date'] < t['exit_date'] for t in result['trades']))
        self.assertLess(result['cost_stress']['metrics']['ending_equity'],result['metrics']['ending_equity'])
        self.assertIsNotNone(result['benchmark']['return_pct'])
        self.assertTrue(result['holdout']['start']>'2023-02-01')
        json.dumps(result,allow_nan=False)

    def test_broad_outage_not_reported_as_market_performance(self):
        with patch.object(engine,'resolve_universe',return_value=({str(i):str(i) for i in range(30)},'directory')), \
                patch.object(engine,'read_prices',side_effect=prices.ProviderUnavailable('temporary outage')), \
                self.assertRaisesRegex(engine.MarketBacktestError,'12'):
            engine.run_backtest(options(mode='market'))

    def test_signal_does_not_change_with_future_bars(self):
        start = date(2023,1,1)
        rows=[[ (start+timedelta(i)).isoformat(),100+i%7,103+i%7,98+i%7,101+i%7] for i in range(70)]
        opts=options()
        opts['settings'].update(strategy='sma_cross',fast_period=2,slow_period=5)
        truncated=engine._prepare(rows[:50],opts)
        complete=engine._prepare(rows,opts)
        self.assertEqual(truncated.entries,[(day,score) for day,score in complete.entries if day<=truncated.days[-1]])
        self.assertEqual(truncated.exits,[day for day in complete.exits if day<=truncated.days[-1]])


if __name__ == '__main__':
    unittest.main()
