# Pilot benchmark — three worked examples

Generated from the real records by `scripts/benchmark/make_examples_doc.py`, so it cannot drift from the data. **12 constraints · 96 probes · all DRAFT · split frozen: no.**

Full inspection of all twelve:

```bash
python scripts/benchmark/inspect_pilot.py
```

These three are chosen to span three classes, three domains and all three answer types, and the third deliberately includes the constraint carrying a recorded source discrepancy — an example set that showed only the clean cases would misrepresent the benchmark.

---

## 1. `K-C1-GEO-01` — Atomic — a single proposition with direct mutual exclusion

| | |
|---|---|
| **Class** | C1 |
| **Domain** | geography |
| **Family** | F-GEO-01 (schema S-C1-01) |
| **Answer type** | entity |
| **Ground truth** | **Canberra** |
| **Answer space** | Canberra, Sydney, Melbourne |
| **Status** | **DRAFT** — 1/1 machine checks pass; no human review |

**In plain English:** A country has exactly one capital city; the capital of Australia is Canberra.

**Formal representation:** `capital_of(Australia) = ?x`  
**D0 predicate:** `c1_mutual_exclusion`

**Gold proposition:** The capital city of Australia is Canberra.

**Entities:** Australia (`Q408`, 399 sitelinks), Canberra (`Q3114`, 213 sitelinks)

### All 8 probes

| Probe | In 5-probe run | Syntax | Polarity | Register | Direction | Expects | Question |
|---|---|---|---|---|---|---|---|
| `P01` | yes | declarative | affirmative | formal | direct | **Canberra** | The capital city of Australia is |
| `P02` | yes | interrogative | affirmative | formal | reverse | **YES** | Is Canberra the capital city of Australia? |
| `P03` | yes | cloze | affirmative | colloquial | direct | **Canberra** | The capital of Australia is ___. |
| `P04` | yes | declarative | affirmative | colloquial | reverse | **YES** | Canberra is the capital of Australia — YES or NO? |
| `P05` | yes | interrogative | negated | formal | direct | **NO** | Is it false that the capital city of Australia is Canberra? |
| `P06` | — | cloze | negated | formal | reverse | **NO** | The statement "It is not the case that Canberra is the capital city of Australia" is ___. |
| `P07` | — | declarative | negated | colloquial | direct | **NO** | It is not the case that the capital of Australia is Canberra — YES or NO? |
| `P08` | — | interrogative | negated | colloquial | reverse | **NO** | Is it false that Canberra is the capital of Australia? |

Every `(polarity × register × direction)` cell appears exactly once — 4 affirmative / 4 negated, 4 formal / 4 colloquial, 4 direct / 4 reverse. Syntax splits 3/3/2 because 8 is not divisible by 3 (ADR-0003).

### Evidence (1/1 pass)

- **[PASS]** `Q408 P36` — Q408 P36 -> ['Q3114', 'Q3141']; expected to contain Q3114  
  <https://www.wikidata.org/wiki/Q408>, retrieved 2026-09-11

> **Note on multi-valued evidence.** The knowledge base returns more than one value for a check above; it passed because the expected value is among them. Wikidata records historical as well as current statements, so a constraint worded as "exactly one" can legitimately meet a KB statement that lists several. Whether the wording should be tightened is a question for human review.

**Known ambiguity:** Sydney and Melbourne are common distractors and are deliberately in the answer space. Melbourne was the seat of federal parliament 1901-1927, which is a genuine source of confusion and is the subject of C4.

---

## 2. `K-C3-SCI-01` — Quantified / rule-based — universal quantification with variable binding

| | |
|---|---|
| **Class** | C3 |
| **Domain** | science_technology |
| **Family** | F-SCI-01 (schema S-C3-01) |
| **Answer type** | boolean |
| **Ground truth** | **NO** |
| **Answer space** | YES, NO |
| **Status** | **DRAFT** — 2/2 machine checks pass; no human review |

**In plain English:** Universal: for every chemical element x, x has exactly one atomic number. No element has two distinct atomic numbers.

**Formal representation:** `forall x,m,n: atomic_number(x,m) AND atomic_number(x,n) -> m = n`  
**D0 predicate:** `c3_functional_uniqueness`

**Gold proposition:** Gold has exactly one atomic number, 79.

**Entities:** gold (`Q897`, 277 sitelinks)

### All 8 probes

| Probe | In 5-probe run | Syntax | Polarity | Register | Direction | Expects | Question |
|---|---|---|---|---|---|---|---|
| `P01` | yes | cloze | affirmative | formal | direct | **NO** | The statement "Gold has more than one atomic number" is ___. |
| `P02` | yes | declarative | affirmative | formal | reverse | **NO** | More than one atomic number belongs to gold — YES or NO? |
| `P03` | yes | interrogative | affirmative | colloquial | direct | **NO** | Is the following statement true? Gold comes with more than one atomic number |
| `P04` | yes | cloze | affirmative | colloquial | reverse | **NO** | The statement "More than one atomic number is what gold has" is ___. |
| `P05` | yes | declarative | negated | formal | direct | **YES** | It is not the case that gold has more than one atomic number — YES or NO? |
| `P06` | — | interrogative | negated | formal | reverse | **YES** | Is the following statement false? More than one atomic number belongs to gold |
| `P07` | — | cloze | negated | colloquial | direct | **YES** | The statement "It is not the case that gold comes with more than one atomic number" is ___. |
| `P08` | — | declarative | negated | colloquial | reverse | **YES** | It is not the case that more than one atomic number is what gold has — YES or NO? |

