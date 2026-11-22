"""Resolve chart symbols through TradingView and Korean-language stock names."""

import html
import io
import json
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from functools import lru_cache


SYMBOL_ID = re.compile(r"[A-Z0-9_]+:[A-Z0-9.^=_!\-]+")
MARKETS = {"nas": "NASDAQ", "nys": "NYSE", "ams": "AMEX"}
# Common classroom aliases also work when the public search services are down.
ALIASES = (
    ("KRX:005930", "삼성전자", "삼전|Samsung Electronics"),
    ("KRX:005935", "삼성전자우", "삼성전자우선주"),
    ("KRX:000660", "SK하이닉스", "하이닉스|에스케이하이닉스|SK Hynix"),
    ("KRX:005380", "현대차", "현대자동차|Hyundai Motor"),
    ("KRX:035420", "네이버", "NAVER"),
    ("KRX:035720", "카카오", "Kakao"),
    ("NASDAQ:AAPL", "애플", "Apple"),
    ("NASDAQ:NVDA", "엔비디아", "Nvidia"),
    ("NASDAQ:TSLA", "테슬라", "Tesla"),
    ("NASDAQ:MSFT", "마이크로소프트", "마소|Microsoft"),
    ("NASDAQ:GOOGL", "알파벳 A", "구글|알파벳|Google|Alphabet"),
    ("NASDAQ:GOOG", "알파벳 C", "구글|알파벳|Google|Alphabet"),
    ("NASDAQ:AMZN", "아마존", "Amazon"),
    ("NASDAQ:META", "메타", "페이스북|Meta Platforms"),
)


# Provider-specific identifiers for the five index charts.
INDICES = (
    ("KRX:KOSPI", "코스피", "KOSPI", "^KS11"),
    ("KRX:KOSDAQ", "코스닥", "KOSDAQ", "^KQ11"),
    ("NASDAQ:IXIC", "나스닥 종합", "나스닥|나스닥종합지수|NASDAQ Composite", "^IXIC"),
    ("SP:SPX", "S&P 500", "S&P|S&P500|SP500", "^GSPC"),
    ("DJ:DJI", "다우존스 산업평균", "다우|다우지수|다우존스|Dow Jones", "^DJI"),
)
INDEX_YAHOO = {symbol: yahoo for symbol, _, _, yahoo in INDICES}
SEARCH_ALIASES = ALIASES + tuple((symbol, name, aliases + "|" + yahoo) for symbol, name, aliases, yahoo in INDICES)
KR_CODE = re.compile(r"[0-9][0-9A-Z]{5}")
KR_BOARDS = {"kospi": ".KS", "kosdaq": ".KQ"}

def _key(text):
    return "".join(unicodedata.normalize("NFKC", text).casefold().split())


def _company_key(name):
    suffix = r"\b(?:incorporated|inc|corporation|corp|company|co|limited|ltd|plc)\.?$"
    value = re.sub(suffix, "", name.casefold().strip(), flags=re.IGNORECASE).rstrip(" ,.")
    return _key(value)


def _entry(symbol, name):
    exchange, ticker = symbol.split(":", 1)
    return {"id": symbol, "name": name, "ticker": ticker, "exchange": exchange}


def _read(url, limit, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=3) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise ValueError("종목 검색 데이터가 너무 큽니다.")
    return content


def _tradingview(query):
    params = urllib.parse.urlencode({"text": query, "hl": 1, "lang": "ko", "domain": "production"})
    raw = _read("https://symbol-search.tradingview.com/symbol_search/v3/?" + params,
                1_000_000, {"Origin": "https://kr.tradingview.com",
                            "Referer": "https://kr.tradingview.com/", "User-Agent": "Mozilla/5.0"})
    rows = json.loads(raw)["symbols"]
    if not isinstance(rows, list):
        raise ValueError("TradingView 종목 목록 형식이 변경되었습니다.")
    for row in rows:
        clean = lambda field: html.unescape(re.sub(r"</?em>", "", str(row.get(field) or "")))
        symbol = (clean("exchange") + ":" + clean("symbol")).upper()
        if SYMBOL_ID.fullmatch(symbol):
            yield _entry(symbol, clean("description") or clean("symbol")), bool(row.get("is_primary_listing"))


_masters = {}
_master_lock = threading.Lock()


