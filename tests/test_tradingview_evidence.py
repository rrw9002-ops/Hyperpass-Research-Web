"""Evidence metadata tests using synthetic report fixtures; no model/CDP calls."""
import copy
import unittest

from hyperpass.tradingview_jobs import TradingViewJobs, _milliseconds_utc


def fixture():
    return {
        'id':'saved-job-fixture','request':{'code':'strategy("Fixture only")'},
        'result':{
            'target_id':'chart-connection-fixture','study_id':'strategy-fixture',
            'previous_source':'private previous editor draft',
            'completed_at':'2030-12-31T12:00:00+00:00',
            'report':{
                'study_id':'strategy-fixture','currency':'USD','metric_units':'percentage_points',
                'metrics':{'net_profit_percent':125,'max_drawdown_percent':7.5,'percent_profitable':40,'total_trades':1000,'profit_factor':2.5},
                'performance':{'all':{'netProfitPercent':1.25,'percentProfitable':.4,'marginCalls':0},'maxStrategyDrawDownPercent':.075},
                'settings':{'dateRange':{'backtest':{'from':1577836800000,'to':1609459200000},'trade':{'from':1580428800000,'to':1609372800000}}},
                'trades':[{'e':{'tm':1577836800000+i*86400000,'b':i},'x':{'tm':1577923200000+i*86400000,'b':i+1}} for i in range(500)],
                'orders':[{'time_index':i,'price':100} for i in range(500)],
                'equity':[], 'total_report_trades':1000,'total_orders':2000,
            },
        },
    }


