# Reproducible numeric work

Quote source-reported figures with provenance. For conclusion-driving derived
numbers, preserve exact inputs, periods, units, currency and instrument identity;
write inspectable formulas/code and run them using an actually available native
calculation tool or local runtime. Save the observed outputs and tool/runtime
identity with source references under the assigned run. Use Decimal or suitable
numerical precision for money. Reject non-finite values, unit mismatches and
unjustified denominators. Read `data-qc.md` before accepting results.

No Python installation is required to open or use this kit. If no trustworthy
calculation capability is available, report that the requested numeric conclusion
is uncomputed and limit readiness. Do not call `tcx-calc`, invent a calculation
receipt, or silently substitute mental arithmetic for a material model run.

For DCF, bind revenue growth, margins, tax, reinvestment, working capital,
discount rate, terminal assumptions, net debt and diluted shares to evidence or
explicit scenarios. Reconcile enterprise to equity/per-share value, ensure the
terminal growth/discount relation is valid, and test sensitivities. Reverse DCF
is an expectations test, not proof of intrinsic value. Preserve supported ranges
and abstain when a material base or market anchor is missing.

For strategy performance use `anti-overfit.md`. Preserve every trial, chronological
splits, costs, data vintage and execution assumptions. A chart or simulated fill
does not establish tradable alpha. For unsupported tests use a clear gap; do not
mark an unrun test `pass` or use `not_applicable` to conceal missing evidence.
