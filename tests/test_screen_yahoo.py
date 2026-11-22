import io
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from hyperpass import screen_yahoo as yahoo
from hyperpass.market_prices import MarketBacktestError


def observed(ticker='AAPL', exchange='NMS'):
    return {'symbol':ticker,'exchange':exchange,'currency':'USD','financialCurrency':'USD',
            'quoteType':'EQUITY','regularMarketTime':1795208402,'gmtOffSetMilliseconds':-18000000,
            'regularMarketPrice':330.0,'regularMarketVolume':100,'marketCap':1234,'sector':'Technology',
            'longName':'Apple Inc.','exchangeDataDelayedBy':15,'marketState':'CLOSED','quoteSourceName':'Delayed Quote'}


def screen_record(ticker='AAPL',exchange='NMS'):
    return {'ticker':ticker,'exchange':exchange,'returnOnEquityPercentLtm':12.5,
            'totalDebtEquityPercentLtm':86,'netIncomeIsLtm':240,'totalRevenueLtm':400,'operatingIncomeLtm':60,
            'peRatioLtm':16,'priceBookRatioQuarterly':1.59,'sector':'Technology','industry':'Consumer Electronics'}


class YahooScreenTest(TestCase):
    def test_eligible_missing_security_type_in_directory(self):
        from hyperpass.market_prices import _us_listings
        raw = b'ACT Symbol|Security Name|Exchange|ETF|Test Issue\nTSM|Taiwan Manufacturer Ltd.|N|N|N\nZZB|Senior Notes|N|N|N\nZZW|Warrants|N|N|N\n'
        self.assertEqual(list(_us_listings(raw)), [])
        self.assertEqual(list(_us_listings(raw,screen_candidates=True)), [('TSM','Taiwan Manufacturer Ltd.','NYSE')])

    def test_quote_identifiers_timestamps_and_financial_units(self):
        q=observed()
        row=yahoo._observation(q,screen_record(),{'AAPL':('Apple','NASDAQ')})
        self.assertEqual((row['id'],row['name'],row['volume'],row['turnover']),('NASDAQ:AAPL','애플',100,33000))
        self.assertEqual((row['income'],row['income_currency'],row['roe'],row['margin'],row['debt']), (240,'USD',12.5,15.0,0.86))
        self.assertEqual((row['price_date'],row['price_time'],row['delay_minutes']),('2026-11-20','2026-11-20T21:00:02+00:00',15))
        self.assertIsNone(row['fiscal_date'])
        self.assertIsNone(yahoo._observation(q,{}, {'AAPL':('Apple','NYSE')}))
        self.assertIsNone(yahoo._observation(dict(q,regularMarketTime=None),{}, {'AAPL':('Apple','NASDAQ')}))
        self.assertIsNone(yahoo._observation(dict(q,currency='CAD'),{}, {'AAPL':('Apple','NASDAQ')}))

    def test_share_classes_and_absent_financials(self):
        q=observed('BRK-B','NYQ')
        q['industry']='Insurance'
        f=screen_record('BRK-B','NYQ')
        members={'BRK-B':('Berkshire Hathaway Inc.','NYSE')}
        q['priceToBook']=0.001
        row=yahoo._observation(q,f,members)
        self.assertEqual((row['id'],row['symbol'],row['yahoo'],row['pbr']),('NYSE:BRK.B','BRK.B','BRK-B',1.59))
        empty=yahoo._observation(dict(q,regularMarketVolume=0),{},members)
        self.assertIsNone(empty['pbr'])
        self.assertIsNone(empty['roe'])
        self.assertEqual(empty['turnover'],0)
        self.assertIsNone(yahoo._observation(q,dict(f,exchange='NMS'),members)['income'])

    def test_batch_only_matches_requested_listed_equities(self):
        sess=Mock()
        sess.quotes.return_value=[observed(),observed(),dict(observed('MSFT'),quoteType='ETF'),observed('TSLA')]
        sess.fundamentals.return_value={'AAPL':screen_record()}
        members={'AAPL':('Apple','NASDAQ'),'MSFT':('Microsoft','NASDAQ')}
        calls=[]
        with patch.object(yahoo,'_listed',return_value=members),patch.object(yahoo,'_YahooSession',return_value=sess):
            out=yahoo.fetch_snapshot(progress=lambda *args:calls.append(args))
        self.assertEqual(out['listed_count'],2)
        self.assertEqual(out['requested_count'],2)
        self.assertEqual([r['id'] for r in out['rows']],['NASDAQ:AAPL'])
        self.assertEqual(out['source'],'Yahoo Finance')
        self.assertEqual(calls[-1][:2],(2,2))

    def test_rate_limit_preserves_completed_prices_and_stops_requests(self):
        sess=Mock()
        sess.quotes.return_value=[observed()]
        sess.fundamentals.side_effect=HTTPError('https://example.invalid/?crumb=private',429,'wait',{},io.BytesIO())
        with patch.object(yahoo,'_listed',return_value={'AAPL':('Apple','NASDAQ'),'MSFT':('Microsoft','NASDAQ')}),patch.object(yahoo,'BATCH_SIZE',1),patch.object(yahoo,'_YahooSession',return_value=sess):
            snap=yahoo.fetch_snapshot()
        self.assertEqual((snap['requested_count'],snap['rows'][0]['price']),(1,330))
        self.assertIn('HTTP 429',snap['warnings'][0])
        self.assertNotIn('private',str(snap))
        self.assertEqual(sess.quotes.call_count,1)
        self.assertIsNone(snap['rows'][0]['roe'])

    def test_unexpected_json_is_an_explicit_provider_error(self):
        session = object.__new__(yahoo._YahooSession)
        session.crumb = 'ephemeral'
        for body, method in [(b'[]',session.quotes), (b'{"quoteResponse":[1]}',session.quotes),
                             (b'{"finance":{"result":[null]}}',session.fundamentals)]:
            with self.subTest(body=body), patch.object(session,'_read',return_value=body):
                with self.assertRaises(MarketBacktestError):
                    method(['AAPL'])

    def test_provider_denial_is_not_a_sample_result(self):
        sess=Mock()
        sess.quotes.side_effect=HTTPError('https://example.invalid/?crumb=private',403,'forbidden',{},io.BytesIO())
        with patch.object(yahoo,'_listed',return_value={'AAPL':('Apple','NASDAQ')}),patch.object(yahoo,'_YahooSession',return_value=sess):
            with self.assertRaisesRegex(MarketBacktestError,'HTTP 403') as caught:
                yahoo.fetch_snapshot()
        self.assertNotIn('private',str(caught.exception))
