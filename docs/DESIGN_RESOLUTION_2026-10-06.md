# Design resolution pass — 2026-10-06

> **DECIDED 2026-10-06.** Every item in "RESEARCHER DECISIONS REQUIRED" below has
> been answered: A1 and A2 approved, A3 approved as (b)+(c), A4 two date axes, A5
> accepted, A6 Variant A, A7 confirmed, A8 declined, A9 the observed 6/96 =
> 93.75% is canonical. The implementation batch is applied. This file is kept as
> the **evidence** behind those decisions; the live state is `HANDOFF.md`,
> `docs/RESULTS_STATUS.md` and `docs/BENCHMARK_ACCOUNTING.md`. Recommendations
> below read as recommendations because that is what they were at the time.

**Status (at the time of writing):** analysis complete, nothing adopted. No constraint authored, no
benchmark record created or modified, no ADR status changed, no GPU job
submitted, no pilot output touched, nothing committed.

Supersedes nothing. Builds on `docs/DECISION_MEMO_2026-10-06.md` and corrects two
figures in it (§6 below).

---

## 1. ADR-0002 — the design lattice

### Requirement

**§4.3:** *"Size. 120 constraints: 30 per class, balanced across 5 domains
(geography, history, biology, public office, science & technology), giving 6
constraints per domain per class."* · *"Constraints are authored in **families**
that hold nuisance variation approximately constant across classes."* ·
*"**Six to eight** constraint schemas are hand-authored per class and each is
instantiated with **four to five** distinct entity sets ... instance counts are
balanced so that no schema dominates a class."*

**Appendix A.1:** *"Increased to 30 per class, 120 total."*

**§4.11:** confirmatory contrast is *"C1+C2 versus C3+C4 (60 constraints per
arm)"*; *"the collapsed contrast carries the confirmatory claim, which is what
makes 120 constraints statistically adequate."*

### Current implementation

`configs/benchmark/design.yaml` resolves the lattice to 30 families × 4 classes,
6 families per domain, 6 schemas per class × 5 instances, with schema × domain
attempted fully crossed. `src/semintegrity/benchmark/design_validator.py`
enforces nine rules against it. The implementation is complete and tested; what
is missing is the researcher's approval of ADR-0002 itself.

### Alternatives

| | schemas × instances per class | §4.3 compliance |
|---|---|---|
| **L1** | 6 × 5 (uniform) | within 6–8 × 4–5; uniform, so "no schema dominates" holds trivially |
| **L2** | 7 schemas: five at 4 instances, two at 5 | within 6–8 × 4–5 arithmetically, but instance counts are unequal |
| **L3** | 8 × 4 = 32, then drop 2 | breaks 30-per-class, so breaks §4.11's 60/60 |

L3 is excluded by §4.11. L2 is arithmetically admissible — 4(5) + 5(2) = 30 —
but puts two schemas at 25% more instances than the other five, which is what
*"instance counts are balanced so that no schema dominates a class"* exists to
prevent. **L1 is the only uniform solution**, since 7×4=28, 7×5=35, 8×4=32 and
8×5=40 all miss 30.

A second, independent choice hides inside L1 and is worth stating because it is
forced rather than preferred. With 6 families per domain, 6 schemas per class,
one constraint per class per family, and at most one constraint per (schema,
domain) cell, **family necessarily coincides with (domain, schema index)**. The
30 families *are* the 30 (domain, schema) cells. That is why the coverage matrix
is organised around six "axes": an axis is simultaneously a schema in each class
and a family theme in each domain. There is no freedom here to exercise.

### Recommendation

**Approve L1 as written.** It is the unique uniform reading of §4.3, it preserves
§4.11's 60/60 exactly, and the validator already enforces it.

### Consequences

* **Authoring:** fixes all 120 `constraint_id`s, 30 `family_id`s and 24
  `schema_id`s. This is the decision that is expensive to reverse — rejection
  after authoring re-keys every record and re-runs Wikidata evidence against new
  ids.
* **Probe generation:** none directly; ADR-0003 governs probes.
* **Detectors:** `schema_id` is the unit of D0's three-instance schema audit
  (§4.8.2), so the schema count sets the audit workload at 24.
* **Statistics:** `(1 | schema/constraint)` in §4.11's model has 24 schema
  levels with 5 observations each — thin but balanced, which is the best
  available under §4.3's counts.
* **Human annotation:** none directly.

---

## 2. ADR-0003 — probe factor balancing at K = 8

### Requirement

**§4.4.2:** *"K = 8 probes per constraint, 960 probes in total, C(8,2) = 28 pairs
per constraint."* · *"Probe transformation factors are **balanced exactly across
classes** and recorded on every probe, so that a class effect cannot be an
artefact of, for example, more negated phrasings appearing at C4"* — syntax
(declarative / interrogative / cloze), polarity (affirmative / negated),
register (formal / colloquial), directionality (direct / reverse); distractor
context excluded to a secondary experiment.