class EvidenceMetadataTests(unittest.TestCase):
    def test_metadata_preserves_raw_values_and_does_not_mutate_saved_job(self):
        job=fixture(); original=copy.deepcopy(job)
        evidence=TradingViewJobs.evidence(job)
        self.assertEqual(job,original)
        self.assertNotIn('previous_source',evidence)
        self.assertEqual(evidence['report']['metrics'],original['result']['report']['metrics'])
        self.assertEqual(evidence['report']['performance'],original['result']['report']['performance'])
        self.assertEqual(evidence['report']['settings'],original['result']['report']['settings'])
        units=evidence['unit_conventions']
        self.assertEqual(units['metrics_percentage_unit'],'percentage_points')
        self.assertEqual(units['raw_performance_percentage_unit'],'fraction')
        self.assertEqual(units['raw_to_display_percentage_multiplier'],100)
        self.assertIn('profit_factor',units['dimensionless_ratio_fields'])

    def test_saved_returned_and_provider_totals_remain_distinct(self):
        evidence=TradingViewJobs.evidence(fixture()); scope=evidence['source_scope']
        self.assertEqual(scope['reported_total_trades'],1000)
        self.assertEqual(scope['reported_total_orders'],2000)
        self.assertEqual(scope['arrays']['trades']['stored_rows'],500)
        self.assertEqual(scope['arrays']['trades']['supplied_rows'],20)
        self.assertEqual(scope['arrays']['equity']['supplied_rows'],0)
        self.assertEqual(evidence['report']['orders'][0]['time_index'],480)
        self.assertEqual(evidence['report']['orders'][-1]['time_index'],499)
        self.assertEqual(scope['saved_job_id'],'saved-job-fixture')
        self.assertEqual(scope['chart_connection_target_id'],'chart-connection-fixture')
        self.assertEqual(scope['strategy_study_id'],'strategy-fixture')

    def test_millisecond_date_summaries_do_not_use_completion_time_or_tail_start(self):
        evidence=TradingViewJobs.evidence(fixture()); dates=evidence['date_range_summary']
        self.assertEqual(dates['source_unit'],'unix_epoch_milliseconds')
        self.assertEqual(dates['backtest']['from_utc'],'2020-01-01T00:00:00+00:00')
        self.assertEqual(dates['backtest']['to_utc'],'2021-01-01T00:00:00+00:00')
        self.assertEqual(dates['trade']['from_utc'],'2020-01-31T00:00:00+00:00')
        self.assertEqual(dates['trade']['to_utc'],'2020-12-31T00:00:00+00:00')
        self.assertEqual(evidence['completed_at'],'2030-12-31T12:00:00+00:00')
        self.assertIn('report.orders[].time_index',evidence['time_conventions'])
        self.assertIn('report.trades[].e.tm',evidence['time_conventions'])

    def test_invalid_dates_are_unknown_and_seconds_are_not_guessed(self):
        for value in [True,None,'2020-01-01',float('inf'),float('nan'),10**1000]:
            with self.subTest(value=type(value).__name__):self.assertIsNone(_milliseconds_utc(value))
        self.assertEqual(_milliseconds_utc(1000),'1970-01-01T00:00:01+00:00')
        self.assertEqual(_milliseconds_utc(-86400000),'1969-12-31T00:00:00+00:00')
        job=fixture(); job['result']['report']['settings']['dateRange']['backtest']['from']='unknown'
        evidence=TradingViewJobs.evidence(job)
        self.assertIsNone(evidence['date_range_summary']['backtest']['from_utc'])
        self.assertEqual(evidence['report']['settings']['dateRange']['backtest']['from'],'unknown')

    def test_observed_fills_use_stored_rows_before_excerpt_not_reported_boundaries(self):
        job=fixture(); report=job['result']['report']
        report['trades']=report['trades'][:25]
        # Both extrema are outside the last-20-row excerpt; row order is not time order.
        report['trades'][1]['x']['tm']=1609459200000
        report['total_report_trades']=25;report['metrics']['total_trades']=25
        original=copy.deepcopy(job)
        evidence=TradingViewJobs.evidence(job); observed=evidence['observed_trade_times']
        self.assertEqual(observed['scope'],'stored_trade_rows_before_excerpt')
        self.assertEqual(observed['first_entry_utc'],'2020-01-01T00:00:00+00:00')
        self.assertEqual(observed['latest_exit_utc'],'2021-01-01T00:00:00+00:00')
        self.assertEqual(observed['coverage'],'matches_reported_counts')
        self.assertEqual((observed['stored_rows'],observed['valid_entry_timestamps'],observed['valid_exit_timestamps']),(25,25,25))
        self.assertEqual(evidence['report']['trades'],report['trades'][-20:])
        reported=evidence['date_range_summary']['trade']
        self.assertEqual(reported['meaning'],'reported_trade_range_not_observed_fills')
        self.assertNotEqual(reported['from_utc'],observed['first_entry_utc'])
        self.assertNotEqual(reported['to_utc'],observed['latest_exit_utc'])
        self.assertEqual(job,original)

    def test_observed_time_coverage_never_promotes_partial_or_unknown_storage_to_full(self):
        for row_count,total,expected in ((500,500,'matches_reported_counts'),(1000,500,'partial'),
                                          (500,1000,'partial'),(499,500,'inconsistent'),
                                          (None,None,'unknown'),(True,'500','unknown'),
                                          (500,'invalid','unknown'),('invalid',500,'unknown'),
                                          (1000,'invalid','partial')):
            with self.subTest(row_count=row_count,total=total):
                job=fixture(); report=job['result']['report']
                report['total_report_trades']=row_count;report['metrics']['total_trades']=total
                evidence=TradingViewJobs.evidence(job); observed=evidence['observed_trade_times']
                self.assertEqual(observed['coverage'],expected)
                self.assertEqual(observed['stored_rows'],500)
                self.assertEqual(observed['reported_trade_rows'],row_count)
                self.assertEqual(observed['reported_total_trades'],total)
                self.assertEqual(observed['first_entry_utc'],'2020-01-01T00:00:00+00:00')
                self.assertEqual(len(evidence['report']['trades']),20)

    def test_observed_fills_ignore_invalid_rows_and_timestamps_without_inventing_dates(self):
        job=fixture(); report=job['result']['report']
        report['trades']=[None,{}, {'e':{'tm':True},'x':{'tm':'2020-01-01'}},
                          {'e':{'tm':0},'x':{'tm':1000}},
                          {'e':{'tm':-86400000},'x':{'tm':float('inf')}},
                          {'e':{'tm':float('nan')},'x':{'tm':10**1000}},
                          {'e':[],'x':None}]
        observed=TradingViewJobs.evidence(job)['observed_trade_times']
        self.assertEqual(observed['stored_rows'],7)
        self.assertEqual(observed['coverage'],'partial')
        self.assertEqual((observed['valid_entry_timestamps'],observed['valid_exit_timestamps']),(2,1))
        self.assertEqual(observed['first_entry_utc'],'1969-12-31T00:00:00+00:00')
        self.assertEqual(observed['latest_exit_utc'],'1970-01-01T00:00:01+00:00')
        for rows,expected,stored in (([], 'partial',0),(None,'not_provided',None)):
            report['trades']=rows
            empty=TradingViewJobs.evidence(job)['observed_trade_times']
            self.assertEqual(empty['coverage'],expected)
            self.assertEqual(empty['stored_rows'],stored)
            self.assertIsNone(empty['first_entry_utc'])
            self.assertIsNone(empty['latest_exit_utc'])

    def test_extrema_and_gap_notes_do_not_pair_or_rewrite_reported_values(self):
        job=fixture(); report=job['result']['report']
        report['performance']['all'].update(largestLosTrade=900,largestLosTradePercent=.8)
        report['trades']=[{'e':{'tm':0},'x':{'tm':1000},'tp':{'v':-900,'p':-.3}},
                          {'e':{'tm':2000},'x':{'tm':3000},'tp':{'v':-80,'p':-.8}}]
        original=copy.deepcopy(job)
        evidence=TradingViewJobs.evidence(job);risk=evidence['risk_context']
        self.assertIn('동일 거래 ID',risk['extrema_rule'])
        self.assertIn('별도 집계',risk['extrema_rule'])
        self.assertIn('slippage=0',risk['gap_execution_rule'])
        self.assertEqual(risk['broker_emulator_reference'],'https://www.tradingview.com/pine-script-docs/concepts/strategies/#broker-emulator')
        self.assertEqual(evidence['report']['performance'],report['performance'])
        self.assertEqual(evidence['report']['trades'],report['trades'])
        self.assertEqual(job,original)

    def test_margin_calls_is_an_observation_without_invented_risk_verdict(self):
        job=fixture(); evidence=TradingViewJobs.evidence(job)
        self.assertEqual(evidence['risk_context']['margin_calls_observed'],0)
        self.assertEqual(evidence['risk_context']['margin_calls_source'],'report.performance.all.marginCalls')
        self.assertNotIn('leverage',evidence['risk_context'])
        del job['result']['report']['performance']['all']['marginCalls']
        del job['result']['report']['metric_units']
        missing=TradingViewJobs.evidence(job)
        self.assertIsNone(missing['risk_context']['margin_calls_observed'])
        self.assertEqual(missing['unit_conventions']['metrics_percentage_unit'],'not_declared')

    def test_source_truncation_is_explicit_and_original_code_is_preserved(self):
        job=fixture(); job['request']['code']='x'*25000
        evidence=TradingViewJobs.evidence(job)
        self.assertTrue(evidence['strategy_source_truncated'])
        self.assertEqual(evidence['source_scope']['strategy_source_characters'],{'stored':25000,'supplied':24000})
        self.assertEqual(len(job['request']['code']),25000)

    def test_only_matching_strategy_settings_reach_ai_while_saved_chart_stays_intact(self):
        job=fixture()
        selected={'id':'strategy-fixture','name':'Selected','inputs':[{'id':'in_0','value':1000,'name':'Initial capital'}]}
        other={'id':'unrelated-strategy','name':'Other','inputs':[{'id':'in_0','value':999999,'name':'Initial capital'}]}
        job['result']['chart']={'symbol':'FIXTURE','timeframe':'1D','studies':[other,selected,{'id':'rsi','name':'RSI'}]}
        job['result']['before']={'symbol':'OLD_FIXTURE','studies':[other]}
        original=copy.deepcopy(job)
        evidence=TradingViewJobs.evidence(job)
        self.assertEqual(job,original)
        self.assertEqual(evidence['chart'],{'symbol':'FIXTURE','timeframe':'1D','studies':[selected]})
        self.assertNotIn('before',evidence)
        self.assertEqual(evidence['report']['metrics'],original['result']['report']['metrics'])
        self.assertEqual(evidence['report']['performance'],original['result']['report']['performance'])
        self.assertEqual(evidence['strategy_source'],job['request']['code'])
        scope=evidence['source_scope']
        self.assertEqual(scope['selected_study_context'],{'study_id':'strategy-fixture','status':'matched','stored_studies':3,'supplied_studies':1})
        self.assertEqual({x['path'] for x in scope['omitted_context']},{'before','chart.studies'})

    def test_missing_ambiguous_or_conflicting_strategy_id_does_not_borrow_other_settings(self):
        for mode in ('missing','duplicate','conflict','no_id'):
            job=fixture(); matching={'id':'strategy-fixture','name':'Same display name'}
            job['result']['chart']={'studies':[{'id':'other','name':'Same display name'}]}
            if mode=='duplicate':job['result']['chart']['studies']=[matching,copy.deepcopy(matching)]
            if mode=='conflict':
                job['result']['chart']['studies']=[matching]
                job['result']['study_id']='different-result-id'
            if mode=='no_id':
                del job['result']['study_id'];del job['result']['report']['study_id']
                job['result']['chart']['studies']=[{'name':'Same display name'}]
            with self.subTest(mode=mode):
                evidence=TradingViewJobs.evidence(job)
                self.assertEqual(evidence['chart']['studies'],[])
                self.assertNotEqual(evidence['source_scope']['selected_study_context']['status'],'matched')

    def test_empty_equity_is_unavailable_in_saved_job_not_just_analysis_excerpt(self):
        job=fixture(); original=copy.deepcopy(job)
        evidence=TradingViewJobs.evidence(job)
        availability=evidence['source_scope']['equity_availability']
        self.assertEqual(availability['status'],'unavailable')
        self.assertEqual(availability['stored_rows'],0)
        self.assertFalse(availability['available_in_saved_job'])
        self.assertFalse(availability['saved_job_has_additional_rows'])
        self.assertEqual(evidence['report']['equity'],[])
        self.assertEqual(job,original)

    def test_present_and_missing_equity_are_reported_without_inventing_curve(self):
        job=fixture(); job['result']['report']['equity']=[{'value':i} for i in range(30)]
        evidence=TradingViewJobs.evidence(job)
        availability=evidence['source_scope']['equity_availability']
        self.assertEqual(availability['status'],'available')
        self.assertTrue(availability['available_in_saved_job'])
        self.assertTrue(availability['saved_job_has_additional_rows'])
        self.assertEqual((availability['stored_rows'],availability['supplied_rows']),(30,20))
        self.assertEqual(evidence['report']['equity'],job['result']['report']['equity'][-20:])
        del job['result']['report']['equity']
        missing=TradingViewJobs.evidence(job)['source_scope']['equity_availability']
        self.assertEqual(missing['status'],'not_provided')
        self.assertIsNone(missing['stored_rows'])
        self.assertFalse(missing['available_in_saved_job'])

    def test_pine_execution_options_have_distinct_documented_meanings(self):
        job=fixture(); original=copy.deepcopy(job)
        evidence=TradingViewJobs.evidence(job)
        self.assertEqual(evidence['unit_conventions']['pine_slippage_unit'],'ticks')
        risk=evidence['risk_context']
        self.assertEqual(risk['standard_ohlc_setting']['parameter'],'fill_orders_on_standard_ohlc')
        self.assertEqual(risk['standard_ohlc_setting']['applies_to_chart_type'],'heikin_ashi')
        self.assertEqual(risk['bar_magnifier_setting']['parameter'],'use_bar_magnifier')
        self.assertEqual(risk['bar_magnifier_setting']['function'],'lower_timeframe_fill_prices')
        self.assertEqual(risk['strategy_properties_reference'],'https://www.tradingview.com/support/solutions/43000628599-strategy-properties/')
        self.assertEqual(evidence['report']['metrics'],original['result']['report']['metrics'])
        self.assertEqual(evidence['report']['performance'],original['result']['report']['performance'])
        self.assertEqual(job,original)


if __name__=='__main__':unittest.main()
