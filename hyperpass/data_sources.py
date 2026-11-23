"""Bounded research-only data adapters. Credentials live only in process memory.

No arbitrary URL, account endpoint, order endpoint, or redirect is accepted.
Provider availability and licensing remain independent of successful setup.
"""
from __future__ import annotations

import base64
import csv
import io
import json
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


class DataSourceError(ValueError):
    """A short user-safe message, never an upstream response or request URL."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport(method, url, headers=None, body=None):
    request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                     headers=headers or {}, method=method)
    opener = urllib.request.build_opener(_NoRedirect(), urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=25) as response:
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise DataSourceError("데이터 응답이 허용 크기를 초과했습니다.")
        return json.loads(raw.decode("utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError()))
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        if code in (401, 403):
            raise DataSourceError("데이터 인증 또는 상품 이용 권한을 확인하세요.") from None
        if code == 429:
            raise DataSourceError("데이터 제공자의 호출 한도에 도달했습니다. 잠시 후 다시 시도하세요.") from None
        if 300 <= code < 400:
            raise DataSourceError("데이터 요청이 다른 주소로 이동하여 차단했습니다.") from None
        raise DataSourceError(f"데이터 제공자가 HTTP {code} 오류를 반환했습니다.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise DataSourceError("데이터 서버에 연결할 수 없습니다. 네트워크와 서버 실행 상태를 확인하세요.") from None
    except (ValueError, UnicodeError):
        raise DataSourceError("데이터 서버가 읽을 수 없는 응답을 반환했습니다.") from None


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _epoch(value):
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return "unknown"


PROVIDERS = {
    "kis": {"fields": ["app_key", "app_secret"], "mode": "read-only-api", "description": "한국투자증권 국내주식 현재가 조회 전용"},
    "fmp": {"fields": ["api_key"], "mode": "read-only-api", "description": "FMP 주식 시세; 가입 상품에 따라 접근 제한"},
    "yahoo": {"fields": [], "mode": "unofficial-public", "description": "Yahoo 공개 차트; 비공식 경로로 변경·차단 가능"},
    "openbb": {"fields": ["port", "version", "username", "password"], "mode": "local-api", "description": "같은 컴퓨터에서 실행 중인 OpenBB API에 연결"},
    "tradingview": {"fields": ["mode", "port", "count", "csv", "symbol", "currency"], "mode": "chart", "description": "열린 TradingView Desktop 차트 읽기; CSV 또는 공개 스캐너는 별도 선택"},
}
_SECRET_KEYS = {"api_key", "apikey", "app_key", "app_secret", "appkey", "appsecret", "password", "access_token", "authorization", "token"}


class DataSources:
    def __init__(self, transport=None):
        self._request = transport or _transport
        self._configs = {}
        self._tokens = {}
        self._lock = threading.RLock()
        self._kis_quote_lock = threading.Lock()
        self._kis_next_quote = 0.0

    def configure(self, name, config):
        if name not in PROVIDERS or not isinstance(config, dict):
            raise DataSourceError("지원하지 않는 데이터 연결입니다.")
        if set(config) - set(PROVIDERS[name]["fields"]):
            raise DataSourceError("지원하지 않는 연결 설정이 포함되어 있습니다.")
        normalized = {}
        for key, value in config.items():
            if not isinstance(value, (str, int)) or isinstance(value, bool):
                raise DataSourceError("연결 설정 형식을 확인하세요.")
            value = str(value).strip()
            if len(value) > (1_000_000 if key == "csv" else 4096):
                raise DataSourceError("연결 설정이 너무 큽니다.")
            if key != "csv" and ("\r" in value or "\n" in value):
                raise DataSourceError("연결 설정에 줄바꿈을 넣을 수 없습니다.")
            normalized[key] = value
        for key in ({"kis": ("app_key", "app_secret"), "fmp": ("api_key",)}.get(name, ())):
            if not normalized.get(key):
                raise DataSourceError(f"필수 설정 {key}를 입력하세요.")
        if name == "openbb":
            try:
                port = int(normalized.get("port", "6900"))
            except ValueError:
                raise DataSourceError("OpenBB 포트는 숫자로 입력하세요.") from None
            if not 1024 <= port <= 65535:
                raise DataSourceError("OpenBB 포트는 1024~65535 범위여야 합니다.")
            normalized["port"] = port
            normalized["version"] = normalized.get("version", "v5")
            if normalized["version"] not in ("v4", "v5"):
                raise DataSourceError("OpenBB 버전은 v4 또는 v5를 선택하세요.")
            if bool(normalized.get("username")) != bool(normalized.get("password")):
                raise DataSourceError("OpenBB 인증을 사용하면 사용자명과 비밀번호를 함께 입력하세요.")
        if name == "tradingview":
            normalized["mode"] = normalized.get("mode") or ("csv" if normalized.get("csv") else "chart")
            if normalized["mode"] not in ("chart", "scanner", "csv"):
                raise DataSourceError("TradingView 연결 방식은 chart, scanner, csv 중 선택하세요.")
            if normalized["mode"] == "csv":
                self._symbol(normalized.get("symbol"))
                if not normalized.get("csv"):
                    raise DataSourceError("TradingView CSV 내용을 입력하세요.")
                self._csv_rows(normalized["csv"])
            if normalized["mode"] == "chart":
                try:
                    normalized["port"] = int(normalized.get("port") or "9222")
                    normalized["count"] = int(normalized.get("count") or "100")
                except ValueError:
                    raise DataSourceError("TradingView 포트와 봉 개수는 정수로 입력하세요.") from None
                if not 1024 <= normalized["port"] <= 65535 or not 1 <= normalized["count"] <= 500:
                    raise DataSourceError("TradingView 포트는 1024~65535, 봉 개수는 1~500 범위여야 합니다.")
        with self._lock:
            self._configs[name] = normalized
            self._tokens.pop(name, None)
        return self.status()[name]

    def disconnect(self, name):
        if name not in PROVIDERS:
            raise DataSourceError("지원하지 않는 데이터 연결입니다.")
        with self._lock:
            self._configs.pop(name, None)
            self._tokens.pop(name, None)
        return self.status()[name]

    def status(self):
        with self._lock:
            return {name: {**value, "configured": name in self._configs or name in ("yahoo", "tradingview")}
                    for name, value in PROVIDERS.items()}

    @staticmethod
    def _symbol(symbol):
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9.^=_:\-]{1,32}", symbol):
            raise DataSourceError("올바른 종목 코드를 입력하세요.")
        return symbol.upper()

    @staticmethod
    def _matching_symbol(requested, returned):
        if not isinstance(returned, str) or returned.strip().upper() != requested:
            raise DataSourceError("제공자가 반환한 종목이 요청 종목과 다르거나 확인되지 않습니다. 해당 데이터를 사용하지 않습니다.")

    def _call(self, method, url, headers=None, body=None):
        # Defense at the one outbound boundary, including injected transports.
        parsed = urllib.parse.urlsplit(url)
        allowed = ((parsed.scheme == "https" and parsed.netloc in (
            "openapi.koreainvestment.com:9443", "financialmodelingprep.com", "query1.finance.yahoo.com", "scanner.tradingview.com")) or
            (parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port and 1024 <= parsed.port <= 65535))
        if not allowed or parsed.username or parsed.password or parsed.fragment:
            raise DataSourceError("허용되지 않은 데이터 서버 주소입니다.")
        try:
            return self._request(method, url, headers or {}, body)
        except DataSourceError:
            raise
        except Exception:
            # An injected or future transport may include the URL/key in its error.
            raise DataSourceError("데이터 요청에 실패했습니다. 연결 설정과 제공자 상태를 확인하세요.") from None

    def fetch(self, name, symbol):
        if name not in PROVIDERS:
            raise DataSourceError("지원하지 않는 데이터 연결입니다.")
        symbol = self._symbol(symbol)
        with self._lock:
            config = dict(self._configs.get(name, {}))
        if name not in ("yahoo", "tradingview") and not config:
            raise DataSourceError("먼저 데이터 연결 설정을 입력하세요.")
        try:
            result = getattr(self, "_fetch_" + name)(symbol, config)
        except DataSourceError:
            raise
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            raise DataSourceError("제공자 응답에서 필요한 시세 데이터를 찾지 못했습니다.") from None
        result.update(provider=name, symbol=symbol, retrieved_at=_utc())
        # Strip any credential-like fields and exact stored secrets from results.
        with self._lock:
            secrets = [str(v) for cfg in self._configs.values() for k, v in cfg.items() if k in _SECRET_KEYS and v]
            secrets += [v[0] for v in self._tokens.values()]
        def clean(value):
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items() if str(k).lower() not in _SECRET_KEYS}
            if isinstance(value, list):
                return [clean(v) for v in value]
            if isinstance(value, str):
                for secret in secrets:
                    value = value.replace(secret, "[redacted]")
                return value
            return value
        return clean(result)

    def kis_quotes(self, symbols, *, detailed=False):
        """Read one official KRX quote or up to 30 quotes with the session's KIS registration."""
        if (not isinstance(symbols, list) or not 1 <= len(symbols) <= (1 if detailed else 30)
                or any(not isinstance(code, str) or not re.fullmatch(r"[0-9][0-9A-Z]{5}", code) for code in symbols)):
            raise DataSourceError("KIS 스크리너에 사용할 국내 종목 코드를 확인하세요.")
        base = "https://openapi.koreainvestment.com:9443"
        tr = "FHKST01010100" if detailed else "FHKST11300006"
        resource = "inquire-price" if detailed else "intstock-multprice"
        params = {}
        for index, code in enumerate(symbols, 1):
            suffix = "" if detailed else "_" + str(index)
            params["FID_COND_MRKT_DIV_CODE" + suffix] = "J"
            params["FID_INPUT_ISCD" + suffix] = code
        url = base + "/uapi/domestic-stock/v1/quotations/" + resource + "?" + urllib.parse.urlencode(params)
        # Serialize quote traffic across charts and screeners, including repeated refreshes.
        with self._kis_quote_lock:
            for attempt in range(2):
                wait = self._kis_next_quote - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                with self._lock:
                    cfg = self._configs.get("kis")
                    if not cfg:
                        raise DataSourceError("데이터 연결에서 한국투자증권 KIS App Key와 Secret을 등록하세요.")
                    token, expiry = self._tokens.get("kis", ("", 0))
                    if not token or time.monotonic() >= expiry:
                        result = self._call("POST", base + "/oauth2/tokenP", {"Content-Type":"application/json"},
                                            {"grant_type":"client_credentials","appkey":cfg["app_key"],"appsecret":cfg["app_secret"]})
                        token = result.get("access_token")
                        if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
                            raise DataSourceError("KIS 토큰 발급에 실패했습니다. App Key와 Secret을 확인하세요.")
                        lifetime = max(1, min(int(result.get("expires_in", 3600)), 86400) - 60)
                        self._tokens["kis"] = (token, time.monotonic() + lifetime)
                    headers = {"authorization":"Bearer " + token, "appkey":cfg["app_key"], "appsecret":cfg["app_secret"],
                               "tr_id":tr, "custtype":"P"}
                self._kis_next_quote = time.monotonic() + 0.15
                result = self._call("GET", url, headers)
                if result.get("msg_cd") == "EGW00201" and not attempt:
                    self._kis_next_quote = time.monotonic() + 1.1
                    continue
                if str(result.get("rt_cd")) != "0" or not isinstance(result.get("output"), dict if detailed else list):
                    raise DataSourceError("KIS 시세 조회가 거절되었습니다. 인증·시장 이용 권한·호출 한도를 확인하세요.")
                return result["output"]

    def _fetch_kis(self, symbol, cfg):
        row = self.kis_quotes([symbol], detailed=True)
        base = "https://openapi.koreainvestment.com:9443"
        path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        fields = ("stck_prpr", "prdy_vrss", "prdy_ctrt", "acml_vol", "stck_oprc", "stck_hgpr", "stck_lwpr", "hts_kor_isnm", "stck_bsop_date", "stck_cntg_hour")
        return {"records": [{key: row[key] for key in fields if key in row}], "as_of": "unknown", "currency": "KRW",
                "warning": "현재가 조회 응답입니다. 수신 시각은 거래소 체결 시각과 다릅니다. 계좌·주문 API는 사용하지 않습니다.", "source_url": base + path}

    def _fetch_fmp(self, symbol, cfg):
        base = "https://financialmodelingprep.com/stable/quote"
        rows = self._call("GET", base + "?" + urllib.parse.urlencode({"symbol": symbol, "apikey": cfg["api_key"]}))
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            raise DataSourceError("FMP 시세를 받지 못했습니다. 종목과 API 상품 권한을 확인하세요.")
        for row in rows:
            self._matching_symbol(symbol, row.get("symbol") if isinstance(row, dict) else None)
        fields = ("symbol", "name", "price", "change", "changePercentage", "volume", "dayLow", "dayHigh", "yearLow", "yearHigh", "marketCap", "timestamp", "currency", "exchange")
        records = [{k: row[k] for k in fields if k in row} for row in rows[:20] if isinstance(row, dict)]
        return {"records": records, "as_of": _epoch(rows[0].get("timestamp")), "currency": rows[0].get("currency", "unknown"),
                "warning": "시세 지연·종목 범위는 FMP 가입 상품에 따릅니다.", "source_url": base + "?" + urllib.parse.urlencode({"symbol": symbol})}

    def _fetch_yahoo(self, symbol, cfg):
        period, interval = cfg.get('range', '3mo'), cfg.get('interval', '1d')
        if period not in ('3mo','1y','2y','5y') or interval not in ('1d','1wk','1mo'):
            raise DataSourceError('지원하는 조회 기간·차트 주기를 선택하세요.')
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol, safe="") + f"?range={period}&interval={interval}"
        response = self._call("GET", url, {"User-Agent": "HyperpassResearch/0.1"})
        chart = response.get("chart", {})
        if chart.get("error") or not chart.get("result"):
            raise DataSourceError("Yahoo 차트 데이터가 없습니다. 종목 또는 제공자 제한을 확인하세요.")
        data = chart["result"][0]
        meta = data.get("meta", {})
        self._matching_symbol(symbol, meta.get("symbol"))
        quote = data["indicators"]["quote"][0]
        records = []
        for index, timestamp in enumerate(data.get("timestamp", [])):
            row = {"timestamp": _epoch(timestamp)}
            for field in ("open", "high", "low", "close", "volume"):
                series = quote.get(field, [])
                row[field] = series[index] if index < len(series) else None
            records.append(row)
        if not records:
            raise DataSourceError("Yahoo 응답에 가격 이력이 없습니다.")
        return {"records": records[-(1600 if cfg.get('chart_lab') else 100):], "as_of": records[-1]["timestamp"], "currency": meta.get("currency", "unknown"), "timeframe": interval,
                "instrument_name": str(meta.get("longName") or meta.get("shortName") or "")[:180], "exchange_code": str(meta.get("exchangeName") or "")[:20],
                "exchange_timezone": str(meta.get("exchangeTimezoneName") or "")[:80],
                "warning": "Yahoo 비공식 공개 차트 경로입니다. 차단·변경될 수 있으며 일봉 OHLC는 별도 배당 조정 수익률이 아닙니다.", "source_url": url}

    def chart_history(self, symbol, period='2y', interval='1d'):
        symbol = self._symbol(symbol)
        result = self._fetch_yahoo(symbol, {'range':period,'interval':interval,'chart_lab':True})
        accepted, excluded = [], []
        for row in result['records']:
            prices = [row.get(k) for k in ('open', 'high', 'low', 'close')]
            if all(type(p) in (int, float) and math.isfinite(p) and p > 0 for p in prices):
                opening, high, low, closing = prices
                tolerance = high * 1e-10
                if low <= high and low - tolerance <= min(opening, closing) and max(opening, closing) <= high + tolerance:
                    accepted.append(row)
                    continue
            excluded.append(row)
        if excluded:
            result['excluded_rows'] = excluded
            result['records'] = accepted
            dates = ', '.join(r['timestamp'][:10] for r in excluded[:8])
            result['warning'] += (f' 가격이 누락되거나 고가·저가와 맞지 않는 {len(excluded)}봉({dates})을 제외했습니다.'
                                  ' 원본 행은 기록에 보존했습니다. 관측 공백이 계산 결과에 영향을 줄 수 있습니다.')
        return dict(result, provider='yahoo', symbol=symbol, retrieved_at=_utc())

    def _fetch_openbb(self, symbol, cfg):
        base = "http://127.0.0.1:" + str(cfg["port"])
        if cfg["version"] == "v5":
            path, provider = "/api/v1/cboe/equity/quote", "cboe"
        else:
            path, provider = "/api/v1/equity/price/historical", "yfinance"
        url = base + path + "?" + urllib.parse.urlencode({"symbol": symbol, "provider": provider})
        headers = {}
        if cfg.get("username"):
            headers["Authorization"] = "Basic " + base64.b64encode((cfg["username"] + ":" + cfg["password"]).encode()).decode()
        response = self._call("GET", url, headers)
        rows = response.get("results")
        if not isinstance(rows, list) or not rows:
            raise DataSourceError("OpenBB 데이터가 없습니다. 선택한 버전·provider 설치 상태를 확인하세요.")
        for row in rows:
            if isinstance(row, dict) and "symbol" in row:
                self._matching_symbol(symbol, row["symbol"])
        rows = rows[-100:]
        last = rows[-1] if isinstance(rows[-1], dict) else {}
        return {"records": rows, "as_of": str(last.get("date") or last.get("timestamp") or "unknown"),
                "currency": last.get("currency", "unknown"), "warning": "별도로 실행 중인 로컬 OpenBB와 해당 provider가 필요합니다. 이 앱은 OpenBB를 자동 설치하지 않습니다.", "source_url": url}

    @staticmethod
    def _csv_rows(text, max_rows=1000):
        try:
            content = text.lstrip("\ufeff").strip()
            first_line = content.partition("\n")[0]
            delimiter = max((",", ";", "\t"), key=first_line.count)
            reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
            aliases = {"시간":"time", "날짜":"date", "일자":"date", "일시":"time", "datetime":"time",
                       "시가":"open", "고가":"high", "저가":"low", "종가":"close", "거래량":"volume", "vol":"volume"}
            lookup = {}
            for name in reader.fieldnames or []:
                key = name.strip().lower()
                lookup[aliases.get(key, key)] = name
            time_key = lookup.get("time") or lookup.get("date") or lookup.get("timestamp")
            if not time_key or "close" not in lookup:
                raise DataSourceError("TradingView CSV에는 time/date와 close 열이 필요합니다.")
            rows = []
            for row in reader:
                if len(rows) >= max_rows:
                    raise DataSourceError(f"CSV는 한 번에 {max_rows:,}행까지 가져올 수 있습니다.")
                clean = {"timestamp": row.get(time_key, "")}
                for field in ("open", "high", "low", "close", "volume"):
                    value = row.get(lookup.get(field, ""), "")
                    if value is None or value == "":
                        clean[field] = None
                    else:
                        number = float(value.replace(",", "") if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", value.strip()) else value)
                        if not (-1e30 < number < 1e30):
                            raise ValueError()
                        clean[field] = number
                rows.append(clean)
            if not rows:
                raise DataSourceError("CSV에 데이터 행이 없습니다.")
            return rows
        except DataSourceError:
            raise
        except (csv.Error, TypeError, ValueError):
            raise DataSourceError("CSV 가격·거래량은 숫자여야 합니다. TradingView 내보내기 형식을 확인하세요.") from None

    def _fetch_tradingview(self, symbol, cfg):
        mode = cfg.get("mode", "chart")
        if mode == "chart":
            from .tradingview_chart import fetch_chart, TradingViewChartError
            try:
                result = fetch_chart(cfg.get("port", 9222), symbol, cfg.get("count", 100))
            except TradingViewChartError as exc:
                raise DataSourceError(str(exc)) from None
            self._matching_symbol(symbol, result.get("symbol"))
            result["warning"] = " ".join(result.get("notes", []))
            return result
        if mode == "scanner":
            market = {"NASDAQ": "america", "NYSE": "america", "AMEX": "america", "KRX": "korea"}.get(symbol.split(":")[0])
            if not market or ":" not in symbol:
                raise DataSourceError("TradingView에는 NASDAQ:AAPL 또는 KRX:005930 같은 거래소:종목 형식을 사용하세요.")
            columns = ["name", "close", "currency", "volume", "change", "exchange", "description"]
            url = "https://scanner.tradingview.com/" + market + "/scan"
            response = self._call("POST", url, {"Content-Type": "application/json", "User-Agent": "HyperpassResearch/0.1"},
                                  {"symbols": {"tickers": [symbol], "query": {"types": []}}, "columns": columns})
            data = response.get("data")
            if not isinstance(data, list) or not data or not isinstance(data[0], dict) or not isinstance(data[0].get("d"), list):
                raise DataSourceError("TradingView 공개 조회가 실패했습니다. 비공식 경로는 차단·변경될 수 있습니다. CSV 가져오기를 사용하세요.")
            for item in data:
                self._matching_symbol(symbol, item.get("s") if isinstance(item, dict) else None)
            row = dict(zip(columns, data[0]["d"]))
            row["symbol"] = data[0]["s"]
            return {"records": [row], "as_of": "unknown", "currency": row.get("currency", "unknown"),
                    "warning": "TradingView 웹 화면용 공개 스캐너의 비공식 실험적 연결입니다. 공식 데이터 API가 아니며 변경·차단·시세 지연이 가능합니다. 체결 시각은 미확인입니다.",
                    "source_url": url}
        if symbol != cfg["symbol"].upper():
            raise DataSourceError("가져온 TradingView CSV의 종목과 조회 종목이 다릅니다.")
        rows = self._csv_rows(cfg["csv"])
        return {"records": rows, "as_of": rows[-1]["timestamp"] or "unknown", "currency": cfg.get("currency") or "unknown",
                "warning": "사용자가 가져온 TradingView CSV입니다. 실시간 API가 아니며 시간대·가격 조정 기준은 내보내기 설정을 확인해야 합니다.",
                "source_url": "https://www.tradingview.com/support/solutions/43000474413-i-need-access-to-your-api-in-order-to-get-data-or-indicator-values/"}