**§4.4.1:** *"Every probe is mapped to a formal representation, and two probes
are equivalent **if and only if** their representations are identical:
`constraint_id, probe_id, logical_form, subject, predicate, object, time_scope,
quantifier, polarity, answer_type`."*

### Current implementation

`src/semintegrity/probes/factor_design.py` gives each constraint all 8
(polarity × register × directionality) cells once and rotates syntax as
`SYNTAX[(cell_index + constraint_index) % 3]`, yielding exactly 10 observations
per factor cell per class and 40 across the benchmark;
`tests/unit/test_probe_balance.py` verifies it.
`src/semintegrity/probes/surface.py` realises each cell as text.

### Alternatives

24 factor cells cannot be crossed inside 8 probes, so some fractional design is
mandatory. The real alternatives are where the imbalance is absorbed:

* **P1 (as written):** polarity × register × directionality complete within each
  constraint; syntax rotates across constraints. Exact at class level, 3/3/2
  within a constraint.
* **P2:** syntax complete within each constraint (3 levels, so 8 probes split
  3/3/2 regardless) and rotate one of the binary factors instead. Moves the
  within-constraint imbalance onto polarity or directionality — worse, because
  §4.4.2's named worry is *"more negated phrasings appearing at C4"*, i.e.
  polarity imbalance specifically.
* **P3:** K = 12 (= 2×2×3) to make syntax complete within a constraint.
  Contradicts §4.4.2's K = 8 and its 960-probe total, and raises authoring and
  annotation volume by 50%.

### Recommendation

**Approve P1 as written.** It puts the unavoidable 3/3/2 on the factor §4.4.2
does *not* single out, and it is exactly balanced at the level the confirmatory
claim is made.

### Consequences

* **Authoring:** sets the 8 surface slots each constraint's author must supply
  (`subject`/`relation`/`object`/`claim` in formal and colloquial register, plus
  `claim_reverse_*` for author-written claims). This is the concrete authoring
  contract.
* **Probe generation:** 960 primary probes are fully determined by the
  constraints plus this design. One engineering item becomes load-bearing:
  `constraint_index` is documented in `factor_design.py` as *"the constraint's
  0-based position **within its class**"*, and `pilot_builder.py` assigns it as a
  running counter in **source-file order**. The order of families in the
  authoring file therefore determines probe syntax, and the docstring says it
  *"must be stable once the benchmark is frozen"*. The canonical ordering must be
  pinned explicitly rather than inherited.
* **Detectors:** directionality deliberately mixes answer types within a
  constraint (§4.7), which is what Stage 0 reconciles; the Q21 polarity mapping
  depends on `polarity` being recorded per probe, which this design guarantees.
* **Statistics:** supplies the `probe_polarity + probe_syntax + probe_direction`
  terms in §4.11's model, balanced by construction.
* **Human annotation:** §4.4.5 requires two annotators on the primary tier, so
  rejecting P1 *after* probe validation discards annotation effort. Before
  validation, rejection is cheap: probes regenerate from templates.

---

## 3. Answer-type allocation

### Requirement

**§4.3:** *"Matched nuisance factors, not matched semantics. Constraints are
authored in families that hold nuisance variation **approximately constant**
across classes — same domain, comparable entity familiarity, **comparable answer
type**, comparable lexical complexity — while the structural requirement
changes."*

`answer_type` is **not** among §4.3's 17 per-constraint fields. It appears in
§4.4.1 as a **probe** field. §4.7 positively expects it to vary within a
constraint: *"the directionality probe factor mixes 'Is A the X of B?' (yes/no)
with 'What is the X of B?' (an entity)"*. §4.4.2's *"balanced exactly across
classes"* applies to the four probe transformation factors, which do not include
answer type.

So: §4.3 asks for comparability within a family. It does not require answer type
to be crossed with class, and "approximately constant" is softer than the
"forbids" I used earlier.

### Current implementation

Constraint-level `answer_type` is marked `DERIVED` in
`src/semintegrity/schemas/constraint.py` — *"the canonical answer type; Stage 0
maps every probe into it"* — and is required because §4.7 needs a closed answer
space. In the 12 pilot constraints it is a perfect function of class:

| class | answer type | answer space | size *m* |
|---|---|---|---|
| C1 | `entity` | e.g. `[Canberra, Sydney, Melbourne]` | 3 |
| C2 | `boolean` | `[YES, NO]` | 2 |
| C3 | `boolean` | `[YES, NO]` | 2 |
| C4 | `date` | e.g. `[1927, 1901, 1913]` | 3 |

At probe level the picture is already mixed in every class: in
`K-C1-GEO-01` the 8 probes are 4 `reverse/boolean`, 2 `direct/boolean`,
2 `direct/entity` — **only 2 of 8 probes elicit the canonical type**.

