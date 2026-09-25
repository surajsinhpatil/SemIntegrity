# Q21 — Stage 0 polarity mapping: formal specification

**Status:** SPECIFICATION ONLY — not implemented, not adopted.
**Date:** 2026-09-25
**Approved in principle:** researcher chose the polarity-normalised mapping and
the "not-X contradicts any definite X" pair rule (2026-09-25), and directed that
it be formalised and simulated offline before any canonicaliser change.

Nothing in `src/` has been changed. The 95% CANON threshold and the
preregistration are untouched.

---

## 1. What a probe expects is already recorded

Every probe carries `expected_answer`. Verified against the pilot benchmark,
with no exceptions:

| check | result |
|---|---|
| polar probe ⟺ `expected_answer ∈ {YES, NO}` | clean partition |
| polar non-boolean probes naming the gold answer in their text | **36 / 36** |
| `expected_answer` follows polarity (affirmative→YES, negated→NO) | **36 / 36** |

So no text parsing is needed to classify a probe, and the candidate a polar
probe asserts is the constraint's gold answer `g`.

## 2. Probe inventory: answer_type × syntax × polarity

All 96 pilot probes. "open" expects a member of the answer space; "polar"
expects YES/NO.

| answer_type | syntax | affirmative | negated |
|---|---|---|---|
| **boolean** | cloze / declarative / interrogative | 8 polar each | 8 polar each |
| **entity** | cloze / declarative / interrogative | 2 open + 2 polar each | 4 polar each |
| **date** | cloze / declarative / interrogative | 2 open + 2 polar each | 4 polar each |

Totals: boolean 48 polar; entity 6 open + 18 polar; date 6 open + 18 polar.

**Syntax does not determine the answer space.** Every syntax appears in both
open and polar forms. Any rule keyed on syntax alone would be wrong.

## 3. The mapping

Let `C` be the constraint (`answer_type` T, `answer_space` S, gold `g`), `P` the
probe (polarity π, `expected_answer` e), and `r` the raw response.

### Case 1 — T = boolean
All probes polar; `S = {YES, NO}`. **Unchanged from current behaviour.** The
current INVALID rate here is 8.3%, and those failures are the cloze cue problem
of §5, not a mapping gap.

### Case 2 — T ∈ {entity, date}, probe open (e ∉ {YES, NO})
**Unchanged.** Match `r` against `S` exactly as now.

### Case 3 — T ∈ {entity, date}, probe polar (e ∈ {YES, NO})
This is the gap. §4.7 already requires that *"Is A the X of B?"* and *"What is
the X of B?"* reach a common canonical space; Stage 0 does not implement it.

1. Parse `r` as a boolean `b`. **Strict**: only a leading yes/no token counts.
   `"The answer is yes"` does **not** parse — treating it as polar would invent
   data. Non-parsing → remains INVALID.
2. Apply
   ```
   affirms = (π == affirmative) == (b == YES)
   ```

   | π | `r` | reading | result |
   |---|---|---|---|
   | affirmative | YES | *"Is X the capital?" → yes* | `DEFINITE(g)` |
   | affirmative | NO | *"Is X the capital?" → no* | `NEGATED(g)` |
   | negated | YES | *"Is it false that X…?" → yes* | `NEGATED(g)` |
   | negated | NO | double negation | `DEFINITE(g)` |

## 4. Pair semantics for `NEGATED`

Per the researcher's decision, `NEGATED(x)` is **evaluable** and contradicts a
definite `x`:

| a | b | contradiction? |
|---|---|---|
| `DEFINITE(x)` | `DEFINITE(y)` | iff `x ≠ y` |
| `DEFINITE(x)` | `NEGATED(y)` | iff `x = y` |
| `NEGATED(x)` | `NEGATED(y)` | never — jointly satisfiable |

Symmetric by construction, and unit-tested as such: PSCR counts unordered pairs,
so an asymmetric rule would make the metric depend on iteration order.

## 5. Two limitations that are properties of the design, not of the mapping

**(a) Polar probes cannot name a non-gold answer.** A polar probe yields only
`g` or `¬g`; it can never yield "Sydney". So polar probes detect `g`/`¬g`
contradictions and never `g`/other-member ones. Because all 36 polar probes
assert the **gold** answer, **no polar probe in this benchmark tests a
distractor** — nothing asks *"Is Sydney the capital of Australia?"*. For the
120-constraint build, consider recording an explicit `asserted_candidate` on each
probe so polar probes can assert distractors and the mapping need not infer the
candidate from `gold_answer`.

**(b) The polar cloze form gives no cue.** Two distinct cloze forms exist:

```
open  : "The capital of Australia is ___."                     expects Canberra
polar : "Au is the symbol on the periodic table of gold: ___"  expects YES
```

The polar cloze `"<assertion>: ___"` does not signal that YES/NO is wanted, and
the model fills the blank with an entity. All four boolean-constraint INVALIDs
are this form (`'Au'`, `'Au'`, `'Canberra'`, `'CANBERRA'`). **The mapping does
not fix these**, and should not: it is a probe-authoring issue, not a
canonicalisation one. Options — reword to cue the answer type, drop polar cloze
from the factor design, or accept it as measured surface sensitivity — are a
separate decision, and changing probe wording touches the frozen factor lattice
(ADR-0003).

## 6. Status

Implemented **only** as an offline simulation in
`scripts/analysis/simulate_polar_mapping.py`, with the truth table and pair
semantics unit-tested in `tests/unit/test_polar_mapping_sim.py` (23 tests). The
production canonicaliser, D1 and the schemas are untouched pending the
simulation results.
