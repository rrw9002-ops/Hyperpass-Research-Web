> Research-edition adaptation: source method preserved; service identities and
> persistence are mapped to reviewed file records. This is not authenticated
> provenance. Any draft/approval readiness below describes analysis only; no
> order draft, approval, account access or execution is available. Final action
> readiness always remains `research-only`. Read `../child-contract.md`.

> Absent execution infrastructure limits action readiness only. Do not block
> supported research merely because this edition has no broker adapter or
> approval service. Preserve instrument-specific research/data gaps separately.

# Review Risk

Use this skill before order ticket creation, approval, sizing/hedge decisions, or policy-sensitive escalation.

Research-edition state access:

- Use only user-supplied, dated holdings or portfolio files. Do not query or sync broker accounts. Missing or stale portfolio inputs limit the dependent conclusions.

Universe method:

- Identify asset universe, instrument, intended exposure, unwanted risk, and installed workflow support.
- For public equity and ETF/index, review downside, catalyst risk, drawdown, stress scenarios, liquidity, concentration, factor/sector exposure, tail risk, and policy constraints.
- For crypto, macro/rates/FX/commodities, options, credit signals, and cross-asset overlays, name instrument-specific risk inputs that are missing, such as funding, roll, duration, basis, venue, custody, borrow, margin, spread, or Greeks.
- Use VaR/CVaR, scenario loss, or stress language only when the data and assumptions are explicit; otherwise name the missing inputs.
- If the universe or instrument is not supported by available research methods and data, classify as `not-decision-ready` or `blocked`.

Expected output:

- Universe, instrument, and risk posture
- Downside case
- Thesis break conditions
- Position sizing limit
- Liquidity and volatility risk
- Stress, drawdown, tail-risk, VaR/CVaR, or scenario-loss notes when supportable
- Policy constraints
- Approval readiness concerns
- Go, revise, or reject recommendation
- Source/as-of posture and implementation-readiness gaps

Decision quality fields when applicable:

- `evidence_grade`, `source_freshness`, `source_quality`
- `decision_quality_required`, `decision_readiness`, `confidence`
- `investor_context_gate_required`, `investor_context_gaps`
- `forecast_required`, `forecast_allowed`, `forecast_block_reason`
- `contrary_evidence`, `update_triggers`, `invalidation_conditions`

Role-specific quality:

- State the largest failure mode first.
- Distinguish investment risk, portfolio risk, policy risk, and execution risk.
- Include support gap, stale data, or missing source status when it changes readiness.
- Include explicit stop/revisit conditions when the user asks for decision support.
- Lower confidence when data quality, sample size, regime coverage, or validation setup is weak.
- Give a clear go, revise, reject, or blocked state with reasons.

Write the assigned versioned role report in the current run, following `../records.md`.
