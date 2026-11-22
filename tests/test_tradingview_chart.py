import base64
import hashlib
import json
import shutil
import struct
import subprocess
import unittest
from unittest.mock import patch

from hyperpass import tradingview_chart as tv


def chart(symbol="NASDAQ:AAPL"):
    return {"symbol": symbol, "timeframe": "D", "currency": "USD", "timezone": "America/New_York",
            "series_symbol":symbol,"series_timeframe":"1D","series_completed":True,
            "bars": [{"time": 1700000000, "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000}],
            "studies": [{"id": "rsi1", "name": "Relative Strength Index", "values": [{"label": "RSI", "display_value": "52.3"}]}],
            "listed_studies": [{"id": "rsi1", "name": "RSI"}]}


def target(url="ws://127.0.0.1:9222/devtools/page/abc-123"):
    return {"type": "page", "url": "https://www.tradingview.com/chart/AbCd/", "webSocketDebuggerUrl": url}


class ChartTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'optional JavaScript compatibility check')
    def test_new_header_with_old_bars_is_rejected_until_main_series_completes(self):
        program = """
          let loading=true;
          const series={
            isLoading:()=>loading, isCompleted:()=>!loading, interval:()=>'1D',
            symbolInfo:()=>({full_name:'KRX_DLY:000660'}),
            bars:()=>({firstIndex:()=>0,lastIndex:()=>0,size:()=>1,
              valueAt:()=>loading?[1,340,350,330,342.56,10]:[1,1117000,1124000,1096000,1113000,10]})
          };
          const chart={symbol:()=>'KRX_DLY:000660',resolution:()=>'1D',
            dataReady:cb=>{cb();return true;},_chartWidget:{model:()=>({mainSeries:()=>series})}};
          global.window={TradingViewApi:{_activeChartWidgetWV:{value:()=>chart}}};
          async function read(){
            return EXPRESSION;
          }
          (async()=>{
            const before=await read();
            loading=false;const after=await read();
            console.log(JSON.stringify({before,close:after.bars[0].close}));
          })().catch(e=>{console.error(e);process.exitCode=1;});
        """.replace("EXPRESSION", tv.CHART_EXPRESSION.replace('__COUNT__','1'))
        result=subprocess.run(['node'], input=program, encoding='utf-8', capture_output=True, timeout=12)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),{'before':{'error':'loading'},'close':1113000})

    def test_bar_series_identity_and_timeframe_must_match_even_on_unchanged_chart(self):
        for changed in ({"series_completed":False}, {"series_symbol":"BATS:AAPL"}, {"series_timeframe":"60"},
                        {"series_timeframe":"1W"}, {"series_timeframe":""}, {"series_symbol":""}):
            with self.subTest(changed=changed), self.assertRaisesRegex(tv.TradingViewChartError,"시계열"):
                tv._normalize({**chart(), **changed},'NASDAQ:AAPL',100)

    def test_loaded_ohlcv_and_displayed_studies_preserve_time_uncertainty(self):
        with patch.object(tv, "_targets", return_value=[target()]), patch.object(tv, "_evaluate", return_value=chart()) as read:
            result = tv.fetch_chart(9222, "NASDAQ:AAPL")
        self.assertEqual(result["records"][0]["close"], 103)
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["timeframe"], "D")
        self.assertEqual(result["studies"][0]["values"][0]["display_value"], "52.3")
        self.assertEqual(result["studies"][0]["value_time"], "data_window_selection_unknown")
        self.assertTrue(result["as_of"].endswith("+00:00"))
        read.assert_called_once_with(target()["webSocketDebuggerUrl"], 9222, 100)

    def test_delayed_korean_feed_keeps_observed_venue(self):
        with patch.object(tv, "_targets", return_value=[target()]), patch.object(tv, "_evaluate", return_value=chart("KRX_DLY:005930")):
            packet = tv.fetch_chart(9222, "KRX:005930")
            self.assertEqual(packet["observed_symbol"], "KRX_DLY:005930")
            self.assertEqual(packet["symbol"], "KRX:005930")
            with self.assertRaises(tv.TradingViewChartError):
                tv.fetch_chart(9222, "KRX:005935")

    def test_selected_tab_only_reads_its_timeframe_for_same_symbol(self):
        target_a = dict(target(), id="tab-a")
        target_b = dict(target("ws://127.0.0.1:9222/devtools/page/tab-b"), id="tab-b")
        with patch.object(tv, "_targets", return_value=[target_a, target_b]), patch.object(tv, "_evaluate", return_value=chart()) as read:
            tv.fetch_chart(9222, "NASDAQ:AAPL", 100, target_id="tab-b")
            read.assert_called_once_with(target_b["webSocketDebuggerUrl"], 9222, 100)
            with self.assertRaises(tv.TradingViewChartError):
                tv.fetch_chart(9222, "NASDAQ:AAPL", target_id="closed-tab")

    def test_symbol_is_verified_from_chart_not_page_title(self):
        with patch.object(tv, "_targets", return_value=[target()]), patch.object(tv, "_evaluate", return_value=chart("NYSE:MSFT")):
            with self.assertRaises(tv.TradingViewChartError):
                tv.fetch_chart(9222, "NASDAQ:AAPL")

    def test_multiple_tabs_select_only_exact_symbol(self):
        with patch.object(tv, "_targets", return_value=[target(), target()]), patch.object(tv, "_evaluate", side_effect=[chart("NYSE:MSFT"), chart()]):
            self.assertEqual(tv.fetch_chart(9222, "NASDAQ:AAPL")["symbol"], "NASDAQ:AAPL")

    def test_local_endpoint_and_input_validation(self):
        for url in ("ws://evil.example:9222/devtools/page/a", "ws://127.0.0.1:9223/devtools/page/a",
                    "ws://127.0.0.1:9222/devtools/page/a?x=1", "ws://user@127.0.0.1:9222/devtools/page/a",
                    "ws://127.0.0.1:9222/devtools/browser/a", "ws://127.0.0.1:9222/devtools/page/a%0d%0a"):
            with self.subTest(url=url), self.assertRaises(tv.TradingViewChartError):
                tv._valid_ws(url, 9222)
        for port, symbol, count in [(80, "AAPL", 100), (True, "AAPL", 100), (9222, "AAPL';alert(1)", 100), (9222, "AAPL", 501), (9222, "AAPL", True)]:
            with self.assertRaises(tv.TradingViewChartError):
                tv.fetch_chart(port, symbol, count)

    def test_bad_bars_rejected(self):
        for field, value in (("high", 90), ("time", 0), ("volume", -1), ("close", float("nan")), ("open", True)):
            raw = chart()
            raw["bars"][0][field] = value
            with self.subTest(field=field), self.assertRaises(tv.TradingViewChartError):
                tv._normalize(raw, "NASDAQ:AAPL", 100)
        raw = chart(); raw["bars"].append(dict(raw["bars"][0]))
        with self.assertRaises(tv.TradingViewChartError):
            tv._normalize(raw, "NASDAQ:AAPL", 100)

    def test_no_arbitrary_page_or_endpoint_fallback(self):
        fake = target(); fake["url"] = "https://tradingview.com.evil.example/chart/"
        with patch.object(tv, "_targets", return_value=[fake]), patch.object(tv, "_evaluate") as read:
            with self.assertRaises(tv.TradingViewChartError):
                tv.fetch_chart(9222, "NASDAQ:AAPL")
            read.assert_not_called()

    def test_fixed_getters_only_in_cdp_call(self):
        response = {"id": 1, "result": {"result": {"value": chart()}}}
        with patch.object(tv, "_WebSocket") as cls:
            cls.return_value.receive.return_value = response
            tv._evaluate(target()["webSocketDebuggerUrl"], 9222, 100)
            packet = json.loads(cls.return_value.send.call_args.args[0])
        self.assertEqual(packet["method"], "Runtime.evaluate")
        self.assertNotIn("__COUNT__", packet["params"]["expression"])
        for forbidden in ("setSymbol", "setResolution", "createStudy", "removeEntity", "fetch(", "XMLHttpRequest", "localStorage", "cookie", "submitOrder"):
            self.assertNotIn(forbidden, packet["params"]["expression"])

    def test_read_errors_redact_upstream_detail(self):
        with patch.object(tv, "_targets", side_effect=OSError("sensitive credential detail")):
            with self.assertRaises(tv.TradingViewChartError) as error:
                tv.fetch_chart(9222, "NASDAQ:AAPL")
            self.assertNotIn("sensitive", str(error.exception))