### A structural fact that simplifies the question

In the matrix's lattice every axis contributes exactly one constraint to every
(class, domain) cell. Therefore **any answer-type assignment that is a function
of the axis is automatically identical across all four classes.** Options (b)
and (c) are not two designs; they are the same design, and (c) adds a covariate
on top. The genuine choice is binary: answer type as a function of **class**, or
as a function of **axis**.

### Concrete comparison

Chance agreement between two independent draws from a closed space of size *m*
is 1/*m*, so the chance "contradiction" rate is 1 − 1/*m*: **0.667 at m = 3,
0.500 at m = 2**. A 2-option class therefore looks *more self-consistent* than a
3-option class before any model behaviour is involved.

**(a) Pilot pairing — answer type ← class**

| contrast | chance-PSCR | artefact |
|---|---|---|
| Confirmatory C1+C2 vs C3+C4 | 0.583 vs 0.583 | **none — exactly balanced** |
| Planned C4 vs C1–C3 pooled | 0.667 vs 0.556 | **0.111** |
| Descriptive four-class profile | 0.667 / 0.500 / 0.500 / 0.667 | **spread 0.167** |

The confirmatory claim is safe because each arm holds one 3-option and one
2-option class. The descriptive profile — which §4.11 presents as descriptive and
H1 makes a per-class claim about — is not.

**(b) Axis-fixed — answer type ← axis** (the matrix as generated: 3 entity,
2 boolean, 1 date axis → 15 / 10 / 5 per class)

Chance-PSCR is **0.611 for every class**, so every contrast is free of this
artefact. It depends only on how many axes are boolean, not on how entity and
date are split: 2 boolean axes → 0.611 for all classes; 1 boolean axis → 0.639
for all classes.

**(c) Family-constant plus cardinality covariate**

Structurally identical to (b) in class-level balance, for the reason above. The
covariate adds protection to §4.11's beta-binomial model. It does **not** help
the confirmatory procedure: §4.11 states *"A bootstrap on a difference in means
cannot deliver covariate adjustment"*, and the cluster bootstrap carries the
confirmatory claim. So (c) is a cheap addition to (b), not an alternative to it.

### The cost of (b), which must be weighed

`c4_interval_precedence` is the one D0 predicate that decides something mutual
exclusion cannot: a **single** response violating a temporal anchor
(`constraint.temporal_validity.start`). It requires a parseable **date** answer,
and returns `NOT_APPLICABLE` otherwise.

| | C4 constraints with a date answer | D0 structural coverage on C4 |
|---|---|---|
| (a) pilot pairing | 30 / 30 | **30 / 30** |
| (b) 1 date axis | 5 / 30 | **5 / 30** |
| (b) 2 date axes | 10 / 30 | 10 / 30 |
| (b) 3 date axes | 15 / 30 | 15 / 30 |

This is a genuine trade: class-level answer-type balance forces C4 to hold no
more date constraints than C1, so raising D0's C4 coverage means pushing
temporal content into C1/C2/C3. The number of date axes is a sub-decision with
no free optimum.

### Recommendation

**(b) with two date axes, plus (c)'s covariate.** Rationale: it removes the
artefact from the descriptive profile and the planned contrast, which is where
H1's per-class claim lives; it holds D0's structural C4 coverage at 10/30 rather
than 5/30; and the covariate costs one term in a model that is already fitted.
Against it: two of six axes carry temporal content into C1–C3, and some
renderings are harder to author.

**If you prefer (a):** it is defensible, and should then be recorded in §4.14's
limitations with the exact numbers above — confirmatory contrast unaffected,
descriptive profile carrying up to 0.167 of answer-space artefact. What is not
defensible is leaving it unstated.

### Consequences

* **Authoring:** under (b) each axis must render in one answer type across all
  four classes — a `date`-typed C1 and a `boolean`-typed C4 are the awkward
  cells. Under (a) each class has one natural type throughout.
* **Probe generation:** unchanged either way; directionality already mixes probe
  answer types.
* **Detectors:** quantified above. Also, D1 (exact match) and D4 (distributional)
  both read `answer_space`, so cardinality balance changes their baselines too.
* **Statistics:** (b) removes the artefact; (a) leaves it in the descriptive
  profile; (c) adds `log(m)` or `m` as a covariate to the secondary model only.
* **Human annotation:** unchanged in volume. Annotators judge probe equivalence,
  not answer type.
* **ADR-0007:** under (b), the 12 pilot constraints are no longer instances of
  the 24 test schemas (their answer types follow class, not axis), so
  ADR-0007's *"dev constraints reuse the **same schemas**"* cannot hold
  literally. See §6, conflict C4.

---

## 4. ADR-0007 — the development set

### Requirement

**§5.6:** *"The analysis plan is preregistered on OSF before any test-set
collection, with a frozen development/test split so that NLI thresholds, judge
prompts and extraction rules are tuned only on development data."* No size, no
provenance, no statement about the pilot constraints.

**§4.12:** Phase 1 *"author 12 pilot constraints (3 per class)"*; Phase 5
*"Author the 120-constraint benchmark"*.

### Current implementation

`configs/benchmark/design.yaml` carries `splits.status: DECIDED` with dev at 24
(6 per class), the 12 pilot absorbed, 12 further authored, and a disjointness
rule enforced by `design_validator.validate_split_disjointness`. The 12 pilot
records carry `split: "pilot"`, and `Split.PILOT` is documented as *"absorbed
into DEV afterwards"*.

### Alternatives

Q1 recorded three. (b) split the 120 into 96 test / 24 dev — rejected because it
drops the arms to ~48 and reopens the n=15 argument. (c) tune on the 12 pilot
constraints only — rejected because per-class D2 threshold calibration on 3
constraints per class is not workable. (a), adopted: a separate disjoint 24.

### Recommendation

**No reopening needed — it is approved and it is the right call.** One
observation strengthens it independently: §5.6 restricts tuning to development
data, and the canonicaliser's Q21 polarity mapping was *derived from pilot
output* (`docs/Q21_polarity_mapping_spec.md` §7 recomputes the 96 responses and
sets the mapping from them). The pilot constraints are already tuning data, so
placing them in the test set would retrospectively breach §5.6. The alternative
is closed by events, not only by preference.

### Consequences

Quantified in §6.

---

## 5. D0 predicate scope — the minimum actually required

### Requirement

**§4.8.2** makes D0 *"deterministic CONDITIONAL verification, not oracular
judgement"*, conditional on correct formalisation, canonicalisation and
knowledge base. `configs/detectors/d0_symbolic.yaml` records the error model as
`systematic_and_schema_correlated` — *"a faulty predicate is confidently wrong
across every instance of its schema"* — and requires a three-instance schema
audit before predicate freeze. **§4.8.1** makes D0 coverage *"a RESULT in its own
right, not a diagnostic"*.

### What the existing predicates actually do

* `c1_mutual_exclusion` — documented as *"schema-general"* and *"infrastructure,
  not content — it carries no facts of its own and applies to any C1 schema whose
  answer space is mutually exclusive"*. Over a closed space: contradiction iff
  the canonical answers differ. Uses no KB.
* `c4_interval_precedence` — parses both canonical answers as dates, compares each
  against `temporal_validity.start`, and returns `VIOLATION` if **either**
  precedes the anchor, *even when the two responses agree*. This is the only
  predicate that decides something mutual exclusion cannot.
* `generic_closed_space` — `c2_conjunction` and `c3_functional_uniqueness`,
  both `version = "0.1-placeholder"`, both delegating to `C1MutualExclusion` and
  both declaring in `formal_statement` exactly what they do not formalise.

### The finding

**The minimum predicate scope is one behaviour, and it already exists.** Over a
closed, mutually exclusive answer space — which §4.7 requires of every constraint
— pairwise contradiction *is* "the canonical answers differ". That covers all 24
schemas with no new logic.

Exactly one schema-specific behaviour adds decidable structure: the temporal
anchor check, which also already exists.

And two do **not** add decidable structure, for a reason that is a design fact
rather than a missing implementation:

* **C2 conjunctive.** The probe asks the conjunction as a whole and the model
  returns one token. A model that answered YES on the strength of one conjunct is
  *indistinguishable in the response* from one that checked both. Conjunct-level
  information exists only in `prerequisite_atomic_facts`, which the knowledge
  screen asks separately — and §4.11 makes that *"a reporting view, never an
  inclusion criterion"*. Using it inside D0 would change D0's role, which is a
  methodology decision, not an implementation task.
* **C3 quantified.** Same shape: the probe asks the instantiated claim, so the
  response carries nothing about the quantifier or its variable binding.

So "implement 12 missing predicates" — the figure in the earlier memo — was the
wrong framing. **Nine of the twelve cannot be made genuine without changing what
the probes ask.**

### Mapping of all 24 proposed schemas

`EXCL` = closed-space mutual exclusion (exists, schema-general).
`ANCHOR` = temporal anchor precedence (exists, needs a date answer and
`temporal_validity.start`).
`N/A-struct` = the class's structure is not decidable from a Track A response.

| axis | C1 | C2 | C3 | C4 |
|---|---|---|---|---|
| 1 Unique role-bearer | `EXCL` | `EXCL` + N/A-struct | `EXCL` + N/A-struct | `EXCL` |
| 2 Disjoint category | `EXCL` | `EXCL` + N/A-struct | `EXCL` + N/A-struct | `EXCL` |
| 3 Part–whole containment | `EXCL` | `EXCL` + N/A-struct | `EXCL` + N/A-struct | `EXCL` |
| 4 Event precedence | `EXCL` | `EXCL` + N/A-struct | `EXCL` + N/A-struct | `EXCL` |
| 5 Extremal uniqueness | `EXCL` | `EXCL` + N/A-struct | `EXCL` + N/A-struct | `EXCL` |
| 6 Interval boundary (`date`) | `EXCL`+`ANCHOR` | `EXCL`+`ANCHOR` + N/A-struct | `EXCL`+`ANCHOR` + N/A-struct | `EXCL`+`ANCHOR` |

Totals: **24 / 24 covered by `EXCL`** · **4 / 24 additionally by `ANCHOR`** (6
axes × 1 date axis; 8/24 if two date axes are chosen in §3) · **12 / 24 carry a
class structure that is not decidable from a single canonical answer** —
all C2 and all C3 schemas.

### Recommendation

**Register one thin predicate subclass per schema, delegating to the two
behaviours above, with an honest `formal_statement` on each** — the pattern
`generic_closed_space.py` already uses. This gives:

* `predicate_registered` passes with **no new detection logic**;
* each schema gets its own `schema_id`, `version` and freeze hash, so §4.8.2's
  three-instance audit is per-schema as required;
* every C2/C3 `formal_statement` says in words that the quantifier or the
  conjuncts are not formalised, and that statement is copied into the freeze
  manifest and every audit record;
* D0 coverage is reported as what it is, satisfying §4.8.1 without overclaiming.

Do **not** write 12 new detection algorithms. Nine of them would be placeholders
with ambitious names, which is precisely the failure mode
`d0_symbolic.yaml` names: a confidently wrong predicate applied across every
instance of its schema.

### Consequences

* **Authoring:** each constraint's `formal_predicate` must name its schema's
  predicate; a per-schema naming convention (e.g. `s_c2_03_excl`) needs pinning.
* **Detectors:** 24 audit records instead of 4; no new detection logic; D0
  coverage per class becomes reportable without caveat inflation.
* **Statistics:** D0 vs D1 disagreement stays a reportable result (§4.8.2) and is
  now interpretable, since D0's formal statement bounds what it claims.
* **Human annotation:** unaffected — but note that D0's *measured error rate* on
  the test split (§4.8.2) is only meaningful against human gold, so this scope
  decision does not escape the human-validation blocker.

---

## 6. Benchmark accounting, reconciled

### Constraints

| | count | state |
|---|---|---|
| Existing pilot constraints (→ dev per ADR-0007) | **12** | authored, DRAFT, 2 runs complete |
| New test constraints (the 120) | **120** | not authored |
| New dev constraints to reach ADR-0007's 24 | **12** | not authored |
| **Total authored at freeze** | **144** | = 120 test + 24 dev |
| **New authoring required** | **132** | 120 + 12 |

### Probes

| tier | basis | probes | new? |
|---|---|---|---|
| Primary Track A, test | 120 × 8 | **960** | all new |
| Primary Track A, dev | 24 × 8 = 192 | **96 new** | 96 exist (the pilot run) |
| Saturation | 24 of the 120 at K = 50 | **1,008 additional** | all new (§4.4.4) |
| Track B | 20-constraint subset, free-form | 160 | same probes, different instruction |
| Knowledge screen | ~2.5 prerequisite facts × 120 | ~300 | derived from constraint records |
| **Primary-tier probe authoring** | | **1,056** | 960 test + 96 dev |

§4.4.2's *"960 probes in total"* refers to the primary test tier and matches
`configs/inference/primary.yaml` (`probes: 960`). Q18's itemisation of ~21,750
generations across 7 models is consistent.

### Corrections to the earlier memo

* It gave **1,152** new probes. That double-counted the 96 pilot probes already
  generated; the correct figure is **1,056**.
* It said **20 of 24** and then **12 of 24** D0 predicates need implementing.
  Per §5 above the correct statement is: 0 need new detection logic, 24 need thin
  per-schema registration, and 12 carry structure that is not decidable from a
  Track A response at all.

### Conflicts found, not resolved

**C1 — the CANON number differs between two repo documents.**
`docs/Q21_polarity_mapping_spec.md` §7 reports **5** remaining INVALID and
**94.8%**. `docs/RESULTS_STATUS.md`, `HANDOFF.md` and the audit script report
**6** and **93.75%**. Both are correct for different rules: the §7 figure is the
*simulation*, which allowed entity/date fall-through; production v1.1 is strict,
which discards `K-C1-GEO-01-P06` as well. The Q21 spec does not label its figure
as conditional on an unadopted rule. One of the two should be annotated.

**C2 — "rewording touches ADR-0003's lattice" is an overstatement.**
`HANDOFF.md` decision 1 and the Q21 spec §5(b) both say rewording the cloze
probes touches the factor lattice. §4.4.1 defines probe equivalence on the
*formal representation*, and surface text is not part of it. Measured: under both
replacement variants in §7, **0 of 96 probes change any formal field**. Rewording
changes the surface realisation of the `cloze` syntax level, not the lattice. The
real concern is construct validity of the syntax factor, which is a different and
smaller claim.

**C3 — cross-split id collision is unguarded.** `design_validator.validate()`
filters to one split before checking `unique_ids`, and the id grammar carries no
split field, so a test constraint and a pilot/dev constraint may share an id with
no check firing. Demonstrated: naive 01..06 test numbering collides on all 12
existing ids.

**C4 — ADR-0007's "same schemas" clause versus answer-type option (b).**
ADR-0007 requires dev constraints to *"reuse the **same schemas** but
**different entity instantiations**"*. The 12 pilot constraints instantiate
`S-Cx-01` under class-tied answer types. If §3 option (b) is adopted, they are
no longer instances of the test schemas, and the clause needs either re-wording
or 12 re-authored dev constraints that do match. This conflict exists only under
(b).

**C5 — `_unique_ids` docstring over-promises.** It is documented as checking that
*"constraint/family/schema ids are well-formed and unique"*; it checks
`constraint_id` duplicates only.

**C6 — ADR-0002 is PROPOSED while artefacts depend on it.**
`configs/benchmark/design.yaml` cites it as the basis, `design_validator.py`
enforces it and `scripts/audit_benchmark_readiness.py` asserts the 120 design.
Nothing is wrong, but the dependency graph points at an unapproved decision.

---

## 7. CANON — the six polar-cloze INVALIDs, resolved offline

**No GPU job was submitted and no inference was run.**

### What the six are

Raw pilot outputs are gitignored (`results/raw/**/*.jsonl`), so the responses are
cluster-only; the six strings are taken from `docs/Q21_polarity_mapping_spec.md`
and the session checkpoint. `data/benchmark/pilot/probes.jsonl` is in the repo, so
the probes themselves are fully inspectable.

All six are the **polar-cloze** form `"<assertion>: ___"` — a cloze probe whose
expected answer is YES or NO. There are **28** such probes among the 96, so the
observed failure rate on this form is **6 / 28 = 21.4%**.

| probe | ctype | expected | observed reply |
|---|---|---|---|
| `K-C2-SCI-01-P01` | boolean | YES | `Au` |
| `K-C2-SCI-01-P04` | boolean | YES | `Au` |
| `K-C2-GEO-01-P03` | boolean | YES | `Canberra` |
| `K-C2-GEO-01-P06` | boolean | NO | `CANBERRA` |
| `K-C1-GEO-01-P06` | entity | NO | `Melbourne` |
| `K-C4-SCI-01-P04` | date | YES | `Albert Einstein` |

### Diagnosis, sharpened

The four echo cases do not echo the token *adjacent* to the blank — in
`"...and its atomic number is 79: ___"` the reply is `Au`, not `79`. They echo
the **subject of the assertion**. The colon-plus-blank construction reads as a
`label: value` gloss, so the model supplies what the sentence is *about*.

The template confirms this is a missing cue rather than a model failure.
`surface.py` realises the three polar syntax levels as:

```
declarative    "<stem> — YES or NO?"      <- carries an explicit cue
interrogative  "Is <stem>?"               <- interrogative syntax cues a yes/no
cloze          "<stem>: ___"              <- no cue at all
```

And the Track A instruction (`configs/inference/prompts.yaml`, `trackA.v1`,
status DRAFT) is *conditional on the model inferring the type*: *"If the expected
answer is a name, reply with the name only. If the expected answer is yes or no,
reply with exactly YES or NO."* The polar cloze makes that inference fail, so the
model takes the name branch.

**§4.4.5 provides for exactly this remedy.** Its five-step validation protocol
is: generate candidates → automated filter → human validation of semantic
equivalence → *"**Rewrite or discard failures; record the discard rate**"* →
freeze. Rewriting a probe that fails validation is the designed process, not a
deviation from it. The rewrite rate must be recorded.

### Can it be fixed offline? Yes — in two template lines

Both failing frames are one line each:
`surface._frame_author_claim` and `surface._frame_assembled`, cloze branch,
currently `f"{stem}: ___"`. Because the surface is generated, fixing the six
means regenerating all **28** polar-cloze probes — they cannot be fixed
individually.

### Exact replacement wording

**Variant A (recommended): truth-value cloze.** `f'The statement "{stem}" is ___.'`

| probe | replacement text | expected |
|---|---|---|
| `K-C2-SCI-01-P01` | `The statement "The chemical symbol for gold is Au and its atomic number is 79" is ___.` | YES |
| `K-C2-SCI-01-P04` | `The statement "Au is gold's symbol, and 79 is its atomic number" is ___.` | YES |
| `K-C2-GEO-01-P03` | `The statement "Canberra is Australia's capital and it sits in the ACT" is ___.` | YES |
| `K-C2-GEO-01-P06` | `The statement "It is not the case that the capital of Australia is Canberra, and the Australian Capital Territory is where it is located" is ___.` | NO |
| `K-C1-GEO-01-P06` | `The statement "It is not the case that Canberra is the capital city of Australia" is ___.` | NO |
| `K-C4-SCI-01-P04` | `The statement "1901 is the year of the Nobel Prize in Physics first being given out" is ___.` | YES |

**Variant B (conservative alternative): cued option suffix.**
`f"{stem} — true or false: ___"`, e.g.
`Canberra is Australia's capital and it sits in the ACT — true or false: ___`.