def _us_master(market):
    """Cache each KIS US listing file separately, retaining old data on a timeout."""
    with _master_lock:
        expires, rows, available = _masters.get(market, (0, (), False))
        if expires > time.monotonic():
            return rows, available
        try:
            url = f"https://new.real.download.dws.co.kr/common/master/{market}mst.cod.zip"
            with zipfile.ZipFile(io.BytesIO(_read(url, 2_000_000))) as archive:
                member = archive.getinfo(market.upper() + "MST.COD")
                if member.file_size > 5_000_000:
                    raise ValueError("종목 목록 크기 초과")
                content = archive.read(member).decode("cp949", errors="replace")
            updated = []
            for line in content.splitlines():
                cells = line.split("\t")
                if len(cells) < 8 or cells[2].lower() != market:
                    continue
                symbol = MARKETS[market] + ":" + cells[4].strip().upper().replace("/", ".")
                name = cells[6].strip()
                if name and SYMBOL_ID.fullmatch(symbol):
                    updated.append((symbol, name, _key(name)))
            if not updated:
                raise ValueError("빈 종목 목록")
            rows, available, ttl = tuple(updated), True, 86400
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            available, ttl = False, 90
        _masters[market] = (time.monotonic() + ttl, rows, available)
        return rows, available


def kr_listings(board):
    """KIS published KRX symbol master, including board and security group."""
    suffix = KR_BOARDS[board]
    with _master_lock:
        expires, rows, available = _masters.get(board, (0, (), False))
        if expires > time.monotonic():
            return rows, available
        try:
            filename = f"{board}_code.mst"
            url = f"https://new.real.download.dws.co.kr/common/master/{filename}.zip"
            with zipfile.ZipFile(io.BytesIO(_read(url, 4_000_000))) as archive:
                member = archive.getinfo(filename)
                if member.file_size > 8_000_000:
                    raise ValueError("국내 종목 목록 크기 초과")
                content = archive.read(member)
            updated = []
            for line in content.splitlines():
                code = line[:9].decode("ascii", errors="ignore").strip()
                name = line[21:61].decode("cp949", errors="replace").strip()
                group = line[61:63].decode("ascii", errors="ignore").strip()
                if KR_CODE.fullmatch(code) and name:
                    updated.append(("KRX:" + code, name, code + suffix, group))
            if not updated:
                raise ValueError("국내 종목 목록이 비었습니다.")
            rows, available, ttl = tuple(updated), True, 86400
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            available, ttl = False, 90
        _masters[board] = (time.monotonic() + ttl, rows, available)
        return rows, available


