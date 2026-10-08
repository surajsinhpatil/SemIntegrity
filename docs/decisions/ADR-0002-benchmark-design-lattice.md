# ADR-0002 — The 120-constraint design lattice

**Kind:** METHODOLOGY

**Status:** APPROVED BY RESEARCHER 2026-10-06 · resolves the lattice half of Q12
**Date:** 2026-09-11 · approved 2026-10-06

## Context
§4.3 states four counts that must all hold simultaneously: 120 constraints;
30 per class; 6 per domain per class over 5 domains; constraints authored in
*families* that hold nuisance variation constant across classes; and 6–8 schemas
per class each instantiated 4–5 times.

## Decision
The counts close exactly under this lattice:

* **30 families**, each fixed to one domain, each contributing **one constraint
  per class** → 30 × 4 = **120**.
* **6 families per domain** × 5 domains = 30 families → **6 constraints per
  (domain, class)** ✓ and **30 per class** ✓.
* **6 schemas per class × 5 instances** = 30 per class ✓.

Family is the nuisance-control blocking factor (§4.3); schema is the nested
random effect (§4.11); domain is the balancing variable with no inferential
claim attached.

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

## Consequences
* Machine-checkable: `design_validator.py` asserts all five properties.
* Schema × domain is *attempted* fully crossed (6 × 5) and relaxed to a balanced
  incomplete allocation where authoring proves infeasible — see Q12.
* Family variants across classes are deliberately **not** semantically
  equivalent; the goal is reduced nuisance variation, not logical identity.
* The lattice was dry-run before authoring: 120 structural placeholders were
  instantiated and validated by `design_validator.py` with
  `strict_schema_crossing=True`, passing 10/10 rules with schema × domain fully
  crossed, so Q12's balanced-incomplete fallback is **not** invoked at adoption.
  Three cells are recorded in advance as the likeliest to force it
  (`axis 5 / science_technology / C4`, `axis 5 / geography / C4`,
  `axis 4 and axis 6 / biology / C2`).
* `sitelink_matching` passed that dry-run **vacuously** — placeholders carry zero
  sitelinks — and must be re-run against real entities before freeze. §4.3 calls
  entity familiarity "the most damaging alternative explanation for any observed
  class effect", so a degenerate pass is not evidence.
* The id grammar carries no split field and `design_validator.validate()` checks
  `unique_ids` within one split at a time. Test constraints therefore occupy cell
  indices **11..16**, leaving 01..10 to pilot/dev; numbering test 01..06 would
  re-mint all 12 existing pilot ids with no check firing.
  `BenchmarkDesignValidator.validate_global_id_uniqueness` now checks this, and
  the readiness audit runs it.
