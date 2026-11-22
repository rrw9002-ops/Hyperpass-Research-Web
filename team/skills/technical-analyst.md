# 기술 분석 · 분석 방법

> 이 문서는 편집 가능한 연구 지침입니다. 저장 후 다음 분석부터 적용됩니다.
> 원본의 Codex·MCP·파일·주문 절차는 웹앱에서 실제로 제공하는 연구 기능으로만 해석합니다.
> 고정 역할 경계, 근거 채택, 독립 검토, 비매매 원칙과 실제 실행 권한은 이 문서로 변경되지 않습니다.

원본 기준: a15871c922870f9803f819d9b994888ec81eabc1
출처: https://github.com/moneybuilderjay-cmyk/Hyperpass-Tradingagent/blob/a15871c922870f9803f819d9b994888ec81eabc1/workspace_templates/modules/repo-skills/files/.tradingcodex/subagents/skills/technical-analyst/tcx-technical/SKILL.md

---

> Research-edition adaptation: source method preserved; service identities and
> persistence are mapped to reviewed file records. This is not authenticated
> provenance. Any draft/approval readiness below describes analysis only; no
> order draft, approval, account access or execution is available. Final action
> readiness always remains `research-only`. Read `../child-contract.md`.

# Technical Analysis

Use this skill for price, volume, trend, volatility, liquidity, drawdown, market-structure, and setup-quality analysis across supported traded instruments.

Universe method:

- Public equity, ETF/index, listed options context, crypto public market data, FX/rates/commodity proxies, and other traded instruments may be reviewed when source data is available and read-only.
- State the data venue/provider, instrument identifier, timeframe, session/market convention, and as-of timestamp.
- For non-equity instruments, identify unsupported specialist fields such as funding, roll yield, duration, Greeks, borrow, margin, custody, or venue fragmentation rather than pretending they are covered.
- Technical observations are evidence inputs, not trade instructions.

Expected output:

- Universe, instrument, timeframe, and data source
- Trend and momentum
- Support, resistance, and invalidation levels
- Volatility and liquidity notes
- Technical risk
- Setup quality
- Readiness label and missing market-structure inputs

Decision quality fields when applicable:

- `evidence_grade`, `source_freshness`, `source_quality`
- `conflict_status`, `decision_readiness`, `confidence`
- `contrary_evidence`, `update_triggers`, `invalidation_conditions`
- anti-overfit checks when backtest, signal, or model-performance claims appear

Role-specific quality:

- State data date, timeframe, and whether price data is missing or stale.
- State raw-versus-adjusted posture and the adjustment or corporate-action
  policy when it can change the result.
- Distinguish observation from trade recommendation.
- Include invalidation or uncertainty instead of a one-way setup call.
- Label stale or partial market data `screen-grade` or `not-decision-ready`
  only when the affected interval, venue, adjustment, liquidity, or market
  anchor could materially change the setup. Provider-derived data is not an
  automatic downgrade when its identity, timeframe, units, and freshness are
  adequate.
- State when evidence is suggestive rather than conclusive, especially when sample size or regime coverage is thin.
- Explicitly note when live implementation friction may erase paper alpha.
- Explain what the setup does and does not support.

Write the assigned versioned role report in the current run, following `../records.md`.
