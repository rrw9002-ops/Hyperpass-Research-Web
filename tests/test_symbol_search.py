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

        with patch.object(lookup, "kr_listings", return_value=([], True)), patch.object(lookup, "_read", side_effect=source) as fetch:
            result = lookup.search_symbols("유나이티드 헬스")
            self.assertEqual(result["notice"], "")
            self.assertEqual(result["results"][0], {"id": "NYSE:UNH", "name": "유나이티드헬스 그룹", "exchange": "NYSE", "ticker": "UNH"})
            before = [c.args[0] for c in fetch.call_args_list if "/common/master/" in c.args[0]]
            lookup.search_symbols("유나이티드")
            self.assertCountEqual(before, [c.args[0] for c in fetch.call_args_list if "/common/master/" in c.args[0]])

    @patch.object(lookup, "_read", side_effect=TimeoutError())
    def test_outage_keeps_ambiguous_alias_and_reports_degraded_search(self, _):
        results = lookup.search_symbols("구글")
        self.assertEqual({r["id"] for r in results["results"]}, {"NASDAQ:GOOGL", "NASDAQ:GOOG"})
        self.assertIn("연결하지 못했습니다", results["notice"])
        self.assertEqual(lookup.search_symbols("없는회사999999")["results"], [])

    def test_direct_inputs_work_without_selecting_suggestion(self):
        with patch.object(lookup, "_read", side_effect=AssertionError("unexpected network")):
            for name in ("삼성전자", "삼전", "005930", "KRX:005930", "Samsung Electronics"):
                self.assertEqual(lookup.chart_symbol(name, "yahoo"), "005930.KS")
            for name in ("애플", "AAPL", "apple"):
                self.assertEqual(lookup.resolve_symbol(name, "tradingview")["id"], "NASDAQ:AAPL")
            self.assertEqual(lookup.chart_symbol("코스닥", "yahoo"), "^KQ11")
            self.assertEqual(lookup.chart_symbol("BATS:AAPL", "tradingview"), "BATS:AAPL")
            self.assertEqual(lookup.chart_symbol("KRX:123456", "csv"), "KRX:123456")
            with self.assertRaisesRegex(ValueError, "여러"):
                lookup.resolve_symbol("구글", "yahoo")

    def test_domestic_board_is_read_from_fixed_width_stock_master(self):
        def listing(url, limit):
            board = url.split("/")[-1].split("_")[0]
            filename = board + "_code.mst"
            code, name = ("123456", "테스트산업") if board == "kosdaq" else ("024680", "다른종목")
            row = code.encode().ljust(9) + b"0"*12 + name.encode("cp949").ljust(40) + b"ST"
            buff = io.BytesIO()
            with zipfile.ZipFile(buff, "w") as archive:
                archive.writestr(filename, row + b"\n")
            return buff.getvalue()
        with patch.object(lookup, "_read", side_effect=listing), patch.object(lookup, "_tradingview", return_value=[]), patch.object(lookup, "_us_master", return_value=([],True)):
            self.assertEqual(lookup.kr_listings("kosdaq")[0][0], ("KRX:123456", "테스트산업", "123456.KQ", "ST"))
            for query in ("테스트산업", "123456", "KRX:123456"):
                result = lookup.resolve_symbol(query, "yahoo")
                self.assertEqual(result["yahoo"], "123456.KQ")
            with self.assertRaisesRegex(ValueError, "상장 시장"):
                lookup.resolve_symbol("999999", "yahoo")

    def test_delayed_korean_feed_accepts_only_same_requested_krx_ticker(self):
        self.assertTrue(_same_chart_symbol("KRX_DLY:005930", "KRX:005930"))
        self.assertFalse(_same_chart_symbol("KRX_DLY:005935", "KRX:005930"))
        self.assertFalse(_same_chart_symbol("OTHER:005930", "KRX:005930"))


if __name__ == "__main__":
    unittest.main()
