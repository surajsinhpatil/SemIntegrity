# ADR-0003 — Probe factor balancing at K = 8

**Kind:** METHODOLOGY

**Status:** PROPOSED — AWAITING RESEARCHER APPROVAL
**Date:** 2026-09-11

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

## Consequences
* A class effect cannot be an artefact of unequal factor distribution — which is
  exactly the threat §4.4.2 names.
* Within a constraint, syntax necessarily splits 3/3/2 (8 ∤ 3). Documented as a
  known property, not silently ignored.
* Directionality may change `answer_type` within a constraint. This is expected
  (§4.7) and is what Stage 0 canonicalisation exists to reconcile.
