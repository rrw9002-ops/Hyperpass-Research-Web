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


def _key(text):
    return "".join(unicodedata.normalize("NFKC", text).casefold().split())


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

    for symbol, name, aliases in ALIASES:
        names = [name, *aliases.split("|")]
        item = _entry(symbol, name)
        if any(term in _key(value) for value in [item["ticker"], *names]):
            add(item, names, 0)

    try:
        for item, primary in _tradingview(query):
            add(item, [item["name"]], 1 if primary else 3)
    except (ValueError, OSError, KeyError, TypeError):
        notices.append("TradingView 실시간 종목 검색에 연결하지 못했습니다.")

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
    return {"results": result, "notice": " ".join(notices)}
