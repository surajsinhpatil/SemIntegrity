# ADR-0021 — A computed ranking as an ADR-0018 `ranked_source`

**Kind:** METHODOLOGY

**Status:** APPROVED BY RESEARCHER 2026-10-08
**Date:** 2026-10-08

**Amends nothing.** ADR-0018 is unchanged. This ADR records which of two
readings of ADR-0018's existing `RankedSource.query` field is operative.

## Context

Eight cells — `F-HIS-15` ("the longest reign in a named monarchy") and
`F-POL-15` ("the longest-serving holder of a named office"), four classes each —
were recorded as blocked after five research attempts. The stated reason:

> F-HIS-15/F-POL-15 require duration derived from P39 qualifiers, but ADR-0018
> does not currently admit an unregistered ranking-by-derived-duration query.

The measure these themes require is a **duration**. Wikidata has no duration
property for an office-holding: the quantity exists only as the difference
between the `P580` and `P582` qualifiers on a `P39` statement. So:

* the **enumerated** route wants `measure_value` "verbatim as retrieved", and a
  duration is not retrieved, it is computed; and
* the two registered ranked queries (`class_members_ranked_by_measure`,
  `located_members_ranked_by_measure`) both order by `wdt:{measure} ?value`, a
  **direct** numeric property, which a duration is not.

Hence the conclusion that the cells were unauthorable without amending ADR-0018.

## The two readings

ADR-0018 defines `RankedSource` as `name · url · retrieved · snapshot · query ·
rank_of_argmax`, and documents `query` as:

> "the ranked query, **if the ranking was computed**"

**Reading A** (the previous session's): `measure` must name a single direct
Wikidata property, so a computed measure falls outside ADR-0018 and admitting
one would amend it.

**Reading B**: ADR-0018 already provides for computed rankings — that is what
the `query` field is for, and what "if the ranking was computed" means. The
constraint ADR-0018 actually imposes is not *which* property supplies the
measure but that the ranking be **frozen and reproducible**: `snapshot` is
required and non-empty "so a ranking is always backed by an entry in the frozen
cache rather than by a query that happens to return the same answer today".

**Reading B is adopted.** A computed duration ranking satisfies every
requirement ADR-0018 states: the ordering is in the query text, the query is
registered and versioned, the result is cached under ADR-0011, and
`rank_of_argmax: 1` is checkable against that cached result.

## Decision

An axis-5 `ranked_source` may be backed by a **registered** SPARQL query that
computes its ordering measure, on these conditions:

1. **Registered, never inline.** The query lives in
   `configs/kb/sparql_queries.yaml` with a `version` and a `description`, like
   the six existing ones. Inlining a query in authoring code is already
   forbidden and remains so — a test asserts no `SELECT…WHERE` with `wdt:`
   exists in `src/` or `scripts/`.
2. **Deterministic.** The query must contain no `NOW()` and no other
   time-varying term. An open-ended interval is closed against a **frozen
   literal date** recorded in the query text, so a re-run of the same registered
   version returns the same ordering. (`NOW()` was measured during drafting: it
   makes an incumbent's duration grow between runs.)
3. **The measure declares its derivation.** `ComparisonUniverse.measure` must
   state the computation and the properties it reads — e.g. *"reign duration in
   days, computed in the registered query from the P580/P582 qualifiers on
   P39"* — so the record says what was ordered, not merely that something was.
4. **The inputs are separately checked.** The `P580`/`P582` qualifiers the
   duration is computed from are verified by ordinary `claim_interval` /
   `claim_interval_end` evidence checks on the asserted bearer. The ranking
   establishes the ordering; the evidence checks establish the bearer's own
   dates. Neither substitutes for the other.
5. **Frozen.** `snapshot` names the cached entry, as ADR-0018 already requires.

## Enforcement

Unchanged, and all pre-existing: `ComparisonUniverse._coherent` refuses a
`ranked_source` whose `rank_of_argmax != 1`; `Constraint._cross_field` refuses an
extremal constraint promoted without a universe; `resolve_query` refuses an
unregistered name and validates every parameter against `^Q\d+$` / `^P\d+$`.
Condition 2 is enforced by review of the registered query text, which is config
under version control — the same way the other six are.

## Evidence this works

Measured during drafting, against live Wikidata:

```
Monarch of the United Kingdom (Q9134365)
  Q9682    Elizabeth II   1952-02-06 -> 2022-09-08   25782 d   rank 1
  Q280856  George VI      1936-12-11 -> 1952-02-06    5535 d

President of the French Republic (Q191954), 34 holders
  Q2038     Mitterrand    1981-05-21 -> 1995-05-17    5109 d   rank 1
  Q2105     Chirac        1995-05-17 -> 2007-05-16    4382 d
```

Both bearers head their orderings by a wide margin, so `rank_of_argmax: 1` is
not sensitive to a boundary case.

## Scope and consequences

* **Only axis 5**, and only where the theme's measure is a duration. The two
  existing direct-property ranked queries are unaffected, and the enumerated
  route remains the preferred representation for a closed set (ADR-0018 §6:
  axis-5 constraints "are not forced onto `ranked_source`").
* **ADR-0018, ADR-0017, CANON, K=8, the pilot, the Revision-4 matrix, every
  detector and every statistic.** Unchanged. No detector reads the field.
* **What this still does not establish.** Exactly what ADR-0018 already
  disclaimed: that `membership_rule` describes the members, or that the universe
  is the one the constraint text implies. Human review items, unchanged.
