import copy
from datetime import datetime, timedelta, timezone
import math
import unittest

from hyperpass.chart_lab import (ChartLabError, analyze_chart, normalize_candles,
                                validate_settings, sma, ema, rsi, indicators,
                                strategy_signals, _simulate)


def packet(prices, volume=1000):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return {'provider':'tradingview','symbol':'TEST','timeframe':'1D','currency':'USD',
            'source_url':'https://www.tradingview.com/', 'as_of':(start+timedelta(days=len(prices)-1)).isoformat(),
            'records':[{'timestamp':(start+timedelta(days=i)).isoformat(),
                        'open':p, 'high':p+1, 'low':max(.001,p-1), 'close':p, 'volume':volume}
                       for i,p in enumerate(prices)]}


class ChartLabTests(unittest.TestCase):
    def test_normalization_handles_time_formats_and_retains_missing_volume(self):
        source = packet([10,11,12])
        source['records'][0]['timestamp'] = 1577836800
        source['records'][1]['timestamp'] = '2020-01-02'
        source['records'][2]['timestamp'] = 1578009600000
        source['records'][1]['volume'] = None
        bars, warnings = normalize_candles(source)
        self.assertEqual(bars[2]['time'],1578009600)
        self.assertIsNone(bars[1]['volume'])
        self.assertEqual(len(warnings),2)
        self.assertEqual(source['records'][0]['timestamp'],1577836800)

    def test_invalid_data_is_rejected_instead_of_filled_or_sorted(self):
        bad = []
        rows = packet([10,11,12]); rows['records'][1]['close'] = None; bad.append(rows)
        rows = packet([10,11,12]); rows['records'][1]['timestamp'] = rows['records'][0]['timestamp']; bad.append(rows)
        rows = packet([10,11,12]); rows['records'].reverse(); bad.append(rows)
        rows = packet([10,11,12]); rows['records'][1]['high'] = 8; bad.append(rows)
        rows = packet([10,11,12]); rows['records'][1]['close'] = math.inf; bad.append(rows)
        rows = packet([10,11,12]); rows['records'][1]['volume'] = -1; bad.append(rows)
        rows = packet([10,11,12]); rows['records'][1]['symbol'] = 'OTHER'; bad.append(rows)
        rows = packet([10,11,12]); rows['records'][1]['timestamp'] = 'unknown'; bad.append(rows)
        bad += [{'records':[{'price':10}],'provider':'fmp'}, {'error':'failed','records':packet([10,11])['records']}]
        for source in bad:
            with self.subTest(source=source), self.assertRaises(ChartLabError): normalize_candles(source)

    def test_unknown_options_and_unsafe_or_inconsistent_parameters_fail(self):
        for options in ({'strategy':'arbitrary-python'}, {'fast_period':True}, {'slow_period':10},
                        {'fee_bps':-1}, {'initial_capital':math.nan}, {'indicators':['unknown']},
                        {'slippage_mode':'ticks'}, {'start_date':'2025-01-02','end_date':'2025-01-01'},
                        {'start_date':'2025-2-1'}, {'train_fraction':1}, {'script':'evil'}):
            with self.subTest(options=options), self.assertRaises(ChartLabError): validate_settings(options)

    def test_missing_price_error_names_row_and_observation_date(self):
        source=packet([10,11,12])
        source['records'][1]['open']=None
        with self.assertRaises(ChartLabError) as context:
            normalize_candles(source)
        message=str(context.exception)
        for expected in ('2번째 봉','2020-01-02','open','보간'):
            self.assertIn(expected,message)

    def test_indicator_known_values_and_warmup_are_not_backfilled(self):
        self.assertEqual(sma([1,2,3,4,5],3),[None,None,2,3,4])
        self.assertEqual(ema([1,2,3,4,5],3),[None,None,2,3,4])
        self.assertEqual(rsi([1,2,3,4,5],3),[None,None,None,100,100])
        self.assertEqual(rsi([5,4,3,2,1],3),[None,None,None,0,0])
        self.assertEqual(rsi([5,5,5,5,5],3),[None,None,None,50,50])
        candles, _ = normalize_candles(packet([10]*70))
        settings=validate_settings()
        result=indicators(candles,settings)
        self.assertEqual(result['bb_upper'][-1],10)
        self.assertEqual(result['bb_lower'][-1],10)
        self.assertEqual(result['macd'][-1],0)
        self.assertEqual(result['atr'][-1],2)
        self.assertIsNone(result['sma_slow'][58])

    def test_future_changes_do_not_change_past_indicators_or_signals(self):
        prices=[100+i*.15+5*math.sin(i/8) for i in range(180)]
        prefix,_=normalize_candles(packet(prices[:110]))
        altered,_=normalize_candles(packet(prices[:110]+[1000]*70))
        settings=validate_settings()
        a,b=indicators(prefix,settings),indicators(altered,settings)
        for key in a: self.assertEqual(a[key],b[key][:110],key)
        for mode in ('trend_breakout','mean_reversion','sma_cross'):
            settings['strategy']=mode
            left=strategy_signals(prefix,a,settings)
            right=strategy_signals(altered,b,settings)
            self.assertEqual(left[0],right[0][:110])
            self.assertEqual(left[1],right[1][:110])

    def test_breakout_excludes_current_high(self):
        source=packet([10,10,10,11,12,30])
        source['records'][-1]['high']=100
        candles,_=normalize_candles(source)
        settings=validate_settings({'fast_period':2,'slow_period':3,'breakout_period':2})
        series=indicators(candles,settings)
        entry,_=strategy_signals(candles,series,settings)
        self.assertTrue(entry[-1])

    def test_close_signals_fill_next_open_with_costs_and_no_same_bar_fill(self):
        source=packet([10,12,15,14])
        source['records'][1].update(open=11,low=10)
        candles,_=normalize_candles(source)
        settings=validate_settings({'fee_bps':10,'slippage_bps':100,'initial_capital':1000})
        result=_simulate(candles,[True,False,False,False],[False,False,True,False],settings,0,3)
        trade=result['trades'][0]
        self.assertEqual(trade['entry_index'],1)
        self.assertEqual(trade['exit_index'],3)
        self.assertAlmostEqual(trade['entry_price'],11*1.01)
        self.assertAlmostEqual(trade['exit_price'],14*.99)
        self.assertGreater(trade['fees'],0)
        self.assertAlmostEqual(result['metrics']['final_equity'],1000+trade['pnl'])
        self.assertLessEqual(result['metrics']['max_drawdown_pct'],0)

    def test_no_pyramiding_and_last_bar_signal_remains_unfilled(self):
        candles,_=normalize_candles(packet([10,11,12,13]))
        settings=validate_settings({'fee_bps':0,'slippage_bps':0,'initial_capital':1000})
        result=_simulate(candles,[True]*4,[False]*4,settings,0,3)
        self.assertEqual(len(result['orders']),1)
        self.assertEqual(result['metrics']['closed_trades'],0)
        self.assertIsNotNone(result['open_position'])
        self.assertAlmostEqual(result['metrics']['final_equity'],1000/11*13)
        last_only=_simulate(candles,[False,False,False,True],[False]*4,settings,0,3)
        self.assertEqual(last_only['orders'],[])
        self.assertEqual(last_only['metrics']['total_return_pct'],0)
        self.assertEqual(last_only['unexecuted_last_signal']['side'],'buy')

    def test_date_exit_uses_first_open_after_window_and_does_not_force_last_close(self):
        candles,_=normalize_candles(packet([10,11,12,13,14]))
        settings=validate_settings({'fee_bps':0,'slippage_bps':0,'initial_capital':1000,'end_date':'2020-01-03'})
        result=_simulate(candles,[True]*5,[False]*5,settings,0,4)
        self.assertEqual(result['trades'][0]['exit_index'],3)
        self.assertEqual(result['trades'][0]['exit_reason'],'end_date')
        result=_simulate(candles[:3],[True]*3,[False]*3,settings,0,2)
        self.assertIsNotNone(result['open_position'])
        self.assertEqual(result['trades'],[])

    def test_tick_slippage_is_explicit_and_zero_price_fills_rejected(self):
        candles,_=normalize_candles(packet([10,11,12,13]))
        settings=validate_settings({'slippage_mode':'ticks','slippage_ticks':2,'tick_size':.5,'fee_bps':0})
        result=_simulate(candles,[True,False,False,False],[False,False,True,False],settings,0,3)
        self.assertEqual(result['trades'][0]['entry_price'],12)
        self.assertEqual(result['trades'][0]['exit_price'],12)
        settings['tick_size']=100
        with self.assertRaises(ChartLabError): _simulate(candles,[True,False,False,False],[False,False,True,False],settings,0,3)

    def test_full_result_has_chronological_holdout_and_independent_cash_start(self):
        prices=[100+i*.05+15*math.sin(i/12) for i in range(360)]
        result=analyze_chart(packet(prices),{'strategy':'mean_reversion','indicators':['sma','rsi']})
        self.assertEqual(set(result['indicators']),{'sma_fast','sma_slow','rsi'})
        backtest=result['backtest']; holdout=backtest['out_of_sample']
        self.assertIsNotNone(holdout)
        self.assertLess(backtest['in_sample']['metrics']['to'],holdout['metrics']['from'])
        for order in holdout['orders']:
            self.assertGreaterEqual(order['signal_index'],backtest['split_index'])
            self.assertGreater(order['execution_index'],order['signal_index'])
        self.assertEqual(holdout['equity'][0]['equity'],result['settings']['initial_capital'])
        self.assertEqual(result['evidence_summary']['backtest_metrics'],backtest['metrics'])
        self.assertEqual(backtest['cost_stress']['multiplier'],2)
        self.assertLessEqual(backtest['cost_stress']['metrics']['final_equity'],backtest['metrics']['final_equity'])
        self.assertEqual(len(result['provenance']['ohlcv_sha256']),64)

    def test_insufficient_strategy_history_is_explicit_but_chart_only_works(self):
        with self.assertRaises(ChartLabError): analyze_chart(packet([10+i for i in range(30)]))
        result=analyze_chart(packet([10+i for i in range(30)]),{'strategy':'none'})
        self.assertIsNone(result['backtest'])
        self.assertIsNone(result['indicators']['sma_slow'][-1])
        self.assertEqual(len(result['candles']),30)

    def test_requested_dates_do_not_silently_change_to_other_periods(self):
        source=packet([100+i for i in range(100)])
        for options in ({'start_date':'2025-01-01'},{'end_date':'2019-01-01'}):
            with self.assertRaises(ChartLabError): analyze_chart(source,options)
        selected=analyze_chart(source,{'start_date':'2020-03-01','end_date':'2020-03-20'})
        self.assertEqual(selected['backtest']['metrics']['from'][:10],'2020-03-01')
        self.assertEqual(selected['backtest']['metrics']['to'][:10],'2020-03-21')
        partial=analyze_chart(source,{'start_date':'2019-01-01','end_date':'2021-01-01'})
        warning=' '.join(partial['warnings'])
        self.assertIn('요청 시작일보다',warning)
        self.assertIn('요청 종료일에 도달하지',warning)


if __name__ == '__main__': unittest.main()
