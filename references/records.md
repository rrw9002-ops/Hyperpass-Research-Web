# File-native research records

These are reviewable research notes, not a signed service ledger or authenticated
database. Checksums detect content changes; they do not authenticate an author.
Record the native runtime child identity separately. Never label a note a
TradingCodex receipt, approval, validated trade, or tamper-proof record.

## Layout and lifecycle

Create a unique `trading/runs/<run-id>/` for substantial work (use a real current
timestamp plus an available unique suffix; don't invent a timestamp). Head Manager
creates `mandate.md` with outcome, scope, horizon/as-of, exclusions, method profile,
selected overlay paths/versions and known gaps. Keep it unchanged after dispatch;
material scope changes get a new run or explicit mandate revision and re-review.

Within that directory:

- `sources/<id>.md`: URL or supplied file, provider/publisher, instrument, coverage,
  publication/observation time, actual retrieval time when available, units,
  adjustments, key supported facts and gaps. If time isn't known write `unknown`.
- `data/`: saved source rows actually used, with source IDs and a data dictionary.
- `calculations/<id>/`: input files, code/formulas, observed result and run notes.
- `roles/<exact-role>/<artifact-id>-v1.md`: one role-owned analysis with metadata
  below. Corrections create v2, etc.; never erase the earlier view.
- `acceptance.md`: Head Manager entries mapping artifact version to native child
  identity, observed file readback, acceptance status, reason and next owner.
- `synthesis-v1.md`: one synthesis identity; corrections append numbered versions.
- `judgment-v1.md`: a snapshot of accepted decision-grade synthesis, assumptions,
  falsifiers, update triggers and future resolution criteria. Research only.

Use relative IDs such as `<run-id>/roles/fundamental-analyst/<id>-v1.md` in records.
Do not rely on a mutable `latest.md`. When practical record a computed SHA-256;
if no hashing tool is available say `hash_not_computed`, never fabricate one.
Do not claim immutable storage; the workflow preserves versions by convention.

## Role report metadata

Use a compact YAML frontmatter or clearly labeled metadata section:
`artifact_id`, `run_id`, `role`, `version`, `input_artifact_ids`, `source_ids`,
`source_as_of`, `evidence_readiness`, `action_readiness: research-only`,
`confidence` with reason, `missing_evidence`, `handoff_state`, and
`follow_up_requests` (objects with trigger, suggested_role, question, reason,
materiality). Empty lists are valid. Use real paths and observed identities only.

Canonical evidence readiness is `factual`, `screen`, `decision-grade`, or
`insufficient`. Retain method-specific `decision_readiness` separately:
`factual-baseline` maps to `factual`, `screen-grade` to `screen`,
`ready-for-portfolio-risk` to `decision-grade` only when the evidence supports
that standard, and `not-decision-ready` to `insufficient` or `screen` with the
limiting reason. Action readiness uses the original axis, but this edition
permits only `research-only` or `blocked`; never claim `draft-eligible`.
Handoff/review state is
`accepted`, `revise`, `blocked`, or `waiting`; children propose readiness while
the Head Manager records acceptance. Independent judgment uses the same states.
Keep source quality, confidence and action readiness separate.

Avoid duplicate evidence packs. Create one only for reuse, a cross-role handoff,
or a material source conflict; otherwise cite sources in the role report itself.
Children propose forecasts inside their assigned role record. Only Head Manager
may promote an accepted forecast into `trading/forecasts/`, preserving the
upstream version and exact accepted evidence IDs;
decisions/postmortems in `trading/decisions/`. Follow `context.md` for memory.

Concurrent children get distinct output directories. They never edit a shared
acceptance log or each other's work. Head Manager reads files before acceptance
and checks citations resolve, required inputs are accepted and scope is preserved.
