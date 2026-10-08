# ADR-0020 — Admissible evidence routes for a C4 temporal constraint

**Kind:** METHODOLOGY

**Status:** APPROVED BY RESEARCHER 2026-10-08
**Date:** 2026-10-08

## Context

Authoring stalled on 14 C4 cells — every biology C4 cell and all five axis-5 C4
cells among them — recorded as unauthorable because "the underlying facts have
no machine-checkable P580/P582 interval". That reading came from
`configs/benchmark/design.yaml`:

```yaml
ground_truth:
  temporal_qualifiers_required: [P580, P582]   # start time, end time
```

Read as a hard precondition, it says a C4 constraint is evidenced only by the
validity-interval qualifiers on a statement. Under that reading 14 of the 24
remaining test cells are unauthorable, and because ADR-0002's lattice is
saturated — every (schema, domain) cell holds exactly one constraint, so the
test split is valid only at exactly 120 — the benchmark would have no valid
state at all.

**Two facts contradict that reading.**

1. **Nothing enforces it.** `temporal_qualifiers_required` is read by **zero
   lines of code**. `kb/evidence.py` admits eight check kinds — `claim`,
   `claim_literal`, `claim_time`, `claim_interval`, `claim_interval_end`,
   `claim_cardinality`, `entity_exists`, `sparql_count` — and no validator,
   builder or schema requires an interval kind for class C4.

2. **The approved corpus already departs from it.** The FROZEN pilot's C4 cells
   (`K-C4-GEO-01`, `K-C4-SCI-01`) are evidenced by `claim_time` alone, and
   `K-C4-POL-01` by `claim_interval` + `claim_time`. Of the 15 authored test C4
   cells, **five** (`K-C4-SCI-16`, `K-C4-POL-16`, `K-C4-HIS-16`, `K-C4-POL-14`,
   `K-C4-GEO-14`) are evidenced by `claim_literal` **only**, and
   `K-C4-POL-12` — the approved special axis-2 case — anchors its interval on
   `P571` (inception) via `claim_literal`, not on a qualifier.

So the strict reading is contradicted by the pilot that CANON was measured on
and by a third of the authored C4 cells. It was never the operative rule; it was
an over-strict gloss adopted mid-authoring.

## Decision

**A C4 constraint's temporal anchor may be evidenced by any of the eight
supported check kinds, provided the anchor is a date actually recorded in
Wikidata and the check names the property it reads.**

Specifically admissible, and already in use:

| route | kind | what it reads |
|---|---|---|
| validity interval | `claim_interval` / `claim_interval_end` | P580 / P582 qualifiers on a statement |
| direct date property | `claim_time` | a time-valued property, e.g. P571 inception, P576 dissolved |
| date literal | `claim_literal` | the exact recorded time literal |
| zero-count over a period | `sparql_count` | a registered query, as in `K-C4-POL-12` |

`temporal_qualifiers_required: [P580, P582]` is **retained and reinterpreted**:
it states the *preferred* anchor where a statement carries a validity interval,
not a precondition on the class. Where the fact's temporal structure is carried
by a direct date property instead, that property is the correct anchor and a
qualifier does not exist to be read.

## What this does NOT change

* **No gate is weakened.** Every route is machine-checked against the frozen
  cache, and a failing check still leaves the constraint DRAFT. The requirement
  that the anchor be *recorded in Wikidata and read by a declared check* is
  unchanged — what is rejected is the claim that only two properties may carry
  it.
* **Corroboration is untouched.** Every C4 cell remains
  `corroboration_required` under ADR-0019, and the independent-witness rule is
  the gate on promotion. This ADR does not promote anything.
* **CANON, K=8, the factor lattice, the pilot, ADR-0017, ADR-0018, the Revision-4
  matrix and every detector are unchanged.** No probe text and no answer-type
  allocation depends on which check kind evidences a date.
* **Invented intervals stay forbidden.** The working agreement's "never
  fabricate" rule is the binding constraint. A cell whose fact has *no* recorded
  date on any property is still unauthorable, and is reported as such rather
  than given a plausible one. ADR-0020 widens the set of *properties* that may
  be read; it does not weaken the requirement that something be read.

## Consequences

* **Authoring.** The 14 cells blocked under the strict reading become
  researchable. Feasibility is then a per-cell question about whether Wikidata
  records *any* date for the fact — not a question about qualifiers.
  `K-C4-GEO-12` was confirmed authorable while this ADR was drafted: Eritrea
  (`Q986`) `P571` = `+1993-05-24`, which dates Ethiopia's loss of coastline.
* **Statistics, detectors, CANON.** None.
* **Documentation.** `design.yaml`'s `ground_truth` block gains a comment
  pointing here, so the field is not read as a precondition again.
