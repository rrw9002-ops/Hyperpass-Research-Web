"""Archive locally supported overlay programs and derive observations from the chart's own bars."""
import ast
from collections import deque
from datetime import datetime
import hashlib
import json
import re

ENGINE = "hyperpass-local-overlay/1"
PIVOT_TEMPLATE_SHA = "80ea903c21b58351f835d03be249219da201dec0a18d422e6900aeb15f87826b"
COLORS = dict(zip("orange yellow red green lime teal aqua blue navy purple fuchsia maroon olive silver gray black white".split(),
                  "#ff9800 #fdd835 #f23645 #4caf50 #00e676 #00897b #00bcd4 #2962ff #311b92 #9c27b0 #e040fb #880e4f #808000 #b2b5be #787b86 #363a45 #ffffff".split()))
PALETTE = ["#ffad62", "#85d8c2", "#c2adeb", "#90bdf5"]
FIELDS = ("open", "high", "low", "close", "hl2", "hlc3", "ohlc4")
TOKENS = re.compile(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|//.*|#[a-fA-F0-9]{6}(?:[a-fA-F0-9]{2})?''')
ERROR = "현재 앱 차트에서 검증할 수 없는 개인 지표 코드입니다."


def sha(value):
    return hashlib.sha256(value.encode("utf8")).hexdigest()


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("개인 지표의 정수 범위를 확인하세요.")
    return value


def color(value):
    if re.fullmatch(r"#[a-f0-9]{6}(?:[a-f0-9]{2})?", value, re.I):
        return value
    if value.startswith("color.") and value[6:] in COLORS:
        return COLORS[value[6:]]
    raise ValueError("개인 지표 색을 확인하세요.")


def pivot_plan(lines):
    if not any("ta.pivothigh" in line for line in lines) or len(lines) < 4:
        return None
    template = list(lines)
    values = []
    for i, pattern, default in [(1, r"pivotBars = input.int\((\d+),", "5"),
                                (2, r"lookbackDays = input.int\((\d+),", "365"),
                                (3, r"lineColor = input.color\((color\.[a-z]+|#[a-fA-F0-9]{6}),", "color.orange")]:
        match = re.match(pattern, template[i])
        if not match:
            return None
        values.append(match[1])
        template[i] = template[i][:match.start(1)] + default + template[i][match.end(1):]
    if sha("\n".join(template)) != PIVOT_TEMPLATE_SHA:
        return None
    return {"type": "pivot", "radius": integer(int(values[0]), 1, 100),
            "days": integer(int(values[1]), 1, 3650), "color": color(values[2])}


def compile_overlay(code):
    lines = [TOKENS.sub(lambda m: "" if m[0].startswith("//") else m[0], line).rstrip()
             for line in code.splitlines()]
    lines = [line for line in lines if line.strip()]
    pivot = pivot_plan(lines)
    if pivot:
        return pivot
    fields = {key: {"field": key} for key in FIELDS}
    periods, plots = {}, []
    title, nodes = "", 0

    def args(call, keys):
        if not isinstance(call, ast.Call) or len(call.args) > len(keys):
            raise ValueError(ERROR)
        result = dict(zip(keys, call.args))
        for item in call.keywords:
            if item.arg not in keys or item.arg in result:
                raise ValueError(ERROR)
            result[item.arg] = item.value
        return result

    def number(node):
        if isinstance(node, ast.Name) and node.id in periods:
            return periods[node.id]
        return integer(ast.literal_eval(node), 1, 2000)

    def string(node):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or len(node.value) > 500:
            raise ValueError("지표 이름과 선 이름은 각각 500자 이내여야 합니다.")
        return node.value

    def expr(node, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 80 or depth > 10:
            raise ValueError("개인 지표 계산식이 너무 복잡합니다.")
        if isinstance(node, ast.Name) and node.id in fields:
            return fields[node.id]
        a = args(node, ["source", "length"])
        method = ast.unparse(node.func)
        if method not in ("ta.sma", "ta.ema", "ta.highest", "ta.lowest"):
            raise ValueError(ERROR)
        return {"method": method[3:], "length": number(a["length"]), "input": expr(a["source"], depth+1)}

    try:
        for line in lines:
            if line != line.lstrip():
                raise ValueError(ERROR)
            clean = TOKENS.sub(lambda m: repr(m[0]) if m[0].startswith("#") else m[0], line)
            clean = re.sub(r"^(?:int|float)\s+(?=\w+\s*=)", "", clean)
            statements = ast.parse(clean).body
            if len(statements) != 1:
                raise ValueError(ERROR)
            stmt = statements[0]
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                name, rhs = stmt.targets[0].id, stmt.value
                if name in fields or name in periods:
                    raise ValueError(ERROR)
                if isinstance(rhs, ast.Call) and ast.unparse(rhs.func) == "input.int":
                    a = args(rhs, ["defval", "title", "minval", "maxval", "step"])
                    n = number(a["defval"])
                    if "title" in a:
                        string(a["title"])
                    if any(type(ast.literal_eval(a[k])) is not int for k in ("minval", "maxval", "step") if k in a):
                        raise ValueError(ERROR)
                    if any(k in a and not valid(ast.literal_eval(a[k])) for k, valid in
                           [("minval", lambda x: x <= n), ("maxval", lambda x: x >= n), ("step", lambda x: x > 0)]):
                        raise ValueError(ERROR)
                    periods[name] = n
                elif isinstance(rhs, ast.Constant):
                    periods[name] = number(rhs)
                else:
                    fields[name] = expr(rhs)
                continue
            if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
                raise ValueError(ERROR)
            call = stmt.value
            if isinstance(call.func, ast.Name) and call.func.id == "indicator" and not title:
                a = args(call, ["title", "shorttitle", "overlay"])
                title = string(a["title"])
                if "shorttitle" in a:
                    string(a["shorttitle"])
                if not title or ast.unparse(a["overlay"]) != "true":
                    raise ValueError(ERROR)
            elif isinstance(call.func, ast.Name) and call.func.id == "plot" and len(plots) < 4:
                a = args(call, ["series", "title", "color", "linewidth"])
                label = string(a["title"]) if "title" in a else ast.get_source_segment(clean, a["series"])
                if len(label) > 500:
                    raise ValueError("500자 이내의 선 이름을 지정하세요.")
                shade = a.get("color")
                shade = color(string(shade) if isinstance(shade, ast.Constant) else ast.unparse(shade)) if shade else PALETTE[len(plots)]
                plots.append({"input": expr(a["series"]), "label": label, "color": shade,
                              "width": integer(number(a["linewidth"]), 1, 4) if "linewidth" in a else 2})
            else:
                raise ValueError(ERROR)
    except (KeyError, TypeError, SyntaxError, RecursionError, OverflowError) as exc:
        raise ValueError(ERROR) from exc
    if not title or not plots:
        raise ValueError(ERROR)
    return {"type": "plots", "plots": plots}


def plot_values(spec, bars, cache):
    key = json.dumps(spec, sort_keys=True)
    if key in cache:
        return cache[key]
    field = spec.get("field")
    if field:
        keys = {"hl2": ("high", "low"), "hlc3": ("high", "low", "close"),
                "ohlc4": ("open", "high", "low", "close")}.get(field, (field,))
        values = [sum(bar[k] for k in keys)/len(keys) for bar in bars]
    else:
        source = plot_values(spec["input"], bars, cache)
        n, method = spec["length"], spec["method"]
        values, window, rolling_sum, ema = [], deque(), 0.0, None
        for i, value in enumerate(source):
            if value is None:
                values.append(None)
                continue
            if method == "ema":
                ema = value if ema is None else ema + (value-ema)*2/(n+1)
                values.append(ema)
            elif method == "sma":
                rolling_sum += value
                if i >= n and source[i-n] is not None:
                    rolling_sum -= source[i-n]
                values.append(rolling_sum/n if i >= n-1 and source[i-n+1] is not None else None)
            else:
                while window and window[0] <= i-n:
                    window.popleft()
                while window and (source[window[-1]] <= value if method == "highest" else source[window[-1]] >= value):
                    window.pop()
                window.append(i)
                values.append(source[window[0]] if i >= n-1 and source[i-n+1] is not None else None)
    cache[key] = values
    return values


def overlay_snapshot(chart, request):
    required = {"name", "code", "ohlcv_sha256"}
    if not isinstance(request, dict) or not required <= set(request) <= required | {"parameters"}:
        raise ValueError("첨부할 지표의 이름과 원본 코드, 차트 식별값을 확인하세요.")
    name, code = request["name"], request["code"]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 180 or not isinstance(code, str) or not 1 <= len(code) <= 64000:
        raise ValueError("지표 이름은 1~180자, 코드는 64,000자 이내여야 합니다.")
    bars, timeframe = chart["candles"], chart["timeframe"]
    digest = sha(json.dumps(bars, sort_keys=True, separators=(",", ":")))
    if digest != request["ohlcv_sha256"] or digest != chart["provenance"]["ohlcv_sha256"]:
        raise ValueError("표시한 가격 봉과 저장할 가격 봉의 식별값이 다릅니다. 차트를 다시 여세요.")
    plan = compile_overlay(code)
    if "parameters" in request and request["parameters"] != plan:
        raise ValueError("화면 지표와 저장할 코드의 계산 조건이 다릅니다. 지표 코드를 확인한 뒤 현재 차트에 다시 적용하세요.")
    as_of = chart.get("observation_time") or chart["created_at"]
    observed = datetime.fromisoformat(as_of).timestamp()
    duration = (int(timeframe)*60 if str(timeframe).isdigit() else
                {"d": 90000, "1d": 90000, "w": 691200, "1wk": 691200, "1w": 691200,
                 "m": 2764800, "1m": 2764800, "1mo": 2764800}.get(str(timeframe).lower(), float("inf")))
    last_confirmed = len(bars)-1 if bars[-1]["time"]+duration <= observed else len(bars)-2
    points, cache = [], {}
    if plan["type"] == "plots":
        lines = [{**plot, "values": plot_values(plot["input"], bars, cache)} for plot in plan["plots"]]
        message = " · ".join(line["label"] for line in lines)
        if not any(v is not None for line in lines for v in line["values"]):
            message += " · 계산에 필요한 봉이 부족합니다."
    else:
        r, cutoff = plan["radius"], bars[-1]["time"]-plan["days"]*86400
        for i in range(r, last_confirmed-r+1):
            high = bars[i]["high"]
            if bars[i]["time"] >= cutoff and all(bars[i-k]["high"] <= high and bars[i+k]["high"] < high for k in range(1, r+1)):
                points.append({"index": i, "high": high, "confirmedAt": i+r})
        count = len(points)
        points = points[-501:]
        values = [None]*len(bars)
        previous = None
        for point in points:
            i = point["index"]
            values[i] = point["high"]
            if previous:
                start, hi = previous["index"], previous["high"]
                for j in range(start+1, i):
                    values[j] = hi+(point["high"]-hi)*(j-start)/(i-start)
            previous = point
        lines = [{"label": "고점 사후 연결값", "color": plan["color"], "width": 2, "values": values}]
        message = f"최근 {plan['days']}일 · 확인 고점 {count}개 · 연결선 {max(0, len(points)-1)}개 · {r}봉 뒤 확정된 고점을 사후 연결"
        message += " · 선을 그릴 고점이 아직 두 개 미만입니다." if count < 2 else " · 고점에 마우스를 올리면 확정 봉을 확인할 수 있습니다."
        if bars[0]["time"] > cutoff:
            message += " · 조회한 이력만 사용"
    last_bar = bars[-1]["timestamp"]
    summary = {"name": name.strip(), "engine_version": ENGINE, "code_sha256": sha(code), "ohlcv_sha256": digest,
               "as_of": as_of, "period": {"from": bars[0]["timestamp"], "to": last_bar}, "parameters": plan,
               "latest_values": [{"label": line["label"], "bar_time": last_bar, "value": line["values"][-1]} for line in lines],
               "latest_bar_confirmed": last_confirmed == len(bars)-1, "symbol": chart["symbol"], "timeframe": timeframe,
               "recent_pivots": [{"pivot_time": bars[p["index"]]["timestamp"], "high": p["high"],
                                  "confirmation_bar_time": bars[p["confirmedAt"]]["timestamp"]} for p in points[-5:]],
               "confirmation_rule": "고점은 오른쪽 확인 봉 마감 후에만 알 수 있습니다. 고점을 사후 연결한 선은 당시 신호가 아닙니다."
                                    if plan["type"] == "pivot" else "마지막 봉이 진행 중이면 해당 봉의 지표 값은 잠정값입니다."}
    return {"code": code, "summary": summary, "display": {"points": points, "lines": lines, "message": message}}