### Why each replacement should canonicalise

1. **The blank now sits in a slot only a truth value can fill.** `"The statement
   '…' is ___."` takes a predicate adjective. `Canberra` is not grammatical
   there; `true` and `false` are. The label-gloss reading that produced the
   echoes is unavailable because the sentence already has an explicit subject
   (*the statement*).
2. **No canonicaliser change is needed.** `_YES_TOKENS` already contains
   `"true"` and `_NO_TOKENS` already contains `"false"`. The alias tables are
   untouched, so this does not spend any §5.6 dev-tuning budget on Stage 0.
3. **The polarity mapping still applies.** `is_polar(probe)` tests
   `expected_answer in ("YES","NO")`, which is unchanged, so the Q21 inversion
   logic continues to govern these probes.
4. **It does not weaken the syntax contrast.** Variant A does not enumerate the
   options, so it stays distinct from the declarative `"— YES or NO?"` form.
   Variant B enumerates and so converges on the declarative form — the reason it
   is second choice.

### Offline validation, executed

Regenerated all 96 pilot probes under each variant via
`pilot_builder.build(..., fetch_evidence=False)` and ran Stage 0 `classify` over
hypothetical replies. Results, identical for both variants:

```
[0] regenerated baseline matches data/benchmark/pilot/probes.jsonl: YES
[0] polar-cloze probes in the 96: 28  (observed INVALID: 6 = 21.4%)
[1] formal representation (§4.4.1) changed on: 0 / 96 probes
[2] probe_text changed on 28 probes; exactly the polar-cloze set: True
[3] duplicate probe texts within a constraint: 0
[4] cued replies canonicalised: 24/24      ('true','false','True.','FALSE')
    observed failures still INVALID: 6/6   ('Au','Canberra','CANBERRA','Melbourne','Albert Einstein')
```

