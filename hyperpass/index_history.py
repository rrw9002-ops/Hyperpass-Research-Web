"""On-demand domestic/US index closes with verifiable provider identity and dated cache."""
import calendar
import csv
import io
import json
import math
import os
import tempfile
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from urllib import parse, request
from xml.etree import ElementTree

from .symbol_search import INDICES


NAMES = {yahoo: name for _, name, _, yahoo in INDICES}
NAVER = {"^KS11": "KOSPI", "^KQ11": "KOSDAQ"}
FRED = {"^GSPC": "SP500", "^DJI": "DJIA", "^IXIC": "NASDAQCOM"}
LOCKS = {symbol: threading.Lock() for symbol in NAMES}
FRESH_SECONDS = 20 * 60


def _read(url):
    req = request.Request(url, headers={"User-Agent": "HyperpassResearch/0.6"})
    with request.urlopen(req, timeout=8) as response:
        raw = response.read(200001)
    if len(raw) > 200000:
        raise ValueError("지수 응답이 예상 크기를 초과했습니다.")
    return raw


def _window(today):
    year = today.year if today.month > 3 else today.year - 1
    month = (today.month - 4) % 12 + 1
    day = min(today.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _series(rows, start, end):
    result = []
    for day, price in rows:
        if not start <= day <= end:
            continue
        day = day.isoformat()
        price = float(price)
        if not math.isfinite(price) or price <= 0 or (result and result[-1]["date"] >= day):
            raise ValueError("지수의 날짜 순서 또는 종가를 확인할 수 없습니다.")
        result.append({"date": day, "close": price})
    if len(result) < 2:
        raise ValueError("지수 수익률을 표시할 관측일이 부족합니다.")
    return result


def _alternative(symbol, today):
    start = _window(today)
    if symbol in NAVER:
        code = NAVER[symbol]
        query = parse.urlencode({"symbol": code, "timeframe": "day", "count": 100, "requestType": 0})
        raw = _read("https://fchart.stock.naver.com/sise.nhn?" + query)
        chart = ElementTree.fromstring(raw.decode("cp949")).find("chartdata")
        if chart is None or chart.get("symbol") != code or chart.get("timeframe") != "day":
            raise ValueError("네이버 금융에서 요청한 일봉 지수를 확인할 수 없습니다.")
        rows = []
        for item in chart.findall("item"):
            parts = item.get("data", "").split("|")
            if len(parts) < 5:
                raise ValueError("네이버 금융 지수 열을 확인하세요.")
            rows.append((datetime.strptime(parts[0], "%Y%m%d").date(), parts[4]))
        return "Naver 금융", "https://stock.naver.com/domestic/index/" + code + "/price", _series(rows, start, today)

    code = FRED[symbol]
    query = parse.urlencode({"id": code, "cosd": start.isoformat(), "coed": today.isoformat()})
    raw = _read("https://fred.stlouisfed.org/graph/fredgraph.csv?" + query)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if reader.fieldnames != ["observation_date", code]:
        raise ValueError("FRED에서 요청한 지수 계열을 확인할 수 없습니다.")
    rows = ((date.fromisoformat(row["observation_date"]), row[code]) for row in reader if row[code] not in ("", "."))
    return "FRED", "https://fred.stlouisfed.org/series/" + code, _series(rows, start, today)


def _load(path, symbol, now):
    if path is None:
        return None
    try:
        if path.stat().st_size > 100000:
            return None
        data = json.loads(path.read_text(encoding="utf8"))
        if data["symbol"] != symbol or data["provider"] not in ("Yahoo Finance", "Naver 금융", "FRED"):
            return None
        stamp = datetime.fromisoformat(data["retrieved_at"])
        if stamp.tzinfo is None or stamp > now:
            return None
        points = data["series"]
        if not isinstance(points, list) or not 2 <= len(points) <= 100:
            return None
        rows = ((date.fromisoformat(p["date"]), p["close"]) for p in points)
        data["series"] = _series(rows, date.min, now.date())
        if data["as_of"] != data["series"][-1]["date"]:
            return None
        return data
    except (KeyError, TypeError, ValueError, OSError):
        return None


def _save(path, result):
    if path is None:
        return
    temp = None
    try:
        path.parent.mkdir(exist_ok=True, parents=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf8", dir=path.parent, delete=False) as out:
            temp = Path(out.name)
            json.dump(result, out, ensure_ascii=False, allow_nan=False)
        os.replace(temp, path)
    except OSError:
        # A read-only or full disk must not suppress a verified online result.
        pass
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def get_index(sources, symbol, cache_dir=None):
    if symbol not in NAMES:
        raise ValueError("조회할 국내·미국 지수를 선택하세요.")
    path = Path(cache_dir)/(symbol[1:] + ".json") if cache_dir is not None else None
    with LOCKS[symbol]:
        return _get(sources, symbol, path)


def _get(sources, symbol, path):
    from .chart_lab import normalize_candles
    now = datetime.now(timezone.utc)
    cache = _load(path, symbol, now)
    if cache and (now - datetime.fromisoformat(cache["retrieved_at"])).total_seconds() < FRESH_SECONDS:
        return dict(cache, cache_status="fresh_cache")
    notice = ""
    try:
        packet = sources.chart_history(symbol, "3mo", "1d")
        if packet.get("symbol") != symbol:
            raise ValueError("Yahoo 지수 코드가 요청과 다릅니다.")
        bars, _ = normalize_candles(packet)
        rows = ((date.fromisoformat(b["timestamp"][:10]), b["close"]) for b in bars)
        series = _series(rows, _window(now.date()), now.date())
        provider, source = "Yahoo Finance", packet["source_url"]
    except (ValueError, OSError, KeyError, TypeError):
        try:
            provider, source, series = _alternative(symbol, now.date())
            notice = "Yahoo 조회가 어려워 다른 제공처의 일별 종가를 표시합니다."
        except (ValueError, OSError, KeyError, TypeError, csv.Error, ElementTree.ParseError):
            if cache:
                return dict(cache, cache_status="stale_cache", notice="두 제공처에 연결하지 못해 마지막으로 저장한 값을 표시합니다.")
            raise ValueError("Yahoo와 보조 제공처에서 지수를 받지 못했습니다. 잠시 후 다시 조회하세요.") from None
    if cache and series[-1]["date"] < cache["as_of"]:
        return dict(cache, cache_status="stale_cache", notice="이번 제공처의 관측일보다 최근인 마지막 저장값을 표시합니다.")
    result = {"symbol": symbol, "name": NAMES[symbol], "provider": provider, "source_url": source,
              "retrieved_at": now.isoformat(), "as_of": series[-1]["date"], "series": series,
              "cache_status": "live", "notice": notice}
    _save(path, result)
    return result
