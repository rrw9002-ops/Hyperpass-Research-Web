from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from hyperpass.data_sources import DataSourceError, DataSources
from hyperpass import screen_kis as kis


def master_line(code, name, board='kospi', group='ST'):
    layout = kis.BOARD[board]
    line = bytearray(b' ' * layout['width'])
    line[:6] = code.encode()
    text = name.encode('cp949')
    line[21:21+len(text)] = text
    line[61:63] = group.encode()
    line[64:76] = b'002700130000'
    for key, text in {'reference':'000190000','volume':'000000000300','revenue':'000000200',
                      'profit':'000000020','roe':'000007.25','fiscal':'20250930','cap':'000000450'}.items():
        pos = layout[key]
        line[pos:pos+len(text)] = text.encode()
    return bytes(line)


class KISScreenFixtures(TestCase):
    def setUp(self):
        def master(name):
            content = {'kospi_code':master_line('005930','삼성전자') + b'\n' + master_line('000001','ETF',group='EF'),
                       'kosdaq_code':master_line('247540','에코프로비엠',board='kosdaq'),
                       'idxcode':('00027제조\n00013전기·전자').encode('cp949')}[name]
            return content,'2026-11-20T20:00:00+00:00'
        self.addCleanup(patch.stopall)
        patch.object(kis,'_master',master).start()
        self.calls = []
        def transport(method,url,headers,body):
            self.calls.append((method,url,headers,body))
            if method == 'POST':
                return {'access_token':'token-test','expires_in':3600}
            if 'intstock-multprice?' in url:
                return {'rt_cd':'0','output':[{'inter_shrn_iscd':'005930','inter2_prpr':'1200',
                         'acml_tr_pbmn':'1830','acml_vol':'2'},
                        {'inter_shrn_iscd':'999999','inter2_prpr':'4500'}]}
            return {'rt_cd':'0','output':{'stck_shrn_iscd':'005930','stck_prpr':'1260','acml_tr_pbmn':'2830',
                    'acml_vol':'3','hts_avls':'3345','per':'11.5','pbr':'2.1'}}
        self.sources = DataSources(transport)

    def connect(self):
        self.sources.configure('kis',{'app_key':'key_kis_test','app_secret':'secret_kis_test'})

    def test_keyless_master_financials_and_missing_points(self):
        d = kis.fetch_snapshot(self.sources)
        self.assertEqual(d['listed_count'],2)
        self.assertEqual(d['price_label'],'기준가')
        self.assertEqual(d['quote_mode'],'master')
        row = d['rows'][0]
        self.assertEqual((row['id'],row['sector'],row['industry']),('KRX:005930','제조','전기·전자'))
        self.assertEqual((row['roe'],row['margin'],row['market_cap']),(7.25,10,45_000_000_000))
        self.assertEqual(row['fiscal_date'],'2025-09-30')
        self.assertIsNone(row['price_date'])
        self.assertIsNone(row['per'])
        self.assertIsNone(row['income'])
        self.assertEqual(self.calls,[])

    def test_authenticated_whole_market_uses_real_turnover_and_rejects_foreign_symbol(self):
        self.connect()
        progress = []
        d = kis.fetch_snapshot(self.sources,progress=lambda *args:progress.append(args))
        self.assertEqual(d['quote_mode'],'api')
        self.assertEqual(d['quoted_count'],1)
        self.assertEqual(progress[-1][:2],(2,2))
        one,missing = d['rows']
        self.assertEqual((one['price'],one['volume'],one['turnover']),(1200,2,1830))
        self.assertIsNone(missing['price'])
        self.assertEqual(missing['quote_mode'],'unavailable')
        self.assertTrue(d['warnings'])
        self.assertEqual([c[0] for c in self.calls],['POST','GET'])
        self.assertEqual(self.calls[1][2]['tr_id'],'FHKST11300006')
        self.assertEqual(parse_qs(urlsplit(self.calls[1][1]).query), {
            'FID_COND_MRKT_DIV_CODE_1':['J'], 'FID_INPUT_ISCD_1':['005930'],
            'FID_COND_MRKT_DIV_CODE_2':['J'], 'FID_INPUT_ISCD_2':['247540']})

    def test_explicit_detail_updates_fundamentals_and_keeps_key_private(self):
        with self.assertRaises(DataSourceError):
            kis.fetch_quotes(self.sources,['005930'])
        self.connect()
        result = kis.fetch_quotes(self.sources,['KRX:005930','005930.KS'])
        self.assertEqual(len(result['rows']),1)
        row = result['rows'][0]
        self.assertEqual((row['price'],row['per'],row['pbr'],row['market_cap']),(1260,11.5,2.1,334_500_000_000))
        self.assertIsNone(row['price_time'])
        self.assertEqual(row['price_date'],None)
        self.assertTrue(row['quote_received_at'])
        self.assertNotIn('secret_kis_test',str(result))
        self.assertEqual(self.calls[-1][2]['tr_id'],'FHKST01010100')
        self.sources.disconnect('kis')
        with self.assertRaises(DataSourceError):
            kis.fetch_quotes(self.sources,['005930'])
        self.connect()
        kis.fetch_quotes(self.sources,['005930'])
        self.assertEqual([row[0] for row in self.calls],['POST','GET','POST','GET'])

    def test_incorrect_schema_invalid_identifiers_and_partial_responses(self):
        with self.assertRaises(DataSourceError):
            kis._listings(master_line('005930','삼성전자')+b'x','kospi',{},None)
        with self.assertRaises(DataSourceError):
            kis.fetch_quotes(self.sources,['NASDAQ:AAPL'])
        self.connect()
        with self.assertRaises(DataSourceError):
            kis.fetch_quotes(self.sources,['247540'])
        self.assertIsNone(kis._quote('005930',{'inter_shrn_iscd':'005930','inter2_prpr':0},
                                     detailed=False,received='today'))