class FakeSocket:
    def __init__(self, data): self.data = bytearray(data); self.sent = []
    def recv(self, size):
        result = bytes(self.data[:size]); del self.data[:size]; return result
    def sendall(self, value): self.sent.append(value)
    def settimeout(self, value): pass
    def close(self): pass


class FrameTests(unittest.TestCase):
    def client(self, wire):
        client = tv._WebSocket.__new__(tv._WebSocket)
        client.sock = FakeSocket(wire); client.buffer = bytearray()
        return client

    def test_fragmented_json_with_ping_uses_masked_pong(self):
        client = self.client(b'\x01\x05{"x":' + b'\x89\x02hi' + b'\x80\x021}')
        self.assertEqual(client.receive(), {"x": 1})
        pong = client.sock.sent[0]
        self.assertEqual(pong[0], 0x8A)
        self.assertEqual(pong[1], 0x82)
        self.assertEqual(bytes(value ^ pong[2 + i % 4] for i, value in enumerate(pong[6:])), b"hi")

    def test_masked_server_and_oversized_frames_rejected(self):
        for wire in (b"\x81\x81", b"\x81\x7f" + struct.pack("!Q", tv.MAX_BYTES + 1)):
            with self.assertRaises(tv.TradingViewChartError):
                self.client(wire).receive()

    def test_client_payload_is_masked(self):
        client = self.client(b""); payload = b'{"method":"Runtime.evaluate"}'
        client.send(payload); frame = client.sock.sent[0]
        self.assertTrue(frame[1] & 0x80)
        self.assertEqual(bytes(value ^ frame[2 + i % 4] for i, value in enumerate(frame[6:])), payload)

    def test_websocket_handshake_verifies_accept_and_preserves_first_frame(self):
        key = base64.b64encode(b"A" * 16).decode()
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        response = ("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode() + b'\x81\x02{}'
        sock = FakeSocket(response)
        with patch.object(tv.socket, "create_connection", return_value=sock), patch.object(tv.os, "urandom", return_value=b"A" * 16):
            ws = tv._WebSocket(target()["webSocketDebuggerUrl"], 9222)
            self.assertEqual(ws.receive(), {})
        self.assertIn(b"Host: 127.0.0.1:9222\r\n", sock.sent[0])
        self.assertNotIn(b"Origin:", sock.sent[0])

    def test_websocket_rejects_invalid_handshake(self):
        sock = FakeSocket(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: wrong\r\n\r\n")
        with patch.object(tv.socket, "create_connection", return_value=sock):
            with self.assertRaises(tv.TradingViewChartError):
                tv._WebSocket(target()["webSocketDebuggerUrl"], 9222)


if __name__ == "__main__":
    unittest.main()
