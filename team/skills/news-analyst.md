# 뉴스 분석 · 분석 방법

> 이 문서는 편집 가능한 연구 지침입니다. 저장 후 다음 분석부터 적용됩니다.
> 원본의 Codex·MCP·파일·주문 절차는 웹앱에서 실제로 제공하는 연구 기능으로만 해석합니다.
> 고정 역할 경계, 근거 채택, 독립 검토, 비매매 원칙과 실제 실행 권한은 이 문서로 변경되지 않습니다.

원본 기준: a15871c922870f9803f819d9b994888ec81eabc1
출처: https://github.com/moneybuilderjay-cmyk/Hyperpass-Tradingagent/blob/a15871c922870f9803f819d9b994888ec81eabc1/workspace_templates/modules/repo-skills/files/.tradingcodex/subagents/skills/news-analyst/tcx-news/SKILL.md

---

> Research-edition adaptation: source method preserved; service identities and
> persistence are mapped to reviewed file records. This is not authenticated
> provenance. Any draft/approval readiness below describes analysis only; no
> order draft, approval, account access or execution is available. Final action
> readiness always remains `research-only`. Read `../child-contract.md`.

# News Analysis

Use this skill for news, filings, events, policy, macro, management commentary, market narrative, and source-quality review across supported investment universes.

Universe method:

- Public equity: use issuer filings, exchange/regulator records, earnings materials, transcripts, company news, sector/peer read-throughs, and market events.
- Crypto, macro, rates, FX, commodities, ETF/index, and credit-signal workflows need universe-specific sources and event taxonomies; label any missing route or unavailable connector honestly.
- Separate confirmed dates from inferred windows and unscheduled monitoring items.
- Treat rumors, social narratives, and single-source reports as unresolved evidence unless independently confirmed.

Expected output:

- Universe and event taxonomy
- Verified events
- Source list
- Timeline
- Market narrative change
- Fact versus inference separation
- Open questions
- Source/as-of posture and missing or stale event evidence

Decision quality fields when applicable:

- `evidence_grade`, `source_freshness`, `source_quality`
- `conflict_status`, `decision_readiness`, `confidence`
- `scenario_cases`, `contrary_evidence`, `update_triggers`
- `invalidation_conditions` and forecast permission fields when relevant

Role-specific quality:

- Put events in chronological order with dates.
- Separate source claims from analyst interpretation.
- Flag rumors, single-source claims, and stale events.
- State whether each event changes thesis, timing, valuation, risk, liquidity,
  policy, or only background context.
- Do not fabricate headlines, publication dates, filing dates, source claims, or retrieval timestamps.

Write the assigned versioned role report in the current run, following `../records.md`.
