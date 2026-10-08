# ADR-0003 — Probe factor balancing at K = 8

**Kind:** METHODOLOGY

**Status:** APPROVED BY RESEARCHER 2026-10-06 · resolves Q2
**Date:** 2026-09-11 · approved 2026-10-06

## Context
§4.4.2 requires four probe factors "balanced exactly across classes":
syntax (3) × polarity (2) × register (2) × directionality (2) = 24 cells.
K = 8, so a full crossing inside one constraint is impossible.

## Decision
A fractional design that is **exactly** balanced at class level:

1. (polarity × register × directionality) = 8 cells = K → each constraint carries
   every one of these cells exactly once.
2. Syntax rotates across constraints:
   `syntax(constraint j, cell i) = SYNTAX[(i + j) mod 3]`.

Guarantees (verified in `tests/unit/test_probe_balance.py`):

| Level | Cells | Observations per cell |
|---|---|---|
| per class (30 constraints, 240 slots) | 24 | exactly **10** |
| whole benchmark (960 slots) | 24 | exactly **40** |

### Why syntax carries the within-constraint imbalance

8 is not divisible by 3, so one factor must absorb a 3/3/2 split inside each
constraint. Syntax is chosen deliberately: §4.4.2's stated worry is "more negated
phrasings appearing at C4", i.e. **polarity** imbalance, and polarity × register
× directionality = 8 = K crosses exactly. Rotating a binary factor instead would
place the residue on the one factor the proposal names.

## Consequences
* A class effect cannot be an artefact of unequal factor distribution — which is
  exactly the threat §4.4.2 names.
* Within a constraint, syntax necessarily splits 3/3/2 (8 ∤ 3). Documented as a
  known property, not silently ignored.
* Directionality may change `answer_type` within a constraint. This is expected
  (§4.7) and is what Stage 0 canonicalisation exists to reconcile.
* **`constraint_index` is load-bearing and is now pinned.**
  `factor_design.py` documents it as "the constraint's 0-based position within
  its class", and the builder used to assign it as a running counter in
  **source-file order**, so the order of families in the authoring file
  determined every probe's syntax. `semintegrity.benchmark.ordering` now derives
  it from the records — domain in §4.3's order, then schema index, then cell
  index — so the rotation is reproducible and "stable once the benchmark is
  frozen" is a property rather than a hope. The pilot's families are already in
  §4.3 order, so adopting it re-worded no pilot probe
  (`tests/unit/test_constraint_ordering.py`).
* **Surface wording is not part of this decision.** §4.4.1 defines probe
  equivalence on the formal representation
  (`constraint_id, probe_id, logical_form, subject, predicate, object,
  time_scope, quantifier, polarity, answer_type`), which does not include the
  probe text. Re-wording a syntax level's template therefore changes no factor
  cell and no equivalence class: measured on the 96 pilot probes, the approved
  polar-cloze re-wording changed **0 of 96** formal representations. Earlier
  notes in `HANDOFF.md` and the Q21 spec describing such a re-wording as
  "touching the factor lattice" overstate it; the genuine concern is construct
  validity of the syntax factor, which is assessed per template rather than per
  lattice.
* **§4.4.5 step 4 applies to this design's output.** "Rewrite or discard
  failures; record the discard rate" is part of probe validation, so a template
  that fails validation is rewritten within the protocol and the rate recorded —
  see `docs/PROBE_REWRITE_LOG.md`.
