# 포트폴리오 · 분석 방법

> 이 문서는 편집 가능한 연구 지침입니다. 저장 후 다음 분석부터 적용됩니다.
> 원본의 Codex·MCP·파일·주문 절차는 웹앱에서 실제로 제공하는 연구 기능으로만 해석합니다.
> 고정 역할 경계, 근거 채택, 독립 검토, 비매매 원칙과 실제 실행 권한은 이 문서로 변경되지 않습니다.

원본 기준: a15871c922870f9803f819d9b994888ec81eabc1
출처: https://github.com/moneybuilderjay-cmyk/Hyperpass-Tradingagent/blob/a15871c922870f9803f819d9b994888ec81eabc1/workspace_templates/modules/repo-skills/files/.tradingcodex/subagents/skills/portfolio-manager/tcx-portfolio/SKILL.md

---

> Research-edition adaptation: source method preserved; service identities and
> persistence are mapped to reviewed file records. This is not authenticated
> provenance. Any draft/approval readiness below describes analysis only; no
> order draft, approval, account access or execution is available. Final action
> readiness always remains `research-only`. Read `../child-contract.md`.

> Absent execution infrastructure limits action readiness only. Do not block
> supported research merely because this edition has no broker adapter or
> approval service. Preserve instrument-specific research/data gaps separately.

# Portfolio Review

Use this skill to evaluate portfolio fit before an order ticket is drafted or before an investment view is escalated into risk/sizing work.

Research-edition state access:

- Use only user-supplied, dated holdings or portfolio files. Do not query or sync broker accounts. Missing or stale portfolio inputs limit the dependent conclusions.

Universe method:

- Identify asset universe, instrument, account/context, benchmark, existing exposure, and whether the installed harness supports the instrument.
- Public equity and ETF/index reviews should consider active weight, sector/factor exposure, liquidity, concentration, benchmark comparison, rolling contribution, timing attribution, and opportunity cost when data exists.
- Use Brinson-style allocation/selection language, factor attribution, or timing attribution only when holdings, benchmark, and return data are explicit; otherwise name the missing inputs.
- Crypto, macro, FX, rates, commodities, options, and credit-linked exposures require instrument-specific implementation inputs; mark missing support as `not-decision-ready` rather than sizing from thin context.
- Separate portfolio fit from personal investment advice.

Expected output:

- Universe, instrument, and portfolio context
- Existing exposure
- Position size context
- Concentration risk
- Liquidity and holding period fit
- Opportunity cost
- Performance attribution or benchmark-relative contribution when supportable
- Portfolio recommendation
- Draft readiness: ready, revise, or no-order
- Source/as-of posture and missing implementation inputs

Decision quality fields when applicable:

- `evidence_grade`, `source_freshness`, `source_quality`
- `decision_quality_required`, `decision_readiness`, `confidence`
- `investor_context_gate_required`, `investor_context_gaps`
- `forecast_required`, `forecast_allowed`, `forecast_block_reason`
- `contrary_evidence`, `update_triggers`, `invalidation_conditions`

Role-specific quality:

- Tie sizing and fit to the user's stated portfolio context.
- Name concentration, correlation, liquidity, and opportunity-cost assumptions.
- State the binding constraint and whether the output is `screen-grade`, `ready-for-portfolio-risk`, `ready-for-draft`, or `not-decision-ready`.
- Do not fabricate positions, cash, costs, capacity, or user constraints.
- State whether the next step is review-only, ready for risk review, or ready for draft.

Write the assigned versioned role report in the current run, following `../records.md`.
