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

### Case 1 — T = boolean  ⚠️ CORRECTED 2026-09-25

An earlier draft of this section said "unchanged from current behaviour". **That
was wrong**, and it is the single most consequential error found so far.

Every probe of a boolean constraint is polar. A correct model answers `YES` to
the affirmative form and `NO` to the negated form, and **both mean "the
constraint holds"**. Recording them literally as `ANSWER('YES')` and
`ANSWER('NO')` makes D1 score that pair as a contradiction, because
`EQUIVALENCE_KEY_FIELDS` excludes polarity and the two probes are therefore
compared.

Measured consequence, computed from the benchmark alone with no model output —
a model answering *every* probe with that probe's own `expected_answer`, i.e. a
perfectly self-consistent model, scores:

| constraint type | current PSCR | proposed |
|---|---|---|
| entity / date | **0.714** | 0.000 |
| boolean | **0.571** | 0.000 |
| **mean** | **0.643** | **0.000** |

So the pipeline carries a **PSCR artifact floor of 0.643** before any real
inconsistency exists. The observed 0.185 sits *below* that floor only because
coverage was 0.253 — the INVALID-dropping was discarding most of the pairs that
would have generated the artifact. **Both defects have the same root cause and
they partially cancel**, which is why the resulting number looked plausible.

The rule is the same as case 3, with the canonical values being whether the
proposition holds rather than which entity is named:

```
affirms = (polarity == affirmative) == (response == YES)
   -> DEFINITE("YES") if affirms else DEFINITE("NO")
```

It applies to responses the canonicaliser **already labelled ANSWER**, not only
to INVALIDs — those are precisely the mis-compared ones.

`tests/unit/test_polar_mapping_sim.py` asserts the invariant against the real
pilot benchmark: a perfectly consistent model must score PSCR 0.000 on every
constraint. Any mapping that fails it is wrong by construction.

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