Every `(polarity × register × direction)` cell appears exactly once — 4 affirmative / 4 negated, 4 formal / 4 colloquial, 4 direct / 4 reverse. Syntax splits 3/3/2 because 8 is not divisible by 3 (ADR-0003).

### Evidence (2/2 pass)

- **[PASS]** `Q897 P1086` — Q897 P1086 -> ['79']; expected '79'  
  <https://www.wikidata.org/wiki/Q897>, retrieved 2026-09-11
- **[PASS]** `Q897 P1086` — Q897 P1086 has 1 statement(s); expected 1  
  <https://www.wikidata.org/wiki/Q897>, retrieved 2026-09-11

**Known ambiguity:** Expected answer NO. Isotopes vary in MASS number, not atomic number; a model conflating the two is a genuine and interesting failure mode. Class assignment (C3 vs C1) requires human review.

---

## 3. `K-C4-POL-01` — Temporal — reasoning over validity intervals or ordering

| | |
|---|---|
| **Class** | C4 |
| **Domain** | public_office |
| **Family** | F-POL-01 (schema S-C4-01) |
| **Answer type** | date |
| **Ground truth** | **1789** |
| **Answer space** | 1789, 1776, 1787 |
| **Status** | **DRAFT** — 2/2 machine checks pass; no human review |

**In plain English:** Temporal ordering: the first holder of the office of President of the United States took office in 1789; no person held it before that year.

**Formal representation:** `forall x,t: holds(x, POTUS, t) -> t >= inception(POTUS)`  
**D0 predicate:** `c4_interval_precedence`

**Gold proposition:** The office of President of the United States was established in 1789; George Washington took office in that year.

**Entities:** President of the United States (`Q11696`, 143 sitelinks), George Washington (`Q23`, 274 sitelinks)

### All 8 probes

| Probe | In 5-probe run | Syntax | Polarity | Register | Direction | Expects | Question |
|---|---|---|---|---|---|---|---|
| `P01` | yes | interrogative | affirmative | formal | direct | **1789** | What is the year of the first holder of the office of President of the United States taking office? |
| `P02` | yes | cloze | affirmative | formal | reverse | **YES** | The statement "1789 is the year of the first holder of the office of President of the United States taking office" is ___. |
| `P03` | yes | declarative | affirmative | colloquial | direct | **1789** | The year of the first US president taking office is |
| `P04` | yes | interrogative | affirmative | colloquial | reverse | **YES** | Is 1789 the year of the first US president taking office? |
| `P05` | yes | cloze | negated | formal | direct | **NO** | The statement "It is not the case that the year of the first holder of the office of President of the United States taking office is 1789" is ___. |
| `P06` | — | declarative | negated | formal | reverse | **NO** | It is not the case that 1789 is the year of the first holder of the office of President of the United States taking office — YES or NO? |
| `P07` | — | interrogative | negated | colloquial | direct | **NO** | Is it false that the year of the first US president taking office is 1789? |
| `P08` | — | cloze | negated | colloquial | reverse | **NO** | The statement "It is not the case that 1789 is the year of the first US president taking office" is ___. |

Every `(polarity × register × direction)` cell appears exactly once — 4 affirmative / 4 negated, 4 formal / 4 colloquial, 4 direct / 4 reverse. Syntax splits 3/3/2 because 8 is not divisible by 3 (ADR-0003).

### Evidence (2/2 pass)

- **[PASS]** `Q23 P39 Q11696` — Q23 P39=Q11696 start year(s) [1789]; expected at least one <= 1789  
  <https://www.wikidata.org/wiki/Q23>, retrieved 2026-09-11
- **[PASS]** ⚠ **DISCREPANCY** `Q11696 P571` — Q11696 P571 -> year(s) [1787]; expected 1787  
  <https://www.wikidata.org/wiki/Q11696>, retrieved 2026-09-11
  > DISCREPANCY RECORD: Wikidata gives office inception (P571) as 1787 (Constitution signed). The constraint concerns 1789, when the office was first held. Recorded, not hidden. Requires human adjudication.

**Known ambiguity:** 1776 (Declaration of Independence) and 1787 (Constitution signed) are in the answer space as genuine distractors that a model may conflate.

> **This constraint is blocked from EVIDENCE_VERIFIED** until the discrepancy is adjudicated by a human, even though every check passes. A check that confirms a discrepancy exists does not resolve it.

---

## What these examples are not

- **Not verified.** All twelve constraints are `DRAFT`. Machine evidence confirms specific Wikidata statements; it does not establish that a constraint is well-posed, unambiguously worded or correctly classified.
- **Not human-reviewed.** No person has checked any of this. The schema rejects `HUMAN_VALIDATED` without a named validator and date, so no script can claim it.
- **Not frozen.** The pilot split carries no freeze manifest.
- **Probe equivalence unvalidated.** §4.4.5 requires two blinded annotators per probe: 96 × 2 = 192 judgements, none performed.


## One open decision these examples make concrete

In example 1, probe `P01` expects `Canberra` while `P05`–`P08` expect `NO`. Whether those probe *the same question* — and so whether this constraint yields 28 comparable pairs or two separate sets of 4 — depends on `EQUIVALENCE_KEY_FIELDS` in `schemas/probe.py`, which currently excludes `polarity`. This is **Q21**, deliberately unresolved. Both polarities are generated and each probe records its own expected answer, so either decision works on exactly this data.

