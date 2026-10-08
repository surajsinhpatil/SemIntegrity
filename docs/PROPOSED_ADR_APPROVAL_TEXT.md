# Proposed approval text for ADR-0002 and ADR-0003

> **APPLIED 2026-10-06.** The researcher approved A1 and A2, and every edit below
> has been made to `docs/decisions/ADR-0002-benchmark-design-lattice.md` and
> `docs/decisions/ADR-0003-probe-factor-balancing.md`. Both now read
> `APPROVED BY RESEARCHER 2026-10-06`. This file is retained as the record of
> what was proposed and approved; the ADRs themselves are authoritative.
>
> Two additions were made beyond the text below, both consequences of work done
> in the same batch: ADR-0002 now points at
> `validate_global_id_uniqueness`, and ADR-0003's `constraint_index` bullet
> records that the ordering is now derived from the records by
> `semintegrity.benchmark.ordering` rather than from source-file order.

---

## ADR-0002 — benchmark design lattice

### Edit 1 of 3 — the status line

Replace:

```markdown
**Status:** PROPOSED — AWAITING RESEARCHER APPROVAL
**Date:** 2026-09-11
```

with:

```markdown
**Status:** APPROVED BY RESEARCHER 2026-10-06 · resolves the lattice half of Q12
**Date:** 2026-09-11 · approved 2026-10-06
```

### Edit 2 of 3 — record that the lattice is forced, not preferred

Insert after the `## Decision` list, before `## Consequences`:

```markdown
### Why these counts and no others

§4.3 permits 6–8 schemas per class at 4–5 instances each. Of those, only
**6 × 5 = 30** is uniform: 7×4 = 28, 7×5 = 35, 8×4 = 32 and 8×5 = 40 all miss
30. A 7-schema allocation does reach 30 with unequal counts — five schemas at 4
instances plus two at 5 — but puts two schemas at 25% more instances than the
rest, which is what §4.3's "instance counts are balanced so that no schema
dominates a class" exists to prevent. 6 × 5 is therefore adopted as the unique
uniform reading rather than as a preference among equals.

A second property follows and is recorded because it constrains authoring. Given
6 families per domain, 6 schemas per class, one constraint per class per family,
and at most one constraint per (schema, domain) cell, **family necessarily
coincides with (domain, schema index)**: the 30 families *are* the 30
(domain, schema) cells. Family and schema are therefore not independently
assignable, and a schema must be authorable as one of four class variants on a
single family theme. The authoring artefact that expresses this is the six-axis
organisation in `docs/BENCHMARK_COVERAGE_MATRIX.md`.
```

### Edit 3 of 3 — consequences

Append to `## Consequences`:

```markdown
* The lattice was dry-run before authoring: 120 structural placeholders were
  instantiated and validated by `design_validator.py` with
  `strict_schema_crossing=True`, passing 10/10 rules with schema × domain fully
  crossed, so Q12's balanced-incomplete fallback is **not** invoked at adoption.
  Three cells are recorded in advance as the likeliest to force it
  (`axis 5 / science_technology / C4`, `axis 5 / geography / C4`,
  `axis 6 / biology / C2`).
* `sitelink_matching` passed that dry-run **vacuously** — placeholders carry zero
  sitelinks — and must be re-run against real entities before freeze. §4.3 calls
  entity familiarity "the most damaging alternative explanation for any observed
  class effect", so a degenerate pass is not evidence.
* The id grammar carries no split field and `design_validator.validate()` checks
  `unique_ids` within one split at a time. Test constraints therefore occupy cell
  indices **11..16**, leaving 01..10 to pilot/dev; numbering test 01..06 would
  re-mint all 12 existing pilot ids with no check firing.
```

---

## ADR-0003 — probe factor balancing at K = 8

### Edit 1 of 3 — the status line

Replace:

```markdown
**Status:** PROPOSED — AWAITING RESEARCHER APPROVAL
**Date:** 2026-09-11
```

with:

```markdown
**Status:** APPROVED BY RESEARCHER 2026-10-06
**Date:** 2026-09-11 · approved 2026-10-06
```

### Edit 2 of 3 — why the imbalance sits on syntax

Insert after the `## Decision` guarantees table:

```markdown
### Why syntax carries the within-constraint imbalance

8 is not divisible by 3, so one factor must absorb a 3/3/2 split inside each
constraint. Syntax is chosen deliberately: §4.4.2's stated worry is "more negated
phrasings appearing at C4", i.e. **polarity** imbalance, and polarity × register
× directionality = 8 = K crosses exactly. Rotating a binary factor instead would
place the residue on the one factor the proposal names.
```

### Edit 3 of 3 — consequences

Append to `## Consequences`:

```markdown
* **`constraint_index` is load-bearing and must be pinned.**
  `factor_design.py` documents it as "the constraint's 0-based position within
  its class", and `pilot_builder.py` assigns it as a running counter in
  **source-file order**. The order of families in the authoring file therefore
  determines every probe's syntax, and the rotation "must be stable once the
  benchmark is frozen". The canonical ordering is fixed explicitly — by
  (domain, axis) in the order declared in the coverage matrix — rather than
  inherited from file layout.
* **Surface wording is not part of this decision.** §4.4.1 defines probe
  equivalence on the formal representation
  (`constraint_id, probe_id, logical_form, subject, predicate, object,
  time_scope, quantifier, polarity, answer_type`), which does not include the
  probe text. Re-wording a syntax level's template therefore changes no factor
  cell and no equivalence class: measured on the 96 pilot probes, a polar-cloze
  re-wording changed **0 of 96** formal representations. Earlier notes in
  `HANDOFF.md` and the Q21 spec describing such a re-wording as "touching the
  factor lattice" overstate it; the genuine concern is construct validity of the
  syntax factor, which is assessed per template rather than per lattice.
* **§4.4.5 step 4 applies to this design's output.** "Rewrite or discard
  failures; record the discard rate" is part of probe validation, so a template
  that fails validation is rewritten within the protocol and the rate recorded.
```

---

## Not included here, and why

* **No answer-type text.** That decision (§3 of the resolution document) is not
  settled, and it needs its own ADR plus an `OPEN_QUESTIONS.md` entry rather than
  an amendment to either of these.
* **No D0 predicate text.** §5's recommendation touches `d0_symbolic.yaml` and the
  predicate registry, not ADR-0002/0003.
* **No ADR-0007 text.** It is already approved and the recommendation is not to
  reopen it. If answer-type option (b) is chosen, its "dev constraints reuse the
  same schemas" clause needs re-wording — that text is deliberately left unwritten
  until the answer-type decision is made.
