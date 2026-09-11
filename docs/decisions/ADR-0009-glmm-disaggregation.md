# ADR-0009 — Disaggregated binomial cells for probe-factor covariates

**Status:** ACCEPTED (researcher, 2026-09-11) · resolves Q4
**Date:** 2026-09-11

## Context
§4.11 specifies a beta-binomial mixed model whose response is
`contradictions / evaluable_pairs` at **constraint × model**, with
`probe_polarity`, `probe_syntax` and `probe_direction` as fixed effects. Those
are **probe**-level attributes, and every event in the numerator is a *pair of
two probes* whose levels generally differ — so as written the covariates have no
defined value at the row's unit of analysis.

## Decision
Disaggregate the binomial cells. The modelling unit becomes
**constraint × model × pair-factor-cell**, where each probe factor is recoded as
an *unordered pair-level* level:

| Factor | Pair-level levels |
|---|---|
| polarity | `aff-aff`, `aff-neg`, `neg-neg` |
| syntax | `dec-dec`, `dec-int`, `dec-clz`, `int-int`, `int-clz`, `clz-clz` |
| direction | `dir-dir`, `dir-rev`, `rev-rev` |

The denominator is the evaluable pairs falling in that cell. Everything else in
the §4.11 formula is unchanged: `class * model_family`, `log(entity_sitelinks)`,
`(1 | schema/constraint)`, `(1 | domain)`.

## Rationale
* Makes the covariates well-defined without abandoning the beta-binomial or
  descending to pair-level modelling, which §4.11 explicitly warns against.
* Preserves overdispersion as the absorber of residual pair dependence.
* Answers the substantive question directly — "do negated-vs-affirmative pairs
  contradict more often than affirmative-vs-affirmative pairs" is exactly what
  §5.5's failure taxonomy wants to quantify.

## Consequences
* Cells are sparse: 28 pairs spread over up to 3 × 6 × 3 = 54 combinations. The
  three factors therefore enter as **separate main effects**, not as a full
  interaction. Cells with zero evaluable pairs contribute no row.
* Row count grows from (120 × 7) to roughly (120 × 7 × non-empty cells), which
  the random intercept for constraint already accounts for.
* This changes a formula stated in the proposal, so it is a **preregistered
  deviation** and must appear in the Phase 4 preregistration and in the paper's
  analysis section, with this ADR as the justification.
* The confirmatory claim is untouched: §4.11 gives it to the cluster bootstrap,
  which never used these covariates.
