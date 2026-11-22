from __future__ import annotations

import json
import io
import unittest
from unittest.mock import patch
import urllib.error

from hyperpass.data_sources import DataSources, DataSourceError, _NoRedirect, _transport


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class DataSourceTests(unittest.TestCase):
    def test_kis_uses_only_token_and_quote_and_caches_token(self):
        transport = FakeTransport([{"access_token": "secret-token", "expires_in": 86400},
                                   {"rt_cd": "0", "output": {"stck_prpr": "70000", "token": "secret-token"}},
                                   {"rt_cd": "0", "output": {"stck_prpr": "70100"}}])
        sources = DataSources(transport)
        safe = sources.configure("kis", {"app_key": "secret-app-key", "app_secret": "secret-app-secret"})
        self.assertNotIn("secret-app", json.dumps(safe))
        first = sources.fetch("kis", "005930")
        sources.fetch("kis", "005930")
        self.assertEqual(len(transport.calls), 3)
        self.assertTrue(transport.calls[0][1].endswith("/oauth2/tokenP"))
        self.assertTrue(all("/quotations/inquire-price?" in c[1] for c in transport.calls[1:]))
        self.assertEqual([c[0] for c in transport.calls], ["POST", "GET", "GET"])
        self.assertNotIn("secret", json.dumps(first))
        self.assertEqual(first["currency"], "KRW")
        self.assertEqual(first["as_of"], "unknown")
        sources.disconnect("kis")
        with self.assertRaises(DataSourceError):
            sources.fetch("kis", "005930")

    def test_fmp_never_returns_key_url_or_unselected_fields(self):
        transport = FakeTransport([[{"symbol": "AAPL", "price": 100, "timestamp": 100,
                                    "apikey": "secret-api-key", "name": "echo secret-api-key", "credentials": "unsafe"}]])
        sources = DataSources(transport)
        sources.configure("fmp", {"api_key": "secret-api-key"})
        result = sources.fetch("fmp", "AAPL")
        self.assertNotIn("secret-api-key", json.dumps(result))
        self.assertNotIn("apikey", result["source_url"])
        self.assertEqual(result["records"][0]["price"], 100)

    def test_bad_config_and_symbols_never_send_network(self):
        transport = FakeTransport([])
        sources = DataSources(transport)
        for name, cfg in [("openbb", {"url": "http://evil"}), ("openbb", {"port": "6900/evil"}),
                          ("openbb", {"port": 80}), ("openbb", {"version": "v6"}),
                          ("openbb", {"username": "u"}), ("kis", {"app_key": "a\r\ninject", "app_secret": "b"})]:
            with self.assertRaises(DataSourceError):
                sources.configure(name, cfg)
        for symbol in ("http://evil", "../../token", "AAPL&apikey=steal", "a\nHeader"):
            with self.assertRaises(DataSourceError):
                sources.fetch("yahoo", symbol)
        self.assertFalse(transport.calls)

    def test_openbb_versions_loopback_auth_and_safe_output(self):
        transport = FakeTransport([{"results": [{"date": "2026-01-01", "close": 10, "password": "secret-pass"}]},
                                   {"results": [{"date": "2026-01-02", "close": 11}]}])
        sources = DataSources(transport)
        sources.configure("openbb", {"port": 6900, "version": "v5", "username": "u", "password": "secret-pass"})
        result = sources.fetch("openbb", "AAPL")
        self.assertIn("127.0.0.1:6900/api/v1/cboe/equity/quote", transport.calls[0][1])
        self.assertTrue(transport.calls[0][2]["Authorization"].startswith("Basic "))
        self.assertNotIn("secret-pass", json.dumps(result))
        sources.configure("openbb", {"version": "v4"})
        sources.fetch("openbb", "AAPL")
        self.assertIn("/api/v1/equity/price/historical", transport.calls[1][1])
        self.assertIn("provider=yfinance", transport.calls[1][1])

    def test_yahoo_labels_unofficial_and_preserves_timestamp_currency(self):
        transport = FakeTransport([{"chart": {"error": None, "result": [{"meta": {"symbol": "AAPL", "currency": "USD"},
                                    "timestamp": [100], "indicators": {"quote": [{"close": [10], "volume": [20]}]}}]}}])
        result = DataSources(transport).fetch("yahoo", "AAPL")
        self.assertEqual(result["records"][0]["close"], 10)
        self.assertEqual(result["currency"], "USD")
        self.assertIn("비공식", result["warning"])
        self.assertNotEqual(result["as_of"], result["retrieved_at"])

    def test_tradingview_csv_never_contacts_network(self):
        transport = FakeTransport([])
        sources = DataSources(transport)
        sources.configure("tradingview", {"csv": "time,open,high,low,close,Volume\n2026-01-01,1,3,1,2,100\n", "symbol": "NASDAQ:AAPL", "currency": "USD"})
        result = sources.fetch("tradingview", "NASDAQ:AAPL")
        self.assertEqual(result["records"][0]["close"], 2)
        self.assertEqual(result["currency"], "USD")
        self.assertIn("CSV", result["warning"])
        with self.assertRaises(DataSourceError):
            sources.fetch("tradingview", "NASDAQ:MSFT")
        self.assertFalse(transport.calls)

    def test_tradingview_scanner_is_explicitly_unofficial(self):
        transport = FakeTransport([{"data": [{"s": "NASDAQ:AAPL", "d": ["AAPL", 100, "USD", 1200, 1, "NASDAQ", "Apple"]}]}])
        sources = DataSources(transport)
        sources.configure("tradingview", {"mode": "scanner"})
        result = sources.fetch("tradingview", "NASDAQ:AAPL")
        self.assertEqual(transport.calls[0][1], "https://scanner.tradingview.com/america/scan")
        self.assertNotIn("Authorization", transport.calls[0][2])
        self.assertIn("비공식", result["warning"])
        self.assertEqual(result["as_of"], "unknown")

    def test_upstream_errors_do_not_leak_secrets(self):
        sources = DataSources(FakeTransport([RuntimeError("https://url/?apikey=secret-key")]))
        sources.configure("fmp", {"api_key": "secret-key"})
        with self.assertRaises(DataSourceError) as caught:
            sources.fetch("fmp", "AAPL")
        self.assertNotIn("secret-key", str(caught.exception))
        error_body = io.BytesIO(b"secret upstream body")
        with patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.HTTPError("https://url/?apikey=secret", 403, "secret", {}, error_body)):
            with self.assertRaises(DataSourceError) as http:
                _transport("GET", "https://financialmodelingprep.com/stable/quote?apikey=secret")
        self.assertNotIn("secret", str(http.exception))
        self.assertTrue(error_body.closed)
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test"))

    def test_empty_and_non_numeric_csv_fail(self):
        sources = DataSources()
        for text in ("time,close\n", "time,close\nx,NaN\n", "time,close\nx,infinity\n", "wrong,close\nx,2\n"):
            with self.assertRaises(DataSourceError):
                sources.configure("tradingview", {"csv": text, "symbol": "AAPL"})

    def test_provider_symbol_mismatches_and_missing_required_ids_rejected(self):
        cases = [
            ("fmp", {"api_key": "secret"}, "AAPL", [{"symbol": "MSFT", "price": 1}]),
            ("fmp", {"api_key": "secret"}, "AAPL", [{"price": 1}]),
            ("fmp", {"api_key": "secret"}, "AAPL", [{"symbol": "AAPL"}, {"symbol": "MSFT"}]),
            ("yahoo", {}, "AAPL", {"chart": {"result": [{"meta": {"symbol": "MSFT"}}]}}),
            ("yahoo", {}, "AAPL", {"chart": {"result": [{"meta": {}}]}}),
            ("tradingview", {"mode": "scanner"}, "NASDAQ:AAPL", {"data": [{"s": "NASDAQ:MSFT", "d": ["MSFT", 1]}]}),
            ("tradingview", {"mode": "scanner"}, "NASDAQ:AAPL", {"data": [{"d": ["AAPL", 1]}]}),
            ("openbb", {"version": "v5"}, "AAPL", {"results": [{"symbol": "MSFT", "price": 1}]}),
            ("openbb", {"version": "v4"}, "AAPL", {"results": [{"symbol": None, "price": 1}]}),
        ]
        for provider, config, symbol, response in cases:
            with self.subTest(provider=provider, response=response):
                sources = DataSources(FakeTransport([response]))
                sources.configure(provider, config)
                with self.assertRaisesRegex(DataSourceError, "종목"):
                    sources.fetch(provider, symbol)

    def test_chart_mode_default_and_error_preserved(self):
        from hyperpass.tradingview_chart import TradingViewChartError
        sources = DataSources(FakeTransport([]))
        with patch("hyperpass.tradingview_chart.fetch_chart", return_value={"symbol": "NASDAQ:AAPL", "records": [{"close": 1}], "notes": ["시점 미확인"]}) as chart:
            result = sources.fetch("tradingview", "NASDAQ:AAPL")
            chart.assert_called_once_with(9222, "NASDAQ:AAPL", 100)
            self.assertIn("시점 미확인", result["warning"])
        with patch("hyperpass.tradingview_chart.fetch_chart", side_effect=TradingViewChartError("차트를 직접 여세요.")):
            with self.assertRaisesRegex(DataSourceError, "차트를 직접"):
                sources.fetch("tradingview", "NASDAQ:AAPL")
        for config in ({"mode": "invalid"}, {"mode": "chart", "port": 80}, {"mode": "chart", "count": 501}, {"mode": "csv"}):
            with self.assertRaises(DataSourceError):
                sources.configure("tradingview", config)


if __name__ == "__main__":
    unittest.main()
