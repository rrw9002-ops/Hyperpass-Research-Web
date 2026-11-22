"""Identify editable Pine indicator source before saving or applying to a chart."""
import re


_TOKEN = re.compile(r"""//[^\n]*|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|[a-zA-Z_]\w*|[^\s]""")


def indicator_title(code):
    """Return a literal indicator title that the chart can report back after compile."""
    if not isinstance(code, str) or not code.strip() or "\x00" in code or len(code.encode()) > 200_000:
        raise ValueError("200KB 이하 Pine 지표 코드를 입력하세요.")
    tokens = [m.group() for m in _TOKEN.finditer(code) if not m.group().startswith("//")]
    declarations = [(i, word) for i, word in enumerate(tokens[:-1])
                    if word in ("indicator", "strategy", "library") and tokens[i + 1] == "("]
    if len(declarations) != 1 or declarations[0][1] != "indicator":
        raise ValueError("개인 지표에는 indicator()로 선언한 Pine 코드를 입력하세요.")
    start = declarations[0][0] + 2
    depth, argument, arguments = 0, [], []
    for word in tokens[start:]:
        if depth == 0 and word in (",", ")"):
            arguments.append(argument)
            if word == ")":
                break
            argument = []
        else:
            depth += int(word in ("(", "[")) - int(word in (")", "]"))
            argument.append(word)
    else:
        raise ValueError("indicator() 선언의 닫는 괄호를 확인하세요.")
    title = next((arg[2:] for arg in arguments if arg[:2] == ["title", "="]), arguments[0])
    if len(title) != 1 or title[0][0] not in ("'", '"') or len(title[0]) < 3:
        raise ValueError('차트 적용 결과를 확인할 수 있도록 indicator("지표 이름", ...)에 고정된 제목을 입력하세요.')
    return re.sub(r"""\\(['"\\])""", r"\1", title[0][1:-1])
