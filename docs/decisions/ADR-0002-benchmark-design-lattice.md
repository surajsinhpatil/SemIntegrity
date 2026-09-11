# ADR-0002 — The 120-constraint design lattice

**Kind:** METHODOLOGY

**Status:** PROPOSED — AWAITING RESEARCHER APPROVAL
**Date:** 2026-09-11

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

## Consequences
* Machine-checkable: `design_validator.py` asserts all five properties.
* Schema × domain is *attempted* fully crossed (6 × 5) and relaxed to a balanced
  incomplete allocation where authoring proves infeasible — see Q12.
* Family variants across classes are deliberately **not** semantically
  equivalent; the goal is reduced nuisance variation, not logical identity.
