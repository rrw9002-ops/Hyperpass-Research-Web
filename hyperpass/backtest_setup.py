"""Condition previews and single-chart Pine templates. Neither starts a job."""
import json

from .chart_lab import STRATEGIES
from .chart_pine import build_pine
from .market_backtest import validate_request
from .research_desk import title


def preview(payload):
    request = validate_request({key: value for key, value in payload.items() if key != 'name'})
    return dict(request, name=title(payload.get('name') or STRATEGIES[request['settings']['strategy']]))


def pine_template(payload):
    market = payload.get('market')
    if market not in ('KR', 'US'):
        raise ValueError('국내 또는 미국 시장을 선택하세요.')
    settings = payload.get('settings')
    required = {'strategy', 'start_date', 'end_date', 'initial_capital', 'fee_bps', 'slippage_ticks'}
    if not isinstance(settings, dict) or not required.issubset(settings):
        raise ValueError('전략, 검증 기간, 시작금, 수수료와 틱 슬리피지를 입력하세요.')
    if not settings['start_date'] or not settings['end_date'] or settings.get('slippage_mode') != 'ticks':
        raise ValueError('시작일·종료일을 입력하고 Pine 슬리피지를 틱 단위로 지정하세요.')
    currency = 'KRW' if market == 'KR' else 'USD'
    code = build_pine(settings, account_currency=currency)
    if not code:
        raise ValueError('시작 코드를 만들 전략을 선택하세요.')
    return {'code': code, 'market': market, 'currency': currency, 'timeframe': '1D'}


def per_example(root, market):
    if market not in ('KR', 'US'):
        raise ValueError('국내 또는 미국 시장을 선택하세요.')
    record = json.loads((root / 'examples' / 'per-portfolios.json').read_text(encoding='utf8'))[market]
    request = preview({
        'name': record['name'], 'market': market, 'mode': 'custom', 'symbols': record['symbols'],
        'settings': {'strategy': 'sma_cross', 'start_date': record['start'], 'end_date': record['end'],
                     'initial_capital': 10000000 if market == 'KR' else 10000, 'fee_bps': 5, 'slippage_bps': 5},
        'ranking': 'momentum_high', 'lookback': 20, 'max_positions': 1, 'monthly_contribution': 0,
        'dividends': False, 'rebalance': {'frequency': 'daily', 'month': 3},
        'strategy_code': {'version': 1, 'entry': 'ranked', 'exit': 'rank_drop',
                          'factors': [{'field': 'per', 'min': 1, 'max': 15, 'order': 'asc'}]},
        'fundamentals': record['fundamentals'],
    })
    return dict(request, sources=record['sources'], description=record['description'])
