import io
import json
import unittest
import zipfile
from unittest.mock import patch

from hyperpass import symbol_search as lookup
from hyperpass.tradingview_control import _same_chart_symbol


class SymbolSearchTests(unittest.TestCase):
    def setUp(self):
        lookup._search.cache_clear()
        lookup._masters.clear()

    def tearDown(self):
        lookup._search.cache_clear()
        lookup._masters.clear()

    @patch.object(lookup, "_us_master", return_value=([], True))
    def test_krx_name_and_preferred_shares_are_distinct(self, _):
        payload = {"symbols": [
            {"symbol": "005935", "exchange": "KRX", "description": "<em>삼성전자</em>우"},
            {"symbol": "005930", "exchange": "KRX", "description": "<em>삼성전자</em>"},
        ]}
        with patch.object(lookup, "_read", return_value=json.dumps(payload).encode()):
            rows = lookup.search_symbols("삼성전자")["results"]
        self.assertEqual([r["id"] for r in rows], ["KRX:005930", "KRX:005935"])
        self.assertEqual(rows[0]["name"], "삼성전자")

    def test_ticker_keeps_tradingview_relevance_for_multiple_exchanges(self):
        payload = {"symbols": [
            {"symbol": "<em>AMD</em>", "exchange": "NASDAQ", "description": "Advanced Micro Devices", "is_primary_listing": True},
            {"symbol": "<em>AMD</em>", "exchange": "ASX", "description": "Arrow", "is_primary_listing": True},
        ]}
        with patch.object(lookup, "_read", return_value=json.dumps(payload).encode()):
            rows = lookup.search_symbols("amd")["results"]
        self.assertEqual([r["id"] for r in rows], ["NASDAQ:AMD", "ASX:AMD"])

    def test_searches_broker_korean_name_by_normalized_substring(self):
        def source(url, *args):
            if url.startswith("https://symbol-search."):
                return b'{"symbols":[]}'
            market = url.split("/")[-1][:3].upper()
            line = "\t".join(["US", "1", market, "venue", "UNH", "code", "유나이티드헬스 그룹", "UnitedHealth"]) if market == "NYS" else "\t".join(["US", "1", market, "venue", "DEMO", "code", "다른 종목", "Demo"])
            buff = io.BytesIO()
            with zipfile.ZipFile(buff, "w") as archive:
                archive.writestr(market + "MST.COD", line.encode("cp949"))
            return buff.getvalue()

        with patch.object(lookup, "_read", side_effect=source) as fetch:
            result = lookup.search_symbols("유나이티드 헬스")
            self.assertEqual(result["notice"], "")
            self.assertEqual(result["results"][0], {"id": "NYSE:UNH", "name": "유나이티드헬스 그룹", "exchange": "NYSE", "ticker": "UNH"})
            lookup.search_symbols("유나이티드")
            self.assertEqual(fetch.call_count, 5)

    @patch.object(lookup, "_read", side_effect=TimeoutError())
    def test_outage_keeps_ambiguous_alias_and_reports_degraded_search(self, _):
        results = lookup.search_symbols("구글")
        self.assertEqual({r["id"] for r in results["results"]}, {"NASDAQ:GOOGL", "NASDAQ:GOOG"})
        self.assertIn("연결하지 못했습니다", results["notice"])
        self.assertEqual(lookup.search_symbols("없는회사999999")["results"], [])

    def test_delayed_korean_feed_accepts_only_same_requested_krx_ticker(self):
        self.assertTrue(_same_chart_symbol("KRX_DLY:005930", "KRX:005930"))
        self.assertFalse(_same_chart_symbol("KRX_DLY:005935", "KRX:005930"))
        self.assertFalse(_same_chart_symbol("OTHER:005930", "KRX:005930"))


if __name__ == "__main__":
    unittest.main()
