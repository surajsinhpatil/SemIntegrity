# ADR-0018 — A frozen comparison universe for extremal constraints

**Kind:** METHODOLOGY

**Status:** APPROVED BY RESEARCHER 2026-10-07 · **AMENDED 2026-10-07**
**Date:** 2026-10-07

> **Read the amendment at the end of this file.** The self-consistency rule in
> "How it is enforced" below originally compared `gold_answer` against the
> enumerated members. That was the wrong object. The universe now records the
> asserted extremal bearer explicitly as `argmax_qid` / `argmax_label`.

## Context

Axis 5 of the Revision 3 matrix is *Extremal uniqueness*: a superlative over a
closed comparison set, four schemas (`S-C1-05` … `S-C4-05`), 20 of the 120 test
constraints.

**A superlative is not a proposition until the set it ranges over is fixed.**
"The highest summit" is true of Everest, Kilimanjaro or Ben Nevis depending on
whether the universe is the world, Africa or Scotland. §4.3 requires every
constraint to store its source, URL and retrieval date, and ADR-0011 requires
evidence to resolve from the frozen cache — but neither gives a superlative
anywhere to record *what it is a superlative of*.

The existing fields do not cover it:

* `answer_space` is the closed set of candidate **answers** — gold plus
  distractors. `{Kilimanjaro, Mount Kenya, Ras Dashen}` does not state that the
  universe is "summits wholly within Africa"; it is consistent with several
  different universes.
* `constraint_text` and `gold_proposition` can say it in prose, which no
  validator can check.
* `evidence[].query` can hold a ranked query, checkable only as "an Evidence
  record exists".

The authoring plan therefore reported the axis-5 requirement as a gate that
could be stated but not enforced, and offered three options: a structured field,
a required prefix in `ambiguity_notes`, or human review only.

## Decision

**Option 1.** A structured comparison universe is added to the constraint
record and is **required for extremal schemas before they may leave DRAFT**.

Three new models in `semintegrity.schemas.constraint`:

```
ComparisonUniverse
  universe         what is being compared, in words
  membership_rule  how membership is decided, precisely enough to rebuild the set
  measure          the quantity ordered over, with its property
  frozen_at        when the universe was fixed
  members          [UniverseMember]   -- the enumerated set, >= 2
  ranked_source    RankedSource | None -- an authoritative frozen ranking
  note

UniverseMember     label · qid · measure_value (verbatim as retrieved)
RankedSource       name · url · retrieved · snapshot · query · rank_of_argmax
```

**Exactly one** of `members` or `ranked_source` is supplied. Enumeration suits
"the highest summit of a continent"; a ranked source suits "the heaviest
naturally occurring element", whose universe no one would list by hand.

`EXTREMAL_SCHEMA_INDICES = {5}` names the schemas this applies to. Under
ADR-0002's lattice the schema index *is* the axis index, so the constant tracks
the matrix and is pinned against it by a test.

## How it is enforced

* **Hard, in the record itself.** `Constraint._cross_field` refuses to construct
  an extremal constraint claiming `EVIDENCE_VERIFIED`, `HUMAN_VALIDATED` or
  `FROZEN` without a `comparison_universe`. This cannot be bypassed by skipping
  the validator, because the model is the only way a record comes into being.
* **Visible, while DRAFT.** `design_validator._comparison_universe` reports
  missing universes as a warning, so the requirement surfaces during authoring
  rather than at promotion.
* **Self-consistent.** Where the universe is enumerated, the asserted extremal
  bearer must be one of its members, and must be the extremum of the recorded
  measures. (Originally stated in terms of `gold_answer`; see the amendment.)
* **Frozen, not live.** `RankedSource.snapshot` is required and non-empty, so a
  ranking is always backed by an entry in the frozen cache rather than by a
  query that happens to return the same answer today (ADR-0011).
* **Prose is not accepted.** The check consults `comparison_universe` and
  nothing else. A full comparison set written into `ambiguity_notes` does not
  satisfy it, and a test asserts that — a requirement verified by looking for
  prose is enforced in name only.

## Scope

**Only the four axis-5 schemas.** The other 20 are unaffected: the field
defaults to `None`, is not required at any status, and a test covers all five
other schema indices promoting without one. The 12 existing pilot constraints
predate the field, carry `None`, and still load unchanged.

The field is marked `DERIVED`, like `answer_type`, `answer_space`,
`gold_answer` and `answer_aliases`: it is not one of §4.3's 17 fields, and it is
added because §4.3's own ground-truth requirement cannot otherwise be met for a
superlative.

## Consequences

* **Authoring.** 20 of the 120 test constraints need a universe recorded before
  promotion. For an enumerated set that means every member's QID and measured
  value; for a ranked source, the query, its frozen snapshot key and gold's
  rank. This is the heaviest evidence burden of the six axes and was already
  flagged as such in the authoring plan.