`YES`/`NO` replies also still canonicalise correctly under the new wording, and
the negated probes still invert (`K-C2-GEO-01-P06`: reply `true` → `NO`, reply
`false` → `YES`).

**Residual risks, measured and reported rather than hidden:**
`"The statement is true"` → INVALID (leading token is `the`; `parse_yes_no` is
deliberately strict). `"accurate"` → INVALID (not in `_YES_TOKENS`). Both are
plausible replies to variant A. Neither is in the observed data, and widening the
token set would be a §5.6 dev-tuning change requiring its own decision.

### What this does NOT establish

Whether a model actually stops echoing the subject. That is an empirical claim
requiring inference, and nothing here substitutes for it. The arithmetic if it
holds: 6 INVALID → 1 (the genuine off-target `Albert Einstein` has no reason to
change), giving **95/96 = 99.0%**, past the ≥95% CANON gate. If only the four
echo cases resolve, 92/96 = **95.8%** — still past the gate.

**An inference path exists that is not the cluster GPU.** ADR-0014 covers local
MPS development and `results/raw/_smoke/local-mps.jsonl` records a prior local
smoke run. The 28 reworded probes could be run against a small local model on
this Mac to test the echo hypothesis before spending cluster time. That is
inference, so I have not run it — it needs your go-ahead, and it would be
evidence about a small local model, not about Qwen2.5-3B.

