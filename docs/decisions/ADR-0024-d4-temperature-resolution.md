# ADR-0024 — D4 `distribution_construction`: `T = 1`, with a reported sensitivity band

**Kind:** METHODOLOGY

**Status:** **APPROVED BY RESEARCHER, 2026-10-15** — "proceed with D4
teacher-forced scoring, reusing cached model weights and stored artifacts
wherever possible". Executed for Qwen2.5-3B as job 15168; the sensitivity band
was computed from the stored log-probabilities with no additional inference,
exactly as this ADR specifies. The other four models were **not** run, by
decision (see `docs/RESULTS_STATUS.md` section 4d).
**Date:** 2026-10-15
**Resolves:** ADR-0016 (OPEN since 2026-09-26) and Q5.
**Relates to:** ADR-0023, `configs/detectors/d4_distributional.yaml`, §4.8.6.

---

## Decision

Adopt ADR-0016's **option A as the frozen primary, together with option C as a
reported sensitivity band**:

```
p_i = softmax_i( mean_token_logprob_i / T ),   T = 1
```

1. **`T = 1` is the preregistered primary value.** It is the only value §4.8.6's
   text determines: the specification requires length normalisation to per-token
   log-probability and mentions no temperature, so `T = 1` is the plain reading
   and every other value is a free parameter.
2. **Frozen before any test-split evaluation.** `T` is recorded in
   `d4_distributional.yaml` and is not to be revisited once D4 has been run on
   the test split.
3. **A sensitivity band `T ∈ {0.5, 1, 2, 4}` is reported alongside**, exploratory,
   so the reader can see whether any qualitative statement depends on the choice.
4. **Reported JSD values are interpretable only against other values computed
   under the same `T`.** Cross-`T` magnitude comparison is forbidden, as is
   cross-constraint absolute comparison (already a §4.8.6 scope limit).

## Why not option B

ADR-0016's option B — fit `T` on the dev split so the distributions are neither
degenerate nor uniform — **is** available under the no-human-validation redesign,
because the criterion reads log-probabilities and needs no labels. It is rejected
anyway:

* it adds a **tuned quantity** to the preregistration of an analysis that is
  explicitly exploratory and on which no primary or secondary metric depends;
* "neither degenerate nor uniform" is itself a researcher choice about what
  counts as degenerate — a degree of freedom wearing empirical clothes;
* it consumes a dev-split GPU run for no gain in the claims D4 can support.

Option A fixes a value that is defensible from the specification; option C
discloses the sensitivity rather than hiding it. Together they are strictly more
honest than a tuned point value.

## What this does NOT do

* **D4 remains EXPLORATORY and is not a contradiction detector.** `D4Distributional`
  exposes no verdict interface and must not acquire one. Its estimand is the
  mean pairwise Jensen–Shannon divergence, within a constraint, between the
  candidate distributions induced by semantically equivalent probes — a measure
  of **distributional instability under paraphrase**. Distributional instability
  is not contradiction, and the two must not be reported under one heading.
* It does not make D4 runnable today. D4 needs **teacher-forced scoring of the
  candidate set, i.e. one GPU run.** Until then D4 is `PENDING`, no longer
  `BLOCKED`: the blocker was this decision, and the remaining requirement is
  compute.
* It does not weaken the existing guard. `builder` stays a required argument
  with no default, so no code path can produce a JSD without the choice being
  made explicitly at the call site.

## Consequences

* `configs/detectors/d4_distributional.yaml` records `temperature: 1.0` and the
  sensitivity band, marked frozen-before-test-evaluation.
* ADR-0016 moves from OPEN to **SUPERSEDED BY ADR-0024**; Q5 moves to RESOLVED.
* The existing test that identical log-probabilities yield materially different
  divergences at `T ∈ {0.5, 1.0, 4.0}` stays, and now documents *why* the band
  is reported rather than warning that the choice is unmade.
* If the researcher declines the GPU run, D4 is **omitted** from the dissertation
  with this ADR recording that the design was resolved and the measurement not
  taken. It is not reported as blocked on a decision.
