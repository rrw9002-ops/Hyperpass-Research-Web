"""Personal Pine indicators, stored alongside the user's research database."""
import re
import uuid

from .provider import ProviderError


class IndicatorStudio:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS personal_indicators(
                       id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL)""")

    def list(self):
        with self.store.connect() as db:
            rows = db.execute("SELECT id, name, code FROM personal_indicators ORDER BY name, id")
            return [dict(id=identity, name=name, code=code) for identity, name, code in rows]

    def save(self, payload):
        name, code = checked_indicator(payload)
        identity = payload.get('id')
        with self.store.connect() as db:
            if not identity:
                identity = uuid.uuid4().hex
                db.execute("INSERT INTO personal_indicators VALUES (?, ?, ?)", (identity, name, code))
            else:
                if not isinstance(identity, str) or not re.fullmatch(r'[0-9a-f]{32}', identity):
                    raise ValueError('저장할 개인 지표를 다시 선택하세요.')
                updated = db.execute("UPDATE personal_indicators SET name=?, code=? WHERE id=?",
                                     (name, code, identity))
                if not updated.rowcount:
                    raise ValueError('수정할 개인 지표가 없습니다.')
        return dict(id=identity, name=name, code=code)


def checked_indicator(payload):
    from .pine_indicator import indicator_title
    name = payload.get('name')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ValueError('지표 이름은 1~120자로 입력하세요.')
    code = payload.get('code')
    if not isinstance(code, str) or not 1 <= len(code.encode('utf-8')) <= 64000:
        raise ValueError('Pine 지표 코드는 64 KB 이내로 입력하세요.')
    indicator_title(code)
    return name.strip(), code


def generate_indicator(provider, prompt):
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
        raise ValueError('지표 설명은 1~4,000자로 입력하세요.')
    schema = {'type': 'object', 'properties': {key: {'type': 'string'} for key in ('name', 'code')},
              'required': ['name', 'code'], 'additionalProperties': False}
    instruction = (
        'Create a TradingView Pine Script v6 indicator for the supplied chart request. '
        'Return a concise name and complete Pine source with //@version=6 and one indicator() '
        'declaration whose title is a literal string. Use overlay=true for price overlays. '
        'Use inputs for adjustable parameters. Prefer confirmed observations and make any pivot '
        'confirmation delay clear in comments. Bound line/label counts. Use only indicator and '
        'drawing functions. Exclude strategies, orders, alerts, and external library imports. '
        'Do not wrap code in Markdown or claim that compilation or chart application has occurred.'
    )
    reply = provider.complete(instruction, {'request': prompt.strip()}, schema=schema, web_search=False)
    try:
        name, code = checked_indicator(reply.get('data') or {})
    except (AttributeError, ValueError, TypeError) as exc:
        raise ProviderError('AI 응답을 Pine 지표로 읽지 못했습니다. 요청을 구체화해 다시 생성하세요.') from exc
    return dict(name=name, code=code, source='ai')
