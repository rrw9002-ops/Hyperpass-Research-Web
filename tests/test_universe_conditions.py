import json
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

from hyperpass import market_factors as factors, market_prices as prices, market_universe as universe


class UniverseTests(unittest.TestCase):
    def test_exchange_industry_intersection_and_classification_coverage(self):
        kospi = ((('KRX:005930','삼성전자','005930.KS','ST'),('KRX:105560','KB금융','105560.KS','ST'),
                  ('KRX:123456','미분류','123456.KS','ST')),True)
        classes = {'as_of':'2025-11-22','by_symbol':{'005930':('Tech','Chip'),'105560':('Finance','Bank')}}
        with patch.object(prices.symbol_search,'kr_listings',return_value=kospi) as listings, \
             patch.object(universe,'classification',return_value=classes):
            members, source = prices.resolve_universe('market','KR',[],{'exchanges':['KOSPI'],'industries':['Chip']})
            self.assertEqual(members,{'005930.KS':'삼성전자'})
            self.assertIn('분류 미확인 1종목',source)
            listings.assert_called_once_with('kospi')
            members, _ = prices.resolve_universe('custom','KR',['005930.KS','105560.KS'],
                                                  {'sectors':['Finance'],'industries':['Chip']})
            self.assertEqual(set(members),{'005930.KS','105560.KS'})
            with self.assertRaisesRegex(prices.MarketBacktestError, '종목이 없습니다'):
                prices.resolve_universe('single','KR',['005930.KS'],{'industries':['Bank']})

    def test_us_directory_uses_exchange_field_and_filters_share_classes(self):
        raw = (b'ACT Symbol|Security Name|Exchange|ETF|Test Issue\nBRK.B|Class B Common Stock|N|N|N\n'
               b'ABC|Another Common Stock|A|N|N\nXYZ|Example ETF|P|Y|N\n')
        with patch.object(prices,'_get',return_value=raw) as get:
            members, source = prices.resolve_universe('market','US',[],{'exchanges':['NYSE']})
            self.assertEqual(list(members),['BRK-B'])
            get.assert_called_once_with(prices.US_DIR+'otherlisted.txt',4_000_000)
            self.assertIn('NYSE',source)
        with self.assertRaises(ValueError):
            prices.resolve_universe('market','KR',[],{'exchanges':['NASDAQ']})

    def test_unavailable_industry_never_falls_back_to_unfiltered_universe(self):
        with patch.object(universe,'classification',side_effect=prices.MarketBacktestError('연결 오류')):
            opt = universe.universe_options('US')
            self.assertEqual(opt['sectors'],[])
            self.assertIn('연결 오류',opt['warning'])
            self.assertIn('NASDAQ',[e['id'] for e in opt['exchanges']])
            with self.assertRaisesRegex(ValueError,'연결 오류'):
                prices.resolve_universe('single','US',['NVDA'],{'sectors':['Technology']})

    def test_pine_uses_verified_exchange_symbol_and_skips_unknown_us_venues(self):
        with patch.object(universe,'classification',return_value={'targets':{'BRK-B':'NYSE:BRK.B','ACC':'AMEX:ACC'}}):
            us, _ = prices.pine_universe('custom','US',['BRK-B','ACC','NOTA'])
        self.assertEqual(us['BRK-B']['target_symbol'],'NYSE:BRK.B')
        self.assertEqual(us['ACC']['target_symbol'],'AMEX:ACC')
        self.assertIsNone(us['NOTA']['target_symbol'])
        kr,_ = prices.pine_universe('single','KR',['005930.KS'])
        self.assertEqual(kr['005930.KS']['target_symbol'],'KRX:005930')

    def test_missing_and_invalid_bars_have_dates_and_dividend_cache_is_separate(self):
        raw = {'meta':{'symbol':'AAA','currency':'USD'},'timestamp':[1675209600+i*86400 for i in range(4)],
               'indicators':{'quote':[{'open':[1,3,2,3],'high':[2,7,3,4],'low':[.5,3,1,2],
                                       'close':[2,2,2,3],'volume':[3,4,None,0]}]},
               'events':{'dividends':{'x':{'amount':.42,'date':1675382400}}}}
        with patch.object(prices,'_get',return_value=json.dumps({'chart':{'result':[raw]}}).encode()) as get, \
             tempfile.TemporaryDirectory() as cache:
            start,end=date(2023,2,1),date(2023,2,4)
            _,basic=prices.read_prices('AAA',start,end,cache)
            _,extra=prices.read_prices('AAA',start,end,cache,with_events=True)
            self.assertEqual(get.call_count,2)
            self.assertFalse(any('events=div' in str(x) for x in get.call_args_list[:1]))
            self.assertIn('events=div',get.call_args.args[0])
            self.assertEqual(basic.omitted,extra.omitted)
            self.assertEqual(extra.omitted,['2023-02-02'])
            self.assertEqual(extra[1],['2023-02-03',2,3,1,2,None,.42])
            self.assertEqual(extra[-1][-2:],[0,0.])
            _,again=prices.read_prices('AAA',date(2023,2,3),end,cache,with_events=True)
            self.assertEqual(again.omitted,[])
            self.assertEqual(again[0],extra[1])
            self.assertEqual(get.call_count,2)

    def test_dated_eps_import_handles_korean_listings_zero_earnings_and_restatements(self):
        data=factors.import_fundamentals('KR','\ufeffsymbol,available_date,eps\n005930.KS,2024-04-02,1200\n005930.KS,2024-03-30,0\n')
        self.assertEqual(data['symbol_count'],1)
        self.assertEqual(data['row_count'],2)
        self.assertEqual([r['eps'] for r in data['fundamentals']],[0,1200])
        us=factors.import_fundamentals('US','available_date,eps,symbol\n2023-04-03,-10,BRK.B')
        self.assertEqual(us['fundamentals'][0]['symbol'],'BRK-B')
        for bad in ['2023-02-30,2,AAPL','2024-01-01,nan,AAPL','2024-01-01,9,005930.KQ',
                    '2024-01-01,5,AAPL\n2024-01-01,6,AAPL','2024-04-01,6,AAPL,extra']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                factors.import_fundamentals('US','available_date,eps,symbol\n'+bad)