### Routes not recommended

* **Strengthen the Track A instruction instead.** The prompt is still
  `status: DRAFT` and tunable, so this is cheap. But stating the expected answer
  type would differentially help the cloze probes, which **confounds the syntax
  factor** §4.4.2 exists to control, and hands the model information the probe
  does not contain.
* **Drop polar cloze from the factor design.** ADR-0003 requires exact class-level
  balance; removing one syntax level for polar probes breaks it.
* **Accept it as measured surface sensitivity.** §4.12 fixes the ≥95%
  canonicalisation criterion in advance and states that *"Failure on any
  criterion triggers pipeline revision before the full benchmark is authored"*.
  Accepting a failing gate is not one of the options the proposal leaves open.

---

## 8. Revised coverage matrix

`docs/BENCHMARK_COVERAGE_MATRIX.md` has been regenerated as **Revision 2**
(`scripts/propose_coverage_matrix.py`). It remains PROPOSED and still authors
nothing. Changes from Revision 1, all driven by the analysis above:

1. **D0 column replaced.** Revision 1 named 24 schema-specific predicates, 12 of
   which do not exist. Revision 2 names the two real behaviours (`EXCL`,
   `ANCHOR`) per schema, marks all C2/C3 schemas `N/A-struct` with the reason,
   and reports the per-schema registration recommendation.
