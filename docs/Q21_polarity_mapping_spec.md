# Q21 — Stage 0 polarity mapping: formal specification

**Status:** ADOPTED AND IMPLEMENTED in production Stage 0, 2026-09-26.
Researcher approved it as a **benchmark-validity correction, not a result**.
**Date:** 2026-09-25
**Approved in principle:** researcher chose the polarity-normalised mapping and
the "not-X contradicts any definite X" pair rule (2026-09-25), and directed that
it be formalised and simulated offline before any canonicaliser change.

The 95% CANON threshold, the probe definitions and the preregistration are
**untouched**. Raw pilot outputs are preserved; nothing was regenerated.

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

---

## 7. Simulation results — pilot job 11969, Qwen2.5-3B, K=8

Offline recompute of the 96 existing responses. No new inference.

| | current | proposed |
|---|---|---|
| canonicalisation rate | 66.7% | **94.8%** (still FAIL, by one response) |
| recovered responses | — | **27** |
| remaining INVALID | 32 | **5** |
| D1 coverage | 0.253 | **0.571** |
| mean PSCR | 0.185 | **0.321** |
| perfect-model artifact | **0.643** | **0.000** |

**The 32 INVALIDs, by cause:** 27 polarity mapping · 4 polar-cloze on boolean
constraints · 1 genuine (`K-C4-SCI-01-P04` answered *"Albert Einstein"* to a
year question).

### The artifact scrambled per-constraint ordering, in both directions

| constraint | current | proposed | |
|---|---|---|---|
| K-C1-GEO-01 | 0.667 | 0.250 | ↓ old value was 2 of 3 evaluable pairs |
| K-C1-POL-01 | 0.000 | 0.000 | = |
| K-C1-SCI-01 | 0.000 | 0.476 | ↑ the gold-symbol contradiction |
| K-C2-GEO-01 | 0.286 | 0.476 | ↑ |
| K-C2-POL-01 | **0.533** | **0.000** | ↓↓ highest → perfectly consistent |
| K-C2-SCI-01 | 0.333 | 0.333 | = |
| K-C3-GEO-01 | 0.400 | 0.600 | ↑ |
| K-C3-POL-01 | **0.000** | **0.600** | ↑↑ flawless → among the worst |
| K-C3-SCI-01 | 0.000 | 0.500 | ↑ |
| K-C4-GEO-01 | 0.000 | 0.286 | ↑ |
| K-C4-POL-01 | 0.000 | 0.333 | ↑ |
| K-C4-SCI-01 | 0.000 | 0.000 | = |

Seven rose, two fell, three unchanged. This is the important part: the error was
**not a uniform bias that a constant could absorb**. Any RQ2 answer — how
consistency varies by semantic class, domain or model — computed on the current
pipeline would be wrong in unpredictable directions.

### Why 94.8% and not 99.0%

Five responses remain INVALID. Four are the polar-cloze form of §5(b); one is a
genuine off-target answer. Fixing the four cloze probes would give 1/96 INVALID
= **99.0%**, comfortably past the gate. That is a probe-authoring change inside
the frozen factor lattice (ADR-0003) and needs a decision, not an edit.

### Interpretation limits

One model, twelve constraints, D1 only. D2/D3/D4 are unimplemented and D4's
method is unresolved. No human validation exists, so no detector
precision/recall against gold can be stated. **These numbers validate the
pipeline, not the models.** PSCR 0.321 is not a finding about Qwen2.5-3B.


---

## 8. Implementation notes (2026-09-26)

Adopted into production. `CANONICALISER_VERSION` 1.0 → **1.1**, so the
canonicaliser hash written onto every record changes and outputs produced before
and after are distinguishable.

| change | file |
|---|---|
| `NEGATED` response label | `schemas/enums.py` |
| `NEGATED` carries a `canonical_answer`; `is_evaluable` accepts it | `schemas/response.py` |
| polarity mapping; `probe` is a **required** argument | `canonicalization/canonicaliser.py` |
| pair rule for `NEGATED` | `detectors/d1/exact_match.py` |
| passes probes; `NEGATED` counts as answered-but-wrong | `analysis/pilot_report.py` |

