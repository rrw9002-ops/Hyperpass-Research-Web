import json
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from hyperpass import market_backtest as engine, market_rules


def plan(factors=None, **options):
    code = {'version':1, 'entry':'ranked', 'exit':'rank_drop',
            'factors':factors or [{'field':'close', 'order':'asc'}]}
    return {'market':'US', 'mode':'custom', 'symbols':['AAA','BBB'], 'max_positions':1,
            'settings':{'start_date':'2024-01-29', 'end_date':'2024-02-07',
                        'strategy':'none', 'initial_capital':1000, 'fee_bps':0, 'slippage_bps':0},
            'strategy_code':json.dumps(code), **options}


def bar(day, price, volume=10, dividend=0, close=None):
    close = price if close is None else close
    return [day,price,max(price,close),min(price,close),close,volume,dividend]


def simulate(payload, histories):
    def prices(symbol, start, end, cache=None, *, with_events=False):
        rows = histories.get(symbol) or histories['AAA']
        return 'USD', [row if with_events else row[:5] for row in rows]
    names = {s:s for s in histories}
    with patch.object(engine, 'resolve_universe', return_value=(names, 'fixture')), patch.object(engine, 'read_prices', side_effect=prices):
        result = engine.run_backtest(payload)
    json.dumps(result, allow_nan=False)
    return result


