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

    def test_cache_labels_old_values_and_rejects_unavailable_market(self):
        with patch.dict(screen._CACHE, {}, clear=True), patch.object(screen, '_fetch', side_effect=[
                {'market':'US','rows':[]},OSError()]) as fetch, patch.object(screen.time, 'monotonic',side_effect=[1,2,120]):
            first = screen.snapshot('US')
            self.assertIs(screen.snapshot('US'),first)
            self.assertIn('warning',screen.snapshot('US'))
            self.assertEqual(fetch.call_count,2)
            with self.assertRaises(ValueError):
                screen.snapshot('XX')
