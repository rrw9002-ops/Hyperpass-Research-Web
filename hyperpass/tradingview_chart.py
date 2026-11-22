"""Read-only, loopback-only TradingView Desktop chart bridge (no MCP dependency).

Chart getter compatibility informed by tradesdontlie/tradingview-mcp, MIT;
see docs/TRADINGVIEW-THIRD-PARTY-LICENSE.txt. No chart mutation is exposed.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import math
import os
import re
import socket
import struct
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 12


class TradingViewChartError(ValueError):
    pass


# This expression is fixed. Only a validated integer count is substituted.
# It calls getters only: no symbol/timeframe changes, studies, orders or scripts.
CHART_EXPRESSION = r"""(() => {
  const chart = window.TradingViewApi?._activeChartWidgetWV?.value();
  if (!chart) return {error:'chart_unavailable'};
  const model = chart._chartWidget.model();
  const series = model.mainSeries();
  const bars = series.bars();
  const rows = [];
  const last = bars.lastIndex();
  const first = Math.max(bars.firstIndex(), last - __COUNT__ + 1);
  for (let i = first; i <= last; i++) {
    const value = bars.valueAt(i);
    if (value) rows.push({time:value[0],open:value[1],high:value[2],low:value[3],close:value[4],volume:value[5] ?? null});
  }
  let info = {};
  try { info = series.symbolInfo() || {}; } catch (_) {}
  const studies = [];
  let sources = [];
  try { sources = model.model().dataSources(); } catch (_) {}
  for (const source of sources.slice(0, 80)) {
    if (typeof source.metaInfo !== 'function') continue;
    try {
      const meta = source.metaInfo();
      const name = meta.description || meta.shortDescription;
      if (!name) continue;
      let id = null;
      try { id = source.id(); } catch (_) {}
      const values = [];
      try {
        const items = source.dataWindowView()?.items() || [];
        for (const item of items.slice(0, 80)) {
          if (item._title && item._value !== undefined && item._value !== '∅')
            values.push({label:String(item._title),display_value:String(item._value)});
        }
      } catch (_) {}
      studies.push({id,name,values,value_time:'data_window_selection_unknown',available:values.length > 0});
    } catch (_) {}
  }
  let listed = [];
  try { listed = chart.getAllStudies().map(s => ({id:s.id,name:s.name || s.title || 'unknown'})); } catch (_) {}
  return {symbol:chart.symbol(),timeframe:String(chart.resolution()),currency:info.currency_code || info.currency || 'unknown',
    timezone:info.timezone || 'unknown',bars:rows,studies,listed_studies:listed,total_available:bars.size()};
})()"""


def _port(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1024 <= value <= 65535:
        raise TradingViewChartError("TradingView 디버그 포트는 1024–65535 정수여야 합니다.")
    return value


def _symbol(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9.^=_:\-]{1,60}", value):
        raise TradingViewChartError("TradingView의 거래소:종목 표기를 입력하세요. 예: NASDAQ:AAPL")
    return value.upper()


def _targets(port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=TIMEOUT)
    try:
        connection.request("GET", "/json/list", headers={"Host": f"127.0.0.1:{port}"})
        response = connection.getresponse()
        if response.status != 200:
            raise TradingViewChartError("TradingView 디버그 연결이 준비되지 않았습니다.")
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise TradingViewChartError("TradingView 탭 목록 응답이 너무 큽니다.")
        result = json.loads(raw)
        if not isinstance(result, list):
            raise TradingViewChartError("TradingView 탭 목록 형식을 확인할 수 없습니다.")
        return result
    finally:
        connection.close()


def _valid_ws(url, port):
    parsed = urlsplit(url)
    if (parsed.scheme != "ws" or parsed.hostname != "127.0.0.1" or parsed.port != port
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not re.fullmatch(r"/devtools/page/[A-Za-z0-9_-]+", parsed.path)):
        raise TradingViewChartError("허용되지 않은 TradingView 디버그 연결 주소입니다.")
    return parsed.path


class _WebSocket:
    """Bounded RFC6455 client for the one local CDP response; no extensions."""
    def __init__(self, url, port):
        path = _valid_ws(url, port)
        self.sock = socket.create_connection(("127.0.0.1", port), TIMEOUT)
        self.buffer = bytearray()
        try:
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            request = (f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                       f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                       "Sec-WebSocket-Version: 13\r\n\r\n")
            self.sock.sendall(request.encode("ascii"))
            while b"\r\n\r\n" not in self.buffer:
                data = self.sock.recv(4096)
                if not data or len(self.buffer) + len(data) > 16384:
                    raise TradingViewChartError("TradingView 디버그 연결 응답을 확인할 수 없습니다.")
                self.buffer.extend(data)
            header, remaining = bytes(self.buffer).split(b"\r\n\r\n", 1)
            self.buffer = bytearray(remaining)
            lines = header.decode("latin1").split("\r\n")
            headers = dict((k.strip().lower(), v.strip()) for k, v in (line.split(":", 1) for line in lines[1:] if ":" in line))
            expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            if (len(lines[0].split()) < 2 or lines[0].split()[1] != "101"
                    or headers.get("sec-websocket-accept") != expected
                    or headers.get("upgrade", "").lower() != "websocket"
                    or "upgrade" not in headers.get("connection", "").lower()):
                raise TradingViewChartError("TradingView WebSocket 연결을 확인하지 못했습니다.")
        except Exception:
            self.sock.close()
            raise

    def close(self):
        self.sock.close()

    def _read(self, count):
        while len(self.buffer) < count:
            chunk = self.sock.recv(min(65536, count - len(self.buffer)))
            if not chunk:
                raise TradingViewChartError("TradingView 디버그 연결이 종료되었습니다.")
            self.buffer.extend(chunk)
        value = bytes(self.buffer[:count])
        del self.buffer[:count]
        return value

    def send(self, payload, opcode=1):
        if len(payload) > MAX_BYTES:
            raise TradingViewChartError("TradingView 요청 크기를 초과했습니다.")
        mask = os.urandom(4)
        length = len(payload)
        prefix = bytes([0x80 | opcode])
        if length < 126:
            prefix += bytes([0x80 | length])
        elif length < 65536:
            prefix += bytes([0x80 | 126]) + struct.pack("!H", length)
        else:
            prefix += bytes([0x80 | 127]) + struct.pack("!Q", length)
        self.sock.sendall(prefix + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def receive(self):
        chunks = bytearray()
        started = False
        deadline = time.monotonic() + TIMEOUT
        for _ in range(256):
            self.sock.settimeout(max(.01, deadline - time.monotonic()))
            if time.monotonic() >= deadline:
                raise TradingViewChartError("TradingView 응답 시간이 초과되었습니다.")
            first, second = self._read(2)
            final, opcode = bool(first & 0x80), first & 0x0f
            if first & 0x70 or second & 0x80:
                raise TradingViewChartError("지원하지 않는 디버그 프레임입니다.")
            size = second & 0x7f
            if size == 126:
                size = struct.unpack("!H", self._read(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self._read(8))[0]
            if size > MAX_BYTES or len(chunks) + size > MAX_BYTES:
                raise TradingViewChartError("TradingView 데이터 응답 크기를 초과했습니다.")
            if opcode >= 8 and (not final or size > 125):
                raise TradingViewChartError("잘못된 디버그 제어 프레임입니다.")
            payload = self._read(size)
            if opcode == 8:
                raise TradingViewChartError("TradingView 디버그 연결이 종료되었습니다.")
            if opcode == 9:
                self.send(payload, 10)
                continue
            if opcode == 10:
                continue
            if opcode == 1 and not started:
                started = True
            elif opcode != 0 or not started:
                raise TradingViewChartError("지원하지 않는 디버그 메시지입니다.")
            chunks.extend(payload)
            if final:
                return json.loads(chunks.decode("utf-8"))
        raise TradingViewChartError("TradingView 디버그 응답 한도를 초과했습니다.")


def _evaluate(url, port, count):
    ws = _WebSocket(url, port)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
            "expression": CHART_EXPRESSION.replace("__COUNT__", str(count)),
            "returnByValue": True, "awaitPromise": False, "timeout": 8000,
        }}).encode())
        deadline = time.monotonic() + TIMEOUT
        for _ in range(32):
            if time.monotonic() >= deadline:
                break
            message = ws.receive()
            if not isinstance(message, dict) or message.get("id") != 1:
                continue
            result = message.get("result", {})
            if message.get("error") or result.get("exceptionDetails"):
                raise TradingViewChartError("현재 TradingView 차트에서 데이터를 읽지 못했습니다. 차트 로딩과 앱 버전을 확인하세요.")
            value = result.get("result", {}).get("value")
            if not isinstance(value, dict) or value.get("error"):
                raise TradingViewChartError("현재 탭에 읽을 수 있는 TradingView 차트가 없습니다.")
            return value
        raise TradingViewChartError("TradingView 데이터 응답을 받지 못했습니다.")
    finally:
        ws.close()


def _normalize(raw, symbol, count):
    observed = str(raw.get("symbol", "")).upper()
    if observed != symbol:
        raise TradingViewChartError("현재 TradingView 차트의 종목이 요청한 심볼과 다릅니다. 앱에서 해당 차트를 직접 여세요.")
    bars = raw.get("bars")
    if not isinstance(bars, list) or not bars or len(bars) > count:
        raise TradingViewChartError("현재 차트에서 유효한 OHLCV 봉을 읽지 못했습니다.")
    records = []
    previous_time = -math.inf
    for row in bars:
        if not isinstance(row, dict):
            raise TradingViewChartError("차트 봉 형식이 올바르지 않습니다.")
        clean = {}
        for field in ("time", "open", "high", "low", "close", "volume"):
            value = row.get(field)
            if field == "volume" and value is None:
                clean[field] = None
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise TradingViewChartError("차트 데이터에 유효하지 않은 수치가 있습니다.")
            clean[field] = value
        if (clean["time"] <= previous_time or clean["time"] <= 0
                or clean["high"] < max(clean["open"], clean["close"], clean["low"])
                or clean["low"] > min(clean["open"], clean["close"], clean["high"])
                or (clean["volume"] is not None and clean["volume"] < 0)):
            raise TradingViewChartError("차트 데이터의 시간순서 또는 OHLCV 범위를 확인할 수 없습니다.")
        previous_time = clean["time"]
        records.append(clean)
    try:
        as_of = datetime.fromtimestamp(records[-1]["time"], timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        raise TradingViewChartError("차트 봉의 기준 시간을 해석할 수 없습니다.") from None
    studies = raw.get("studies", [])
    if not isinstance(studies, list):
        studies = []
    normalized = []
    for study in studies[:80]:
        if not isinstance(study, dict):
            continue
        values = study.get("values", [])
        normalized.append({"id": str(study.get("id", ""))[:150], "name": str(study.get("name", ""))[:300],
            "values": [{"label": str(v.get("label", ""))[:200], "display_value": str(v.get("display_value", ""))[:300]}
                       for v in values[:80] if isinstance(v, dict)] if isinstance(values, list) else [],
            "value_time": "data_window_selection_unknown"})
    return {"provider": "tradingview", "mode": "desktop-chart-cdp", "symbol": symbol,
            "records": records, "studies": normalized, "listed_studies": raw.get("listed_studies", [])[:80],
            "timeframe": str(raw.get("timeframe", "unknown"))[:40], "currency": str(raw.get("currency", "unknown"))[:30],
            "chart_timezone": str(raw.get("timezone", "unknown"))[:80], "as_of": as_of,
            "retrieved_at": datetime.now(timezone.utc).isoformat(), "source_url": "https://www.tradingview.com/chart/",
            "notes": ["사용자가 연 TradingView Desktop 차트의 로드된 봉만 읽음. 자동 종목 변경·지표 추가 없음.",
                      "as_of는 마지막 봉 시작 시각입니다. 진행 중인 봉일 수 있으며 조정·지연 여부는 별도 확인이 필요합니다.",
                      "지표 값은 데이터 창 표시값입니다. 커서 선택 시각을 확인할 수 없어 마지막 봉과 같은 시점으로 간주하지 않습니다."]}


def fetch_chart(port: int, symbol: str, count=100):
    """Read already-open chart. User must explicitly enable local CDP first."""
    port = _port(port)
    symbol = _symbol(symbol)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 500:
        raise TradingViewChartError("차트 봉 개수는 1–500 정수여야 합니다.")
    try:
        candidates = []
        for target in _targets(port):
            if not isinstance(target, dict) or target.get("type") != "page":
                continue
            parsed = urlsplit(target.get("url", ""))
            if (parsed.scheme in ("https", "http") and parsed.hostname
                    and (parsed.hostname == "tradingview.com" or parsed.hostname.endswith(".tradingview.com"))
                    and parsed.path.startswith("/chart")):
                candidates.append(target)
        if not candidates:
            raise TradingViewChartError("TradingView Desktop에서 조회할 차트를 먼저 여세요.")
        # Match by the chart getter, not URL/title; do not silently select another symbol.
        last_error = None
        for target in candidates[:8]:
            try:
                raw = _evaluate(target.get("webSocketDebuggerUrl", ""), port, count)
                if str(raw.get("symbol", "")).upper() == symbol:
                    return _normalize(raw, symbol, count)
            except TradingViewChartError as exc:
                last_error = exc
        if last_error:
            raise last_error
        raise TradingViewChartError("열린 TradingView 차트에 요청한 심볼이 없습니다. 거래소:종목을 정확히 맞추세요.")
    except TradingViewChartError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, http.client.HTTPException):
        raise TradingViewChartError("TradingView Desktop에 연결하지 못했습니다. 직접 켠 로컬 디버그 포트와 열린 차트를 확인하세요.") from None
