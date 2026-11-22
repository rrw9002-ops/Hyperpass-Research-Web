# 독립 판단 검토 · 분석 방법

> 이 문서는 편집 가능한 연구 지침입니다. 저장 후 다음 분석부터 적용됩니다.
> 원본의 Codex·MCP·파일·주문 절차는 웹앱에서 실제로 제공하는 연구 기능으로만 해석합니다.
> 고정 역할 경계, 근거 채택, 독립 검토, 비매매 원칙과 실제 실행 권한은 이 문서로 변경되지 않습니다.

원본 기준: a15871c922870f9803f819d9b994888ec81eabc1
출처: https://github.com/moneybuilderjay-cmyk/Hyperpass-Tradingagent/blob/a15871c922870f9803f819d9b994888ec81eabc1/workspace_templates/modules/repo-skills/files/.tradingcodex/subagents/skills/judgment-reviewer/tcx-judgment/SKILL.md

---

> Research-edition adaptation: source method preserved; service identities and
> persistence are mapped to reviewed file records. This is not authenticated
> provenance. Any draft/approval readiness below describes analysis only; no
> order draft, approval, account access or execution is available. Final action
> readiness always remains `research-only`. Read `../child-contract.md`.

# Agent Judgment Review

Use this procedure when an accepted decision-oriented artifact needs
independent challenge. Adjudicate the conclusion; do not merely accumulate
objections or default to neutrality.

Treat the current user mandate, Investor Context, sealed Investment Brain, and
sealed Strategy as the governing frame for this run:

- Brain supplies inquiry priorities, hypotheses, interpretation, and
  falsifiers.
- Strategy supplies applicable decision rules.
- Reviewed file-native evidence controls whether their factual conditions hold.
- Judgment tests the evidence-to-interpretation-to-conclusion link.

You may overturn or qualify the current conclusion when that link fails under
the same frame. Never silently replace the mandate, Brain, or Strategy. If the
frame appears inapplicable or repeatedly defective, preserve that as a separate
`frame concern` for Head Manager or later postmortem; it does not amend the
current run.

Inputs:

- exact conflict or review question, the decision being adjudicated, and the
  downstream decision it can change
- a compact judgment frame containing the applicable mandate, Brain-derived
  questions or falsifiers, Strategy rules, and Investor Context constraints
- accepted, reviewed file-native Artifact IDs with exact file versions, observed child attribution and handoff states; read those versions by exact path
- source/as-of metadata, source trust notes, and forecast fields
- stated missing evidence, blocked actions, and downstream recipient

Treat paths and compact summaries as navigation aids, never substitutes for
exact accepted file versions and observed child attribution, or the exact conflict question. Return
`waiting` when a required accepted input or the conflict question is missing.

Choose the strongest task-relative countercase. Bull-versus-bear is useful for
directional investment claims, but do not force it onto every request; use an
appropriate alternative hypothesis, adverse scenario, assumption challenge, or
claim-versus-refutation for the actual decision.

Make the following explicit in concise professional prose:

- adjudicated conclusion under the governing frame: maintain, change, qualify,
  or abstain
- material delta from the reviewed conclusion and the decisive reason
- strongest supporting evidence
- strongest contrary case and whether it survives
- weak, stale, missing, or discounted source posture
- overconfidence risk
- assumptions that would change the conclusion
- source trust notes
- update triggers
- invalidation conditions
- frame compliance and any separate frame concern
- owning role for any required revision
- review outcome: `accepted`, `revise`, `blocked`, or `waiting`

Evidence weighting:

- Require official source-of-record evidence when exact issuer, regulator,
  exchange, filing, contractual, or policy status is material.
- Treat management claims as source claims until independently supported.
- Treat market-derived evidence as useful but timestamp-sensitive.
- Treat attributable OpenBB/provider data, credible institutional data, and
  reputable secondary reporting as usable evidence for the claims and periods
  they competently cover. They may support a final conclusion without a primary
  duplicate when attribution, freshness, and coverage are adequate and no
  material conflict remains.
- Discount stale evidence, unsupported assumptions, and sources with missing
  as-of or retrieved-at posture.

Outcome rules:

- Use `accepted` when conclusion-driving claims have fit-for-purpose support
  and contrary evidence, source trust, update triggers, and invalidation
  conditions are explicit enough for downstream use. The adjudicated conclusion
  may maintain, change, qualify, or abstain; `accepted` means the review itself
  is downstream-ready. Do not request revision
  solely because support is non-primary.
- Use `revise` when an owning role can fix weak evidence, missing source
  posture, unsupported assumptions, or unclear forecast/update fields.
- Use `blocked` when the conclusion depends on unavailable evidence, policy
  conflicts, missing profile context, or unsupported downstream authority.
- Use `waiting` when required upstream artifacts or accepted handoff state are
  missing.

Review-specific quality:

- Challenge the artifact's application of evidence; do not produce replacement
  analyst work or introduce a new investment philosophy.
- Name and adjudicate the best objection instead of averaging conflict into
  false consensus.
- Lower confidence when source trust, freshness, coverage, or contradiction is
  weak.
- When Decision Memory is introduced after an independent current view,
  disclose whether and why it changed the adjudication. Treat Memory as
  evidence, never authority.
- Do not create order tickets, approvals, broker actions, execution requests,
  strategy changes, policy changes, or forecast ledger records from this review
  alone.