2. **Answer-space cardinality and chance-PSCR added**, per axis and per class, so
   §3's balance claim is checkable in the artefact rather than asserted.
3. **M2 corrected** to "approximately constant", and restated as an
   interpretation rather than a requirement.
4. **M4 replaced** with the minimum-scope finding.
5. The lattice dry-run, the id-collision check and the Q12 strain cells are
   unchanged and still pass.

The matrix still shows **one** date axis. If you choose two date axes per §3's
recommendation, the matrix needs one further revision — I have not pre-empted
that choice.

---

## RESEARCHER DECISIONS REQUIRED

### A. Decisions you must personally approve

**A1 — ADR-0002, the design lattice.** Approve / amend / reject. Recommended:
approve as written (L1, 6 schemas × 5 instances; it is the unique uniform reading
of §4.3). Most expensive decision to reverse after authoring.

**A2 — ADR-0003, probe factor balancing.** Approve / amend / reject. Recommended:
approve as written (P1). Cheap to reverse before human probe validation, costly
after.

**A3 — Answer-type allocation.** (a) class-tied / (b) axis-fixed / (c) (b) plus
cardinality covariate. Recommended: **(b) with two date axes, plus (c)'s
covariate**. Needs an ADR and an `OPEN_QUESTIONS.md` entry either way. If (a),
the §3 artefact numbers go into §4.14's limitations.