class MarketConditionsTests(unittest.TestCase):
    def test_code_validation_is_strict_and_round_trips(self):
        request = plan()
        opt = engine.validate_request(request)
        self.assertEqual(engine.validate_request(opt), opt)
        self.assertEqual(opt['strategy_code']['factors'][0]['order'], 'asc')
        for code in (None, '__import__("os")', {'field':'volume'},
                     dict(opt['strategy_code'], factors=[{'field':'per','order':'x'}]),
                     dict(opt['strategy_code'], version=True),
                     dict(opt['strategy_code'], factors=[{'field':'per','order':'asc','min':True}]),
                     dict(opt['strategy_code'], factors=[{'field':'volume','order':'asc','min':2,'max':1}])):
            with self.subTest(code=code), self.assertRaises(ValueError):
                engine.validate_request(dict(request,strategy_code=code))
        old = dict(request['settings'],start_date='2015-01-01',end_date='2025-12-31')
        self.assertEqual(engine.validate_request(dict(request,settings=old))['settings']['start_date'], '2015-01-01')

    def test_per_filters_priority_and_filing_date(self):
        days = ['2024-01-29','2024-01-30','2024-01-31','2024-02-01','2024-02-02']
        symbols = {'AAA':[bar(d,20) for d in days], 'BBB':[bar(d,30) for d in days]}
        fundamentals = [{'symbol':'AAA','available_date':'2023-11-01','eps':2},
                        {'symbol':'BBB','available_date':'2023-11-01','eps':2},
                        {'symbol':'BBB','available_date':'2024-01-30','eps':6}]
        filters = [{'field':'per','order':'asc','min':1,'max':15}, {'field':'close','order':'desc'}]
        result = simulate(plan(filters,fundamentals=fundamentals),symbols)
        orders = [(o['symbol'],o['side'],o['date']) for o in result['orders']]
        self.assertEqual(orders,[('AAA','buy','2024-01-30'),('AAA','sell','2024-02-01'),('BBB','buy','2024-02-01')])
        self.assertEqual(result['orders'][2]['signal_date'],'2024-01-31')
        self.assertEqual(result['orders'][2]['factors'],{'per':5,'close':30})
        result = simulate(plan(list(reversed(filters)),fundamentals=fundamentals),symbols)
        self.assertEqual(result['orders'][0]['symbol'],'BBB')

    def test_per_without_usable_history_and_stale_eps(self):
        with patch.object(engine, 'resolve_universe') as universe, self.assertRaisesRegex(ValueError,'EPS'):
            engine.run_backtest(plan([{'field':'per','order':'asc'}]))
        universe.assert_not_called()
        with self.assertRaisesRegex(ValueError,'관측 가능한 조건값'):
            simulate(plan([{'field':'per','order':'asc'}],fundamentals=[{'symbol':'AAA','available_date':'2020-01-01','eps':1}]),
                     {'AAA':[bar('2024-01-30',1),bar('2024-01-31',1)]})

    def test_missing_volume_or_halted_session_does_not_liquidate_by_rank(self):
        days = ['2024-01-29','2024-01-30','2024-01-31','2024-02-01','2024-02-02']
        a = [bar(d,10,v) for d,v in zip(days,[50,None,0,1,1]) if d != '2024-01-31']
        b = [bar(d,10,25) for d in days]
        r = simulate(plan([{'field':'volume','min':10,'order':'desc'}]),{'AAA':a,'BBB':b})
        self.assertEqual([o['date'] for o in r['orders']], ['2024-01-30','2024-02-02','2024-02-02'])
        self.assertEqual(r['coverage']['factor_data']['missing_observations'],1)

    def test_monthly_contribution_and_ex_date_entitlement(self):
        dates = ['2024-01-29','2024-01-30','2024-01-31','2024-02-01','2024-02-02']
        rows = [bar(d,100,10,div) for d,div in zip(dates,[0,9,1,0,0])]
        # The ex-date on the first purchase belongs to the previous holder.
        result = simulate(plan(monthly_contribution=100,dividends=True),{'AAA':rows})
        m = result['metrics']
        self.assertAlmostEqual(m['dividend_income'],10)
        self.assertAlmostEqual(m['ending_equity'],1110)
        self.assertAlmostEqual(m['total_return_pct'],1)
        self.assertEqual(m['contributions'],100)
        self.assertEqual(m['net_profit'],10)
        self.assertAlmostEqual(m['max_drawdown_pct'],0)
        self.assertAlmostEqual(result['benchmark']['ending_equity'],1100)
        self.assertAlmostEqual(result['benchmark']['return_pct'],0)
        self.assertAlmostEqual(result['open_positions'][0]['quantity'],11.1)

    def test_deposit_does_not_mask_drawdown(self):
        rows = [bar('2024-01-29',10),bar('2024-01-30',10),bar('2024-02-01',10,close=8),bar('2024-02-02',8)]
        result = simulate(plan(monthly_contribution=1000),{'AAA':rows})
        self.assertAlmostEqual(result['metrics']['ending_equity'],1600)
        self.assertAlmostEqual(result['metrics']['max_drawdown_pct'],-20)
        self.assertAlmostEqual(result['metrics']['total_return_pct'],-20)

    def test_annual_selection_in_march_and_reference_months(self):
        days = ['2024-02-28','2024-02-29','2024-03-01','2024-03-04','2024-04-01']
        payload = plan(rebalance={'frequency':'annual','month':3})
        payload['settings']['end_date'] = days[-1]
        result = simulate(payload,{'AAA':[bar(d,100) for d in days]})
        self.assertEqual([(o['signal_date'], o['date']) for o in result['orders']], [('2024-03-01','2024-03-04')])
        self.assertTrue(market_rules.scheduled('2024-06-03','2024-05-31',{'frequency':'quarterly','month':3}))
        self.assertFalse(market_rules.scheduled('2024-07-01','2024-06-28',{'frequency':'quarterly','month':3}))

    def test_momentum_percentage_is_backward_looking(self):
        data = [bar((date(2024,1,29)+timedelta(i)).isoformat(),p) for i,p in enumerate([10,12,15,90])]
        opts = engine.validate_request(plan([{'field':'momentum','min':49,'max':51,'order':'desc'}],lookback=2))
        selection = engine._prepare(data,opts)
        self.assertEqual(selection.entries,[(date(2024,1,31).toordinal(),(-50.0,),False)])
