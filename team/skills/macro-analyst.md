# 매크로 분석 · 분석 방법

> 이 문서는 편집 가능한 연구 지침입니다. 저장 후 다음 분석부터 적용됩니다.
> 원본의 Codex·MCP·파일·주문 절차는 웹앱에서 실제로 제공하는 연구 기능으로만 해석합니다.
> 고정 역할 경계, 근거 채택, 독립 검토, 비매매 원칙과 실제 실행 권한은 이 문서로 변경되지 않습니다.

원본 기준: a15871c922870f9803f819d9b994888ec81eabc1
출처: https://github.com/moneybuilderjay-cmyk/Hyperpass-Tradingagent/blob/a15871c922870f9803f819d9b994888ec81eabc1/workspace_templates/modules/repo-skills/files/.tradingcodex/subagents/skills/macro-analyst/tcx-macro/SKILL.md

---

> Research-edition adaptation: source method preserved; service identities and
> persistence are mapped to reviewed file records. This is not authenticated
> provenance. Any draft/approval readiness below describes analysis only; no
> order draft, approval, account access or execution is available. Final action
> readiness always remains `research-only`. Read `../child-contract.md`.

# Macro Analysis

Use this skill when an investment workflow depends on macro, rates, FX, commodities, policy shocks, liquidity, inflation, funding, central banks, sector read-throughs, or cross-asset transmission.

Universe method:

- Identify the macro universe and instrument/channel: rates, FX, commodities, inflation, labor, growth, liquidity, fiscal policy, central bank policy, sector/macro shock, or cross-asset overlay.
- Treat macro evidence as an input to thesis, valuation, risk, or portfolio fit.
- State data source, region, period, release date, as-of timestamp, and whether the series is revised, delayed, or preliminary.
- Do not pretend that macro research support implies futures, FX, commodity, options, or rates execution support.

Expected output:

- Universe, region, and transmission channel
- Source/as-of posture and key data releases
- Macro facts versus policy/market interpretation
- Cross-asset read-through to the requested security, sector, asset, or portfolio
- Scenario path and what would falsify it
- Confidence, stale data, and missing source gaps
- Open macro questions and missing support

Decision quality fields when applicable:

- `evidence_grade`, `source_freshness`, `source_quality`
- `conflict_status`, `decision_readiness`, `confidence`
- `scenario_cases`, `contrary_evidence`, `update_triggers`
- `invalidation_conditions` and forecast permission fields when relevant

Role-specific quality:

- Distinguish economic data, policy statements, market pricing, user assumptions, and analyst inference.
- State when evidence is suggestive rather than conclusive, especially around regime shifts and small samples.
- For historical or replay work, bind first-release, vintage, or real-time-period
  observations. Label a currently revised series as hindsight evidence rather
  than treating it as known at the historical cutoff.
- Use `screen-grade` or `not-decision-ready` only when a missing market anchor,
  source date, or instrument-specific input materially prevents the requested
  inference. Current attributable institutional, OpenBB/provider, or reputable
  secondary evidence can support stronger readiness without a primary
  duplicate.
- Do not fabricate economic releases, policy dates, market levels, source timestamps, or tool output.

Write the assigned versioned role report in the current run, following `../records.md`.
