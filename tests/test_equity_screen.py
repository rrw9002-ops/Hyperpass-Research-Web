import io
import json
import unittest
from unittest.mock import patch

from hyperpass import equity_screen as screen


class EquityScreenTest(unittest.TestCase):
    def test_matching_currency_and_missing_data(self):
        def row(symbol, price, currency):
            return {'s':symbol, 'd':['Samsung', '기술', '반도체', price, currency, 100, 1000, 0, None,
                                     10, 12, 0.1, 250, 1795185000, None, 'KRW']}
        payload = {'totalCount':3,'data':[row('KRX:005930', 200, 'KRW'), row('KRX:000660', 100, 'USD'),
                                         row('KRX:123456', 100, 'KRW')]}
        members = {'005930.KS':'삼성전자','000660.KS':'SK하이닉스'}
        with patch.object(screen, 'resolve_universe', return_value=(members,'directory')), patch(
                'urllib.request.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
            snap = screen._fetch('KR')
        self.assertEqual((len(snap['rows']), snap['listed_count']), (1, 2))
        item = snap['rows'][0]
        self.assertEqual((item['name'],item['symbol'],item['exchange']), ('삼성전자','005930','KOSPI'))
        self.assertEqual(item['turnover'],20000)
        self.assertIsNone(item['pbr'])
        self.assertEqual(item['per'],0)
        self.assertEqual(item['price_date'],'2026-11-20')

    def test_refresh_contacts_provider_and_labels_outage(self):
        service = screen.EquityScreen(None)
        with patch('hyperpass.screen_yahoo.fetch_snapshot', side_effect=[
                {'market':'US','rows':[],'as_of':'original'},
                {'market':'US','rows':[],'as_of':'reloaded'},
                OSError()]) as fetch:
            self.assertEqual(service.snapshot('US')['cache_status'], 'fresh')
            self.assertEqual(service.snapshot('US')['cache_status'], 'cached')
            self.assertEqual(service.snapshot('US', refresh=True)['as_of'], 'reloaded')
            stale = service.snapshot('US', refresh=True)
            self.assertEqual((stale['cache_status'],stale['as_of']), ('stale','reloaded'))
            self.assertIn('Yahoo',stale['warning'])
            self.assertEqual(fetch.call_count,3)
            with self.assertRaises(ValueError):
                service.snapshot('XX')

    def test_missing_financials_only_and_session_invalidation(self):
        service = screen.EquityScreen(None)
        primary = {'market':'KR','rows':[{'id':'KRX:005930','price':120,'per':None,'roe':5}]}
        extra = {'rows':[{'id':'KRX:005930','price':999,'per':10,'roe':99}]}
        with patch('hyperpass.screen_kis.fetch_snapshot', return_value=primary) as fetch, patch.object(screen, '_fetch', return_value=extra) as supplement:
            self.assertIsNone(service.snapshot('KR')['rows'][0]['per'])
            supplement.assert_not_called()
            row = service.snapshot('KR',extra=True)['rows'][0]
            self.assertEqual((row['price'],row['per'],row['roe'],row['supplement_fields']), (120,10,5,['per']))
            service.invalidate_kis()
            self.assertIsNone(service.snapshot('KR')['rows'][0]['per'])
            self.assertEqual(fetch.call_count,3)