**`probe` is required, not optional.** Canonicalisation that cannot see what was
asked is precisely what produced the 0.643 artifact, so the signature makes the
mistake impossible rather than merely discouraged.

**One rule tightened during implementation.** A polar probe whose answer does not
parse as YES/NO is now `INVALID` rather than falling through to answer-space
matching. A test caught why this matters: on a boolean constraint the answer
space *is* `{YES, NO}`, so `"The answer is yes"` matched `YES` literally and
**bypassed the polarity inversion** — reintroducing on negated probes the exact
artifact the mapping removes. Failing closed is uniform across answer types and
never manufactures an answer the model did not give.

**D0 is unchanged and still `ANSWER`-only.** A symbolic predicate evaluates a
definite answer against the knowledge base; "not Canberra" supplies no value.
Widening D0 to reason over complements is a new methodological choice, not an
implementation detail, so it was left alone. The consequence is a D0 coverage
gap on polar probes answered against the asserted candidate, which
`d0_symbolic.yaml` requires be reported as a result rather than absorbed.

**Tests.** `tests/unit/test_perfect_model_invariant.py` runs production Stage 0
and D1 over the real 12-constraint benchmark and asserts PSCR 0.000 everywhere,
plus that coverage is 1.0 (so the invariant cannot pass vacuously) and that a
deliberately inconsistent model is still detected (so the rule cannot pass by
never firing). `tests/unit/test_polarity_mapping.py` covers affirmative and
negated polar probes across entity, date and boolean, including every
double-negation row. 312 tests pass.

The offline simulation and its tests were removed: with the mapping in
production they compared production against itself and would have been
misleading.


---

## 9. Independent re-run (job 12095, 2026-09-26)

The researcher directed that the mapping be adopted first and the 96 probes
re-generated with **probe wording unchanged**, to see whether the cloze failures
reproduce. They do, exactly.

Job 12095, csis.cn1, 96 generated / 0 resumed, canonicaliser v1.1 applied at
generation time rather than re-scored afterwards:

| | job 11969 re-scored | job 12095 fresh |
|---|---|---|
| ANSWER / NEGATED / ABSTAIN / INVALID | 68 / 4 / 18 / 6 | 68 / 4 / 18 / 6 |
| canonicalisation | 93.75% | 93.75% |
| mean PSCR | 0.300 | 0.300 |
| mean D1 coverage | 0.551 | 0.551 |
| truth accuracy | 0.767 | 0.767 |

`scripts/analysis/compare_runs.py` over the two raw files:

```
exact raw-text match : 96/96  100.00%
ANSWER->ANSWER 68 · ABSTAIN->ABSTAIN 18 · INVALID->INVALID 6 · NEGATED->NEGATED 4
IDENTICAL set of INVALID probes in both runs
```

**Byte-identical**, a day apart, on different nodes (cn4 → cn1), through an
environment that was torn down and rebuilt in between. The six INVALIDs are the
same six probes with the same six texts:

```
K-C1-GEO-01-P06  'Melbourne'          K-C2-SCI-01-P04  'Au'
K-C2-GEO-01-P06  'Canberra'           K-C3-GEO-01-P06  'CANBERRA'
K-C2-SCI-01-P01  'Au'                 K-C4-SCI-01-P04  'Albert Einstein'
```

**Conclusion: the polar-cloze failures are a property of the probe form, not
sampling noise.** Deciding what to do about them (§5b) is a methodology call.

Secondary, and useful beyond this question: this is real evidence for §4.6's
requirement that determinism be VERIFIED rather than assumed. It is not the
whole preregistered check — `configs/inference/determinism_check.yaml` spans 100
prompts, two batch compositions and every model — but it is a genuine component
of it, and the first such evidence the project has.
