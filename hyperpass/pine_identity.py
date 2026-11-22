"""Bind an individual Pine run to the exchange chart study that it created."""
import hashlib
import re
import uuid


# Scan Pine only to identify the span of strategy()'s const-string title argument.
# Strings and comments are tokens so commas, parentheses and declarations in them
# cannot affect the argument boundary. TradingView still checks the original
# expression's type and the rest of the student's program.
_TOKEN = re.compile(
    r'(?P<skip>\s+|//[^\r\n]*|/\*[\s\S]*?\*/)'
    r'''|(?P<quoted>"""(?:\\[\s\S]|(?!""")[^\\])*"""|'''
    r"""'''(?:\\[\s\S]|(?!''')[^\\])*'''|"""
    r'''"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*')'''
    r'|(?P<name>[a-zA-Z_]\w*)|(?P<other>.)', re.DOTALL)
_BAD_TITLE = 'strategy() 선언에서 표시 제목 title의 범위를 확인할 수 없습니다. 첫 인자 또는 title= 인자를 확인하세요.'


def title_span(source):
    tokens = []
    for token in _TOKEN.finditer(source):
        if token.lastgroup == 'skip':
            continue
        if token.lastgroup == 'other' and token[0] in ('"', "'"):
            raise ValueError(_BAD_TITLE)
        tokens.append(token)
    declarations = [i for i,t in enumerate(tokens[:-1])
                    if t[0] == 'strategy' and tokens[i+1][0] == '(' and
                    not source[max(source.rfind('\n',0,t.start()), source.rfind('\r',0,t.start()))+1:t.start()].strip()]
    if len(declarations) != 1:
        raise ValueError(_BAD_TITLE)
    start = declarations[0] + 2
    expected_closes, titles, ordinal = [], [], 0
    for i in range(start,len(tokens)):
        value = tokens[i][0]
        if value in ('(', '[', '{'):
            expected_closes.append({'(':')','[':']','{':'}'}[value])
        elif value in (')',']','}') and expected_closes:
            if value != expected_closes.pop():
                raise ValueError(_BAD_TITLE)
        elif not expected_closes and value in (',',')'):
            arg = tokens[start:i]
            named = len(arg) >= 2 and arg[0].lastgroup == 'name' and arg[1][0] == '=' and (len(arg) == 2 or arg[2][0] != '=')
            if (named and arg[0][0] == 'title') or (not named and ordinal == 0):
                expression = arg[2:] if named else arg
                if not expression:
                    raise ValueError(_BAD_TITLE)
                titles.append((expression[0].start(),expression[-1].end()))
            if value == ')':
                if len(titles) != 1:
                    raise ValueError(_BAD_TITLE)
                return titles[0]
            ordinal += 1
            start = i + 1
        elif value in (']','}'):
            raise ValueError(_BAD_TITLE)
    raise ValueError(_BAD_TITLE)


def source_hash(source):
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def execution_source(original, receipt):
    start,end = receipt['title_span']
    title = receipt['title']
    if not re.fullmatch(r'HP-[0-9a-f]{32}',title) or not 0 <= start < end <= len(original):
        raise ValueError(_BAD_TITLE)
    # Keep the student's const expression in the type-checked branch instead of
    # replacing invalid source with valid code or dropping its comments/lines.
    title_expression = '(true ? "' + title + '" : (' + original[start:end] + '))'
    return original[:start] + title_expression + original[end:]


def new_execution(original, span):
    receipt = {'version':1,'title':'HP-' + uuid.uuid4().hex,'title_span':list(span),
               'original_sha256':source_hash(original)}
    source = execution_source(original,receipt)
    receipt['source_sha256'] = source_hash(source)
    return source,receipt