**A4 — Number of date axes**, conditional on A3 = (b)/(c). 1 / 2 / 3.
Recommended: 2. Trades D0's structural C4 coverage (5 / 10 / 15 of 30) against
temporal content bleeding into C1–C3.

**A5 — D0 predicate scope.** Recommended: per-schema thin registration over the
two existing behaviours, with honest `formal_statement`s, and **no new detection
logic**. The alternative — probing conjuncts or quantifier instances separately
so that genuine C2/C3 predicates become constructible — is a change to what the
probes ask, and would be a larger redesign.

**A6 — The polar-cloze rewrite.** Approve variant A / variant B / neither.
Recommended: **variant A**. Offline evidence is in §7; the model-behaviour claim
is unverified.

**A7 — ADR-0007 acknowledgement.** Not a reopening: confirm the quantified bill
(132 new constraints, 1,056 new primary probes, 144 authored at freeze) and the
§5.6 reading that the pilot 12 are already tuning data.

**A8 — Local MPS inference, yes or no.** Running the 28 reworded probes against a
small local model would test the echo hypothesis without cluster GPU time. It is
still inference, and the evidence would concern a local model rather than
Qwen2.5-3B.

**A9 — Conflict C1.** Which of the two CANON figures is canonical, and annotate
the other. Both are in the repo and both are correct under different rules.

### B. Engineering decisions I can take once A is settled

* **B1** Test id indices 11..16 (pilot/dev keeps 01..10) — already taken; §6 C3
  is the evidence.
* **B2** Pin the canonical family ordering that defines `constraint_index`, since
  source-file order currently determines probe syntax.
* **B3** Per-schema predicate naming convention and the 24 thin registrations
  (shape follows from A5).
* **B4** Fix `_unique_ids` and add the cross-split id uniqueness check (C5, C3).
* **B5** Apply the chosen cloze template to the two functions in `surface.py`,
  with a regression test that pins all 28 reworded texts.
* **B6** Annotate the Q21 spec and/or `RESULTS_STATUS.md` per A9's answer.
* **B7** Record the probe rewrite rate as §4.4.5 step 4 requires.

### C. Work that can proceed immediately, with no methodology decision

* **C1** PyMC beta-binomial model and the knowledge-screen analysis — the last two
  analysis gaps. Note Q4 is settled by ADR-0009 and Q8 by fact (R is absent on the
  cluster, so PyMC is the only backend).
* **C2** Human-annotation infrastructure, built and not run: Sample A/B
  construction, the blinded interface, Krippendorff α, the adjudication path.
  Unblocks D2's checkpoint and thresholds the moment labels exist.
* **C3** `_unique_ids` / cross-split id checks (B4 needs no methodology input).
* **C4** Sync the cluster, which is still 9 commits behind, and re-verify there.
* **C5** Storage staging plan for the 244 GB / 286 GB shared-headroom FAIL —
  models staged one at a time and evicted.