* **Reproducibility.** The comparison becomes re-checkable from the record
  alone, which is the point: a superlative verified against a live endpoint is
  verified against whatever that endpoint says later.
* **Detectors.** None. D0's `EXCL` behaviour on `S-Cx-05` is unchanged, and no
  detector reads the field. D4 and the CANON result are untouched.
* **Statistics.** None.
* **What this does not do.** It does not make the *semantics* of a superlative
  machine-checkable — nothing verifies that `membership_rule` really describes
  `members`, or that the universe is the one the constraint text implies. Those
  remain human review items, as do axis-2 disjointness and axis-3 transitive
  chains. The gate establishes that the universe is **recorded and frozen**, not
  that it is **correct**.

---

# Amendment 2026-10-07 — the asserted extremal bearer

**Approved by the researcher.** Amends ADR-0018 only. It does not change axis-5
methodology or coverage: the same 20 cells, the same two representations.

## 1. The original rule compared the wrong object

ADR-0018 required, for an enumerated universe, that **`gold_answer` be one of
its members**, reasoning that "a superlative cannot be true of something outside
the universe it ranges over". The reasoning is right; the field was wrong.

## 2. ADR-0017 Option B invalidated the assumption

That rule silently assumed the gold answer *is* the extremal bearer — true only
while axis 5 carried an `entity` answer type. ADR-0017's Option B amendment
(2026-10-07) makes **axis 5 `boolean` for all four classes**, so:

```
gold_answer       = YES or NO
extremal bearer   = an entity, named in the proposition
```

`"YES"` is never a summit, so the check could not be satisfied by any axis-5
constraint. All **20** were blocked from `EVIDENCE_VERIFIED` by the enumerated
route — a `ranked_source` universe escaped only because the membership check
applied solely when `members` was non-empty.

## 3. What must actually be checked

The **asserted extremal bearer** — the entity the constraint claims is the
extremum — not the Boolean truth value. The truth value says whether the claim
holds; the bearer is what the claim is *about*. Those are different objects and
only the second belongs in the universe.

## 4. The schema now records it explicitly

```
ComparisonUniverse
  + direction      'max' | 'min'   -- which extremum the superlative names
  + argmax_qid     ^Q\d+$          -- the entity ASSERTED to be the extremum
  + argmax_label                   -- its label; must match its member
```

Enforced:

* `argmax_qid` must be among `members[].qid`, and `argmax_label` must equal that
  member's label;
* the bearer must be the extremum of the **recorded** `measure_value`s, in the
  recorded `direction`. Where a value is not numeric the relationship is not
  machine-checkable and is **not checked** — a pass there would be a check that
  cannot fail;
* for a `ranked_source`, the bearer must head the ordering (`rank_of_argmax` = 1);
* at constraint level the bearer must be one of the constraint's own
  `entity_qids`, so a universe about a different entity cannot be attached;
* **no member or bearer may be labelled `YES` or `NO`.** This guard exists
  because the superseded check was once satisfied by enumerating a member
  labelled `"YES"` — nonsense that passed.

`direction` is required rather than defaulted: whether the bearer is the maximum
or the minimum is load-bearing, and a default would let "the earliest" be
checked as "the latest".

## 5. The universe is answer-type independent

The bearer is recorded, never inferred from `gold_answer`. The representation
works unchanged whether axis 5 is boolean, entity or date, so a future
answer-type decision cannot invalidate it the way Option B invalidated the
original rule. A negative claim (gold `NO`) is still about a universe and a
bearer; the truth value is orthogonal.

## 6. Both representations remain valid

Enumerated sets and ranked sources are both still permitted, and **axis-5
constraints are not forced onto `ranked_source`**. Enumeration suits a
closed set ("the highest summit of a continent"); a ranked source suits a
universe no one would list by hand ("the heaviest naturally occurring element").

## `rank_of_gold` was RENAMED, not reinterpreted

The field was documented as *"gold's position in the ranking"*. Under Option B
the gold answer is YES/NO and has no position in a ranking of summits, so the
name denoted the wrong object. Keeping it beside `argmax_qid` would have created
two meanings for one field, so it is **renamed to `rank_of_argmax`** and now
refers to `argmax_qid`. Nothing retains the old meaning, and no authored record
used the old name — the rename touched code, tests and documentation only.

## Consequences

* **Authoring.** Each of the 20 axis-5 constraints records `direction`,
  `argmax_qid` and `argmax_label` in addition to the universe. Still the heaviest
  evidence burden of the six axes.
* **Detectors, statistics, CANON, the matrix, K, the factor lattice.** Unchanged.
  No detector reads the field.
* **What this still does not establish.** That `membership_rule` genuinely
  describes `members`, or that the universe is the one the constraint text
  implies. The gate establishes that the bearer is recorded, inside its universe,
  and extremal by the recorded measures — not that the universe is the right one.
  That stays a human review item.