def search_symbols(query):
    query = query.strip() if isinstance(query, str) else ""
    if not 1 <= len(query) <= 80:
        return {"results": [], "notice": "종목명 또는 티커를 80자 이내로 입력하세요."}
    return _search(query, int(time.monotonic() // 60))


@lru_cache(maxsize=160)
def _search(query, cache_minute):
    term = _key(query)
    matches = {}
    notices = []

    def add(item, names, priority):
        normalized = [_key(name) for name in (item["ticker"], *names)]
        rank = (0 if term in normalized else
                1 if any(name.startswith(term) for name in normalized) else
                2 if any(term in name for name in normalized) else 3)
        # TradingView returns same-ranked listings in relevance order.
        score = (rank, priority, len(item["name"]) if priority == 2 else 0)
        if item["id"] not in matches or score < matches[item["id"]][0]:
            matches[item["id"]] = (score, item)

    for symbol, name, aliases in SEARCH_ALIASES:
        names = [name, *aliases.split("|")]
        item = _entry(symbol, name)
        if any(term in _key(value) for value in [item["ticker"], *names]):
            add(item, names, 0)

    try:
        for item, primary in _tradingview(query):
            add(item, [item["name"]], 1 if primary else 3)
    except (ValueError, OSError, KeyError, TypeError):
        notices.append("TradingView 실시간 종목 검색에 연결하지 못했습니다.")

    if re.search("[가-힣]", query) or KR_CODE.fullmatch(query.upper()):
        for board in KR_BOARDS:
            rows, _ = kr_listings(board)
            for symbol, name, yahoo, _group in rows:
                if term in _key(name) or term == _key(yahoo.split(".")[0]):
                    add(_entry(symbol, name), [name, yahoo], 1)

    if re.search("[가-힣]", query):
        complete = True
        for market in MARKETS:
            rows, available = _us_master(market)
            complete = complete and available
            for symbol, name, normalized in rows:
                if term in normalized:
                    add(_entry(symbol, name), [name], 2)
        if not complete:
            notices.append("미국 종목 한글명 목록의 일부를 갱신하지 못했습니다.")
    result = [item for _, item in sorted(matches.values(), key=lambda pair: pair[0])[:15]]
    return {"results": result, "notice": " ".join(notices),
            "exact": [item["id"] for score, item in matches.values() if score[0] == 0]}


def _direct(query):
    term = _key(query)
    for symbol, name, aliases, yahoo in INDICES:
        if term in map(_key, (symbol, symbol.split(":")[1], name, *aliases.split("|"), yahoo)):
            return dict(_entry(symbol, name), yahoo=yahoo)
    matches = []
    for symbol, name, aliases in ALIASES:
        if term in map(_key, (symbol, symbol.split(":")[1], name, *aliases.split("|"))):
            item = _entry(symbol, name)
            # The bundled KRX aliases are specifically KOSPI listings.
            item["yahoo"] = item["ticker"] + ".KS" if item["exchange"] == "KRX" else item["ticker"]
            matches.append(item)
    if len(matches) > 1:
        raise ValueError("같은 이름에 여러 주식 종류가 있습니다. 검색 결과에서 거래소와 종목을 선택하세요.")
    return matches[0] if matches else None


def _provider_entry(item, target):
    exchange, ticker = item["exchange"], item["ticker"]
    yahoo = INDEX_YAHOO.get(item["id"], "")
    if not yahoo and exchange in (*MARKETS.values(), "NYSEARCA", "ARCA", "BATS"):
        yahoo = ticker.replace(".", "-")
    elif not yahoo and exchange == "KRX" and target != "tradingview":
        direct = _direct(item["id"])
        if direct:
            yahoo = direct["yahoo"]
        else:
            for board in KR_BOARDS:
                found = next((row for row in kr_listings(board)[0] if row[0] == item["id"]), None)
                if found:
                    yahoo = found[2]
                    item = _entry(found[0], found[1])
                    break
    if target == "yahoo" and not yahoo:
        raise ValueError("이 거래소의 Yahoo 티커를 확인할 수 없습니다. Yahoo의 거래소 접미사까지 입력하세요.")
    return dict(item, yahoo=yahoo)


def resolve_symbol(query, target="any"):
    """Resolve a student's one-field input. Never invent a KOSPI/KOSDAQ board."""
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 80:
        raise ValueError("종목명 또는 티커 하나를 입력하세요.")
    if target not in ("yahoo", "tradingview", "any"):
        raise ValueError("종목을 조회할 데이터 출처를 확인하세요.")
    query = query.strip()
    key = query.upper()
    direct = _direct(query)
    if direct:
        return direct
    korean_yahoo = re.fullmatch(r"([0-9][A-Z0-9]{5})\.(KS|KQ)", key)
    if korean_yahoo:
        code, suffix = korean_yahoo.groups()
        entry = _direct(code) or _entry("KRX:" + code, code)
        return dict(entry, yahoo=key)
    if SYMBOL_ID.fullmatch(key):
        return _provider_entry(_entry(key, key.split(":", 1)[1]), target)
    # Explicit Yahoo identifiers are usable even when the name service is offline.
    yahoo_format = re.fullmatch(r"(?:\^[A-Z0-9.]+|[A-Z0-9-]+[.=][A-Z0-9]+|[A-Z]+-[A-Z]+)", key)
    if yahoo_format and target != "tradingview" and not re.fullmatch(r"[A-Z]+\.[AB]", key):
        return {"id": "", "name": key, "ticker": key, "exchange": "", "yahoo": key}
    if KR_CODE.fullmatch(key):
        for board in KR_BOARDS:
            match = next((row for row in kr_listings(board)[0] if row[0] == "KRX:" + key), None)
            if match:
                return dict(_entry(match[0], match[1]), yahoo=match[2])
        if target == "tradingview":
            return dict(_entry("KRX:" + key, key), yahoo="")
        raise ValueError("국내 종목의 상장 시장을 확인하지 못했습니다. 코스피는 .KS, 코스닥은 .KQ를 붙여 입력하세요.")
    payload = search_symbols(query)
    rows = payload["results"]
    exact = [r for r in rows if r["id"] in payload.get("exact", ())]
    if not exact:
        named = [r for r in rows if r["exchange"] in MARKETS.values() and _company_key(r["name"]) == _company_key(query)]
        if len(named) == 1:
            return _provider_entry(named[0], target)
    us = [r for r in exact if r["exchange"] in MARKETS.values() and r["ticker"] == key]
    if len(us) == 1:
        return _provider_entry(us[0], target)
    if len(exact) == 1 or (not exact and len(rows) == 1):
        return _provider_entry((exact or rows)[0], target)
    if not exact and not rows and target != "tradingview" and re.fullmatch("[A-Z]{1,6}", key):
        return {"id": "", "name": key, "ticker": key, "exchange": "", "yahoo": key}
    if rows:
        raise ValueError("여러 종목이 일치합니다. 검색 결과에서 원하는 종목을 한 번 선택하세요.")
    raise ValueError("이름이나 티커에 맞는 종목을 찾지 못했습니다. 철자 또는 거래소를 확인하세요.")


def chart_symbol(value, source):
    target = "tradingview" if source == "tradingview" else "yahoo"
    if isinstance(value, str):
        query = value.strip()
        key = query.upper()
        if source == "csv" and SYMBOL_ID.fullmatch(key):
            return key
        # Accept API callers already passing a provider-native ticker.
        if target == "yahoo" and re.fullmatch(r"[A-Z.^=_0-9-]{1,32}", query) and not KR_CODE.fullmatch(query):
            known = _direct(query)
            return known["yahoo"] if known else query
    result = resolve_symbol(value, target)
    return result["id"] if target == "tradingview" else result["yahoo"]
