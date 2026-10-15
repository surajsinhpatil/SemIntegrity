# ADR-0016 — D4 `distribution_construction` remains UNRESOLVED

**Kind:** METHODOLOGY

**Status:** **SUPERSEDED BY ADR-0024, 2026-10-15** — resolved as option A (`T = 1`) frozen as primary, with option C's band `T in {0.5, 1, 2, 4}` reported as sensitivity. Q5 is RESOLVED. The analysis below stands as the reasoning that led there.
**Date:** 2026-09-26
**Relates to:** Q5 · `configs/detectors/d4_distributional.yaml`

This record exists because the choice could not be made from the repository.
Everything in D4 that the specification *does* determine is implemented; this
is the one parameter it does not, and it is not mine to pick.

## The gap

§4.8.6 requires candidate sequences be scored teacher-forced, **length-
normalised to per-token log-probability**, and then compared by Jensen–Shannon
divergence "over the resulting distribution".

Per-token log-probabilities **do not form a probability distribution**. They do
not sum to 1 and are not constrained to do so. A mapping is therefore required,
and JSD magnitudes depend on which mapping is chosen.

## What the repository DOES settle

Two of the three candidates in Q5 can be eliminated from the existing text:

| candidate | status |
|---|---|
| renormalise `exp(sum logprob_i)` | **Eliminated.** Drops length normalisation, which §4.8.6 explicitly requires. |
| `p_i = softmax_i(mean_token_logprob_i)` | The "no temperature" reading, i.e. `T = 1`. |
| `p_i = softmax_i(mean_token_logprob_i / T)`, frozen `T` | The general family. |

So the repository narrows the choice to a **one-parameter family**

```
p_i = softmax_i( mean_token_logprob_i / T ),   T > 0
```

and the only open question is the value of `T`, where `T = 1` is the
no-temperature case.

## Why `T = 1` was NOT simply adopted

It is the obvious default, and adopting it would have been easy. Three reasons
not to:

1. **Q5 states the mapping must be preregistered**, because "JSD magnitudes are
   not comparable across choices". A quantity that must be preregistered cannot
   be fixed by an implementation detail.
2. **The effect is not cosmetic.** `tests/unit/test_d4_distributional.py`
   demonstrates it: identical log-probabilities produce three materially
   different divergences at `T ∈ {0.5, 1.0, 4.0}`, with lower temperature
   sharpening the distribution and raising JSD. That test exists to keep this
   from being argued away later.
3. **`T` interacts with the candidate set.** Candidate sets differ in size and
   in the spread of their log-probabilities, so one `T` does not affect every
   constraint equally. §4.8.6 already forbids cross-constraint absolute
   comparison for a related reason; `T` is a second lever of the same kind.

## Consequences of leaving it open

D4 **cannot be run**. `D4Distributional` takes `builder` as a required argument
with no default, so no code path can produce a JSD without the choice being
made explicitly at the call site.

Everything else is done and tested (27 tests): the teacher-forced scoring
interface, length normalisation, JSD with its bounds and symmetry,
mean-pairwise-within-constraint aggregation, the scope limits, and the
enforcement that D4 exposes no verdict interface at all.

**D4 is not on the critical path.** It is exploratory, it is explicitly not a
detector, and no primary or secondary metric depends on it. Leaving this open
blocks nothing except D4 itself.

## What a decision needs to state

1. the value of `T` (or that the family is rejected for something else);
2. that it is frozen before any test-split evaluation;
3. that reported JSD values are interpretable **only** relative to other values
   computed under the same `T`.

## Options

**A. `T = 1`** — the plain "no temperature" reading of §4.8.6. Simplest to
preregister and to describe in the paper. Reasonable if there is no positive
reason for anything else, but it should be a decision rather than a default.

**B. A different fixed `T`, justified on the dev split** — chosen so the
resulting distributions are neither degenerate nor uniform across the dev
constraints. More defensible empirically, but it consumes dev-split budget and
adds a tuned quantity to the preregistration.

**C. Report JSD under a sensitivity band, e.g. `T ∈ {0.5, 1, 2}`** — treats the
choice as an acknowledged researcher degree of freedom and shows the conclusion
does not hinge on it. Arguably the most honest option for an exploratory
analysis. Costs three times the compute, which is negligible here because D4 is
teacher-forced scoring over a closed candidate set, not generation.

**D. Drop D4 from the study.** It is exploratory, it is not a detector, and
nothing depends on it. A legitimate scope decision rather than a failure.
