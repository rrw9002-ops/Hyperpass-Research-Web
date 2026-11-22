# 기본 분석 · 분석 방법

> 이 문서는 편집 가능한 연구 지침입니다. 저장 후 다음 분석부터 적용됩니다.
> 원본의 Codex·MCP·파일·주문 절차는 웹앱에서 실제로 제공하는 연구 기능으로만 해석합니다.
> 고정 역할 경계, 근거 채택, 독립 검토, 비매매 원칙과 실제 실행 권한은 이 문서로 변경되지 않습니다.

원본 기준: a15871c922870f9803f819d9b994888ec81eabc1
출처: https://github.com/moneybuilderjay-cmyk/Hyperpass-Tradingagent/blob/a15871c922870f9803f819d9b994888ec81eabc1/workspace_templates/modules/repo-skills/files/.tradingcodex/subagents/skills/fundamental-analyst/tcx-fundamental/SKILL.md

---

> Research-edition adaptation: source method preserved; service identities and
> persistence are mapped to reviewed file records. This is not authenticated
> provenance. Any draft/approval readiness below describes analysis only; no
> order draft, approval, account access or execution is available. Final action
> readiness always remains `research-only`. Read `../child-contract.md`.

# Fundamental Analysis

Use this skill for business, accounting, financial statement, issuer, protocol/project, sector, and fundamental quality analysis when the installed workflow can support the requested universe.

Universe method:

- Public equity: analyze business model, financial statement linkage, earnings quality, cash conversion, DuPont-style driver decomposition when useful, management, capital allocation, operating KPIs, source/as-of posture, and evidence gaps.
- ETF/index: analyze constituent, sector, factor, liquidity, passive-flow, and methodology fundamentals only when supported by evidence.
- Crypto public markets: analyze protocol economics, supply, usage, governance, liquidity, and ecosystem fundamentals as research context only.
- Macro/rates/FX/commodities: identify the relevant fundamental transmission channel and call out specialist underwriting gaps rather than inventing unsupported coverage.
- Credit signals may inform common-equity or portfolio downside; do not underwrite debt securities unless a dedicated credit workflow is installed.

Expected output:

- Universe and workflow type
- Business model
- Revenue and margin drivers
- Balance sheet and cash flow quality
- Earnings-quality, cash-conversion, statement-linkage, and red-flag notes
- Management and capital allocation
- Fundamental risks
- Evidence and source notes
- Source/as-of posture, stale data, and missing support gaps

Decision quality fields when applicable:

- `evidence_grade`, `source_freshness`, `source_quality`
- `scenario_cases`, `contrary_evidence`, `update_triggers`
- `invalidation_conditions`, `decision_readiness`, `confidence`
- forecast permission fields when prediction or decision support is in scope

Role-specific quality:

- State what matters most for the company instead of listing generic ratios.
- Explain drivers, risks, and uncertainty in plain causal terms.
- Reconcile filing-derived aggregates to the underlying filing or disclosure:
  identifier/accession, accepted or published time, form, fiscal period, units,
  and amendment posture. For a historical cutoff, use only the version
  available then; a latest company-facts view cannot silently replace it.
- Distinguish issuer/company fundamentals from security actionability; good fundamentals alone are not a buy decision.
- Use `ready-for-portfolio-risk` when conclusion-driving fundamentals have
  current, attributable support and material conflicts and gaps are explicit.
  Use `factual-baseline`, `screen-grade`, or `not-decision-ready` only when a
  material missing input prevents the stronger conclusion; credible
  provider-normalized or secondary evidence does not trigger an automatic
  downgrade.
- Do not fabricate financial metrics, source facts, filings, or validation results.
- Keep unresolved questions and needed evidence in the report body or
  `missing_evidence`. When a
  distinct follow-up proposal is material, encode it as a structured
  `follow_up_requests` object in the report metadata; never submit a
  string list.

Write the assigned versioned role report in the current run, following `../records.md`.
