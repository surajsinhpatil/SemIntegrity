# Decision memo — three design issues raised by the coverage matrix

**Date:** 2026-10-06 · **Status:** superseded by
`docs/DESIGN_RESOLUTION_2026-10-06.md` and the decisions taken that day. Kept as
the record of the three issues as first raised.

> **Two figures in this memo were later corrected.** It gives **1,152** new
> probes, which double-counted the 96 pilot probes already generated — the
> correct figure is **1,056** (`docs/BENCHMARK_ACCOUNTING.md`). And it says 12 of
> 24 D0 predicates need implementing; the correct statement is that **none** need
> new detection logic, 24 need thin per-schema registration, and 12 carry
> structure that is not decidable from a Track A response at all
> (`docs/decisions/ADR-0017-answer-type-allocation.md` and
> `src/semintegrity/detectors/d0/predicates/schema_registrations.py`).
**Scope:** no constraints authored, no benchmark record modified, no ADR status
changed, nothing committed.

Sources: `proposal/semintegrity_proposal.docx` (authoritative), the ADRs under
`docs/decisions/`, `docs/OPEN_QUESTIONS.md`, and the code and data as they stand
at `09e15ac`.

A note on one of my own earlier claims, because it affects how issue #3 should be
read: I wrote that "§4.3 requires comparable answer type across classes, and the
pilot's confounding must not be carried forward." §4.3's actual wording is
*"approximately constant"* and *"comparable"*, not identical, and the proposal
nowhere states that answer type must be crossed with class. The requirement is
real but weaker than I represented it. Details in issue #3.

---

## Issue #1 — is the target 120 total, or 120 test plus 12 dev?

### A. What the proposal says

**Appendix A.1** (resolved design questions), answering *"Is 15 constraints per
level sufficient for statistical claims?"*:

> "No. Increased to 30 per class, **120 total**. At n = 15 the 95% intervals
> around 0.90 and 0.60 overlap, so the values the original H1 predicts could not
> be separated. Adequacy at n = 30 depends on the collapsed confirmatory contrast
> (C1+C2 vs C3+C4, 60 per arm); the four-class profile is descriptive."

**§4.3 Benchmark construction**, first line:

> "Size. 120 constraints: 30 per class, balanced across 5 domains (geography,
> history, biology, public office, science & technology), giving 6 constraints
> per domain per class."

**§4.12 Execution plan** lists authoring in two separate phases:

| Phase | Work | Gate |
|---|---|---|
| 1 | "Formalise constraint representation; author 12 pilot constraints (3 per class)" | "Predicates execute; ground truth resolves" |
| 5 | "Author the 120-constraint benchmark; human probe validation" | "Benchmark frozen" |

and closes the pilot go/no-go list with:

> "Failure on any criterion triggers pipeline revision **before the full benchmark
> is authored**."

**§4.13 Compute and infrastructure** — the sentence quoted as "authoring is the
binding resource" is, verbatim:

> "Total generation load across 7 models is roughly 19,000 short generations (on
> the order of one million output tokens), which is small. **The binding resource
> for this project is authoring and annotation effort, not GPU time.**"

That is all §4.13 says about authoring. It is a statement about *what is scarce*,
not about how many constraints exist or how they are split. It contains no count.

**§5.6 Release** is the only place a split is required:

> "The analysis plan is preregistered on OSF before any test-set collection, with
> a frozen development/test split so that NLI thresholds, judge prompts and
> extraction rules are tuned only on development data."

§5.6 requires a dev/test split and never sizes it, never says whether dev comes
out of the 120, and never says where the 12 pilot constraints end up.

### B. Relevant ADR and status

**ADR-0007 — "A separate development set, disjoint from the 120"**, kind
METHODOLOGY, status **APPROVED BY RESEARCHER 2026-09-11 · resolves Q1**.

### C. What the proposal requires vs what the implementation assumes

**Answering your questions directly:**

* **Does the proposal define 120 constraints TOTAL?** Yes. Appendix A.1 says
  "120 total" and §4.3 says "120 constraints". That is the size of *the
  benchmark*.
* **Or 120 TEST constraints plus the 12 pilot/dev constraints?** The proposal
  does not say this. The words "test set" and "development set" appear only in
  §5.6, with no sizes. The proposal is **silent** on whether the 12 Phase-1 pilot
  constraints sit inside the 120 or beside it.
* **Is ADR-0007 consistent with the proposal, or a later design change?** It is a
  **later design decision that fills a genuine gap**, not a contradiction. It
  neither changes the 120 nor the 30-per-class nor the 60/60 arms — all three are
  preserved exactly as §4.3, §4.11 and Appendix A.1 state them. What it adds is
  a decision the proposal left undetermined: where development data comes from.
  Q1 recorded the gap as a `CONFLICT` precisely because §5.6 and §4.11 cannot
  both be satisfied if dev is carved out of the 120 (a 20% carve-out leaves ~48
  per arm, which reopens the n=15 argument Appendix A.1 used to reject 15 per
  class).
* **What exactly does ADR-0007 change?** Three things: (1) "The **120
  constraints are the test set**"; (2) a **separate development set of 24
  constraints (6 per class)** is authored, disjoint from the 120; (3) "the 12
  Phase-1 pilot constraints (3 per class) **are absorbed into it**", with 12
  further dev constraints authored to reach 24, reusing the same schemas with
  different entity instantiations.

**One further piece of evidence, which did not exist when ADR-0007 was approved
and now bears on it independently.** §5.6 restricts tuning to development data.
The canonicaliser's Q21 polarity mapping — v1.1, in production, the change that
moved the perfect-model PSCR artifact from 0.643 to 0.000 — was *designed from
pilot output*. `docs/OPEN_QUESTIONS.md` Q21 records the pilot responses probe by
probe and derives the mapping from them ("Empirical evidence from the first
cluster pilot (2026-09-25, job 11969)"), and ADR-0007 lists
`canonicaliser_alias_tuning` among dev's uses. So the 12 pilot constraints have
**already been used as tuning data**. Placing them in the test set would
retrospectively violate §5.6. This is not an argument for ADR-0007 so much as an
observation that the alternative is now closed.

### D. Concrete consequence for size and design

| | constraints to author | primary probes (K=8) |
|---|---|---|
| Test set (the 120) | **120 new** | 960 |
| Dev set (ADR-0007, 24 total) | **12 new** (12 pilot absorbed) | 192 |
| **Total new authoring** | **132** | 1152 |

The "108" figure was mine, from the option list I put to you earlier in this
session, and it is wrong under ADR-0007: it assumed the pilot 12 count toward
the 120. The benchmark is still **120 total**, exactly as the proposal says; the
*authoring* job is 120 new test constraints, because none of the existing 12 can
be one of them.

Secondary consequence, already demonstrated in §7 of the matrix: the id grammar
in `src/semintegrity/utils/ids.py` carries no split field, and
`design_validator.validate()` filters to one split before checking `unique_ids`.
A test set numbered 01..06 per (class, domain) would mint all 12 existing pilot
ids a second time, and no current check would fire.

### E. Engineering or methodology?

**Already decided methodology — not open.** ADR-0007 is APPROVED. The only thing
needed from you here is confirmation that you still hold that decision now that
the authoring bill it implies is visible (132 new constraints rather than 108),
and that you accept the §5.6 reading above. If you do, nothing further is
required: the matrix already assumes it.

The id index allocation (test at 11..16) is **engineering**, and I have taken it.

---

## Issue #2 — ADR-0002 and ADR-0003 are PROPOSED, and the matrix instantiates both

### A. What the proposal says

**§4.3**, on schemas:

> "Schema-based instantiation. **Six to eight constraint schemas** are
> hand-authored per class and each is instantiated with **four to five distinct
> entity sets**. The logic is authored by hand throughout; only the entities
> vary. Because instances of a schema are correlated by construction, schema
> enters the statistical model as a nested random effect (Section 4.11) and
> **instance counts are balanced so that no schema dominates a class**."

**§4.3**, on families:

> "Matched nuisance factors, not matched semantics. Constraints are authored in
> **families** that hold nuisance variation approximately constant across classes
> ... while the structural requirement changes."

**§4.4.2**, on probe factors:

> "Probe transformation factors are **balanced exactly across classes** and
> recorded on every probe, so that a class effect cannot be an artefact of, for
> example, more negated phrasings appearing at C4" — syntax (declarative /
> interrogative / cloze), polarity (affirmative / negated), register (formal /
> colloquial), directionality (direct / reverse); distractor context excluded as
> a secondary experiment.

**§4.4.2**, on K:

> "K = 8 probes per constraint, 960 probes in total, C(8,2) = 28 pairs per
> constraint."

### B. Relevant ADRs and status

* **ADR-0002 — The 120-constraint design lattice.** METHODOLOGY. **PROPOSED —
  AWAITING RESEARCHER APPROVAL**, dated 2026-09-11.
* **ADR-0003 — Probe factor balancing at K = 8.** METHODOLOGY. **PROPOSED —
  AWAITING RESEARCHER APPROVAL**, dated 2026-09-11.

### C. What each establishes, and what the proposal actually fixes

**ADR-0002 establishes:**

1. 30 families, each fixed to one domain, each contributing one constraint per
   class → 30 × 4 = 120.
2. 6 families per domain × 5 domains → 6 constraints per (domain, class) and 30
   per class.
3. 6 schemas per class × 5 instances = 30 per class.
4. Family is the nuisance-control blocking factor; schema is the nested random
   effect; domain is a balancing variable with no inferential claim.
5. Schema × domain is attempted fully crossed (6 × 5), relaxable to a balanced
   incomplete allocation per Q12.

How much of that is forced by the proposal rather than chosen? Items 1, 2 and 4
follow from §4.3's stated counts and roles. Item 3 is **nearly** forced: §4.3
allows 6–8 schemas at 4–5 instances each, and of those combinations only
**6 × 5 = 30** is uniform (7×4=28, 7×5=35, 8×4=32, 8×5=40). A 7-schema
allocation does reach 30 with unequal counts — five schemas at 4 instances plus
two at 5 — but that is a less balanced design than §4.3's "instance counts are
balanced so that no schema dominates a class" invites. So ADR-0002's item 3 is
the balanced reading, not the only arithmetically possible one.

What ADR-0002 adds beyond the proposal is item 5 and the identity that makes the
counts close: with 6 families per domain, 6 schemas per class, one constraint per
class per family and at most one constraint per (schema, domain) cell, **family
necessarily coincides with (domain, schema index)**. That identity is a
consequence, not a preference, and it is why the matrix is organised around six
axes.

**ADR-0003 establishes:** a fractional design exactly balanced at class level —
each constraint carries all 8 (polarity × register × directionality) cells once,
and syntax rotates across constraints as `SYNTAX[(cell_index + constraint_index)
% 3]`, giving exactly 10 observations per factor cell per class and 40 across the
benchmark. It records two consequences explicitly: syntax must split 3/3/2 within
a constraint because 8 is not divisible by 3, and **"directionality may change
`answer_type` within a constraint"**.

§4.4.2 requires exact class-level balance and K=8; it does not specify how to
achieve both, since 24 factor cells cannot be crossed within 8 probes. ADR-0003
is one solution to a problem the proposal poses and leaves open.

### D. What would become invalid or reworkable if we author before approval

The two ADRs carry very different exposure, and it is worth separating them:

**ADR-0002 — expensive if rejected.** It fixes the family structure, the schema
count and every `family_id`, `schema_id` and `constraint_id`. If you chose 7
schemas per class, or a blocking structure other than the 4-class family, then:
the 24 schema definitions change; the 120-cell allocation changes; all 120
constraint ids are re-keyed; `configs/benchmark/design.yaml` changes and
`design_validator.py`'s expectations with it. Constraint *content* — entities,
gold answers, sources, evidence records — would largely survive a re-keying, but
every record would be rewritten and the Wikidata evidence re-verified against new
ids. This is the one worth not pre-empting.

**ADR-0003 — cheap if rejected.** It governs probes, not constraints. Probe
surface text is generated from templates in
`src/semintegrity/probes/surface.py` and factor cells from
`src/semintegrity/probes/factor_design.py`, so rejecting it means regenerating
960 probes, not re-authoring anything. The constraint records are untouched. The
real cost of a late change here is not authoring but **human probe validation**:
§4.12 Phase 5's gate is "human probe validation", and §4.4.5 validated probes
would have to be re-validated. If probes have already been through annotation
when the factor design changes, that annotation effort is lost.

One engineering detail that becomes load-bearing under ADR-0003 and is worth
recording before authoring: `constraint_index` in the syntax rotation is, per
`factor_design.py`, "the constraint's 0-based position **within its class**", and
`pilot_builder.py` assigns it as a running counter in source-file order. So **the
order of families in the authoring file determines probe syntax**, and it "must
be stable once the benchmark is frozen". The canonical ordering needs to be
pinned explicitly rather than inherited from however the file happens to be
written.

### E. Engineering or methodology?

**Methodology, both.** Both ADRs are marked `**Kind:** METHODOLOGY` and both read
AWAITING RESEARCHER APPROVAL. I am not approving them, and I have not changed
either status. The matrix is an *instance* of them offered for review; it does
not and cannot ratify them.

---

## Issue #3 — answer type and class

### A. The exact §4.3 requirement

Verbatim, the whole of the relevant paragraph:

> "**Matched nuisance factors, not matched semantics.** Constraints are authored
> in families that hold nuisance variation **approximately constant** across
> classes — same domain, **comparable entity familiarity, comparable answer
> type, comparable lexical complexity** — while the structural requirement
> changes. The four class variants within a family are deliberately **not**
> semantically equivalent; the goal is to reduce nuisance variation, not to
> produce logically identical statements."

Three further facts bound how much that sentence can carry:

1. **`answer_type` is not one of §4.3's per-constraint fields.** The proposal
   lists 17: `constraint_id, family_id, schema_id, domain, class,
   formal_predicate, constraint_text, entities[], entity_qids[],
   entity_sitelinks[], gold_proposition, gold_source, gold_source_url,
   gold_source_date, temporal_validity, ambiguity_notes,
   prerequisite_atomic_facts[]`. No `answer_type`.
2. **`answer_type` is a *probe* field.** §4.4.1's formal probe representation is
   `constraint_id, probe_id, logical_form, subject, predicate, object,
   time_scope, quantifier, polarity, **answer_type**`. The constraint-level
   `answer_type` in `schemas/constraint.py` is marked `DERIVED` and documented as
   "the canonical answer type; Stage 0 maps every probe into it", added because
   §4.7 requires a closed answer space.
3. **The proposal expects answer type to vary within a constraint.** §4.7:
   "the directionality probe factor mixes 'Is A the X of B?' (yes/no) with 'What
   is the X of B?' (an entity), and comparing those raw strings is meaningless."
   ADR-0003 states the same thing as a consequence. This is exactly what Stage 0
   exists to reconcile.

### B. What the pilot and the matrix each do

**The pilot** (12 DRAFT constraints, `data/benchmark/pilot/constraints.jsonl`)
makes the constraint-level canonical answer type a perfect function of class:

| class | answer type | answer-space size |
|---|---|---|
| C1 | `entity` | 3 |
| C2 | `boolean` | 2 |
| C3 | `boolean` | 2 |
| C4 | `date` | 3 |

At probe level the picture is quite different, and it weakens the concern I
raised. In `K-C1-GEO-01`, the 8 probes are 4 `reverse/boolean`, 2
`direct/boolean`, 2 `direct/entity` — so **only 2 of 8 probes elicit the
constraint's canonical type**, and 6 of 8 are boolean. The same holds in
`K-C4-GEO-01`. Every constraint in every class already carries a mostly-boolean
probe set, by ADR-0003's construction.

**The matrix** (`docs/BENCHMARK_COVERAGE_MATRIX.md`) instead fixes answer type on
the *axis*, so all four class variants in a family share one type, and each class
receives 15 `entity`, 10 `boolean` and 5 `date` constraints. Answer type is then
orthogonal to class by construction.

### C. Required by the proposal, or an interpretation?

**An interpretation introduced by the matrix.** Stating it plainly:

* §4.3 asks for nuisance variation "approximately constant" across classes within
  a family and names "comparable answer type" as one such nuisance. The matrix's
  allocation satisfies that. So does any allocation where the four class variants
  of a family share a type.
* But §4.3 does **not** require answer type to be crossed with class, does not
  carry answer type as a constraint field at all, and §4.7 and §4.4.2 positively
  expect probe-level answer type to vary. "Comparable" and "approximately" are
  the proposal's words, not "identical" or "balanced exactly" — the latter phrase
  §4.4.2 reserves for the four probe transformation factors, which do not include
  answer type.
* The pilot's arrangement is harder to defend under §4.3 than the matrix's, since
  a perfect functional dependence on class is not "approximately constant across
  classes" on any reading. But it is a deviation from a soft requirement, not a
  violation of a hard one.

### D. Concrete consequence

Sharper than "an answer-format artefact", and it cuts in a direction worth
knowing:

* **The confirmatory contrast is unaffected.** §4.11's confirmatory test is
  C1+C2 versus C3+C4. Under the pilot's pairing, arm 1 holds one 3-option class
  and one 2-option class, and so does arm 2. Answer-space cardinality is
  **balanced across the two confirmatory arms**, so the confound cannot bias the
  claim that carries the study.
* **The descriptive four-class profile is affected.** Chance agreement is higher
  in a 2-option space than a 3-option one, so per-class PSCR estimates for C2/C3
  are not directly comparable with C1/C4 under the pilot's pairing, and §4.11's
  model has no answer-space-cardinality term to absorb it — the class coefficient
  would carry it. §4.11 presents the four-class profile as descriptive, which
  limits but does not remove the problem.
* **The planned contrast is the weakest case.** "C4 versus C1–C3 pooled" compares
  a 3-option class against a pooled set that is {3, 2, 2}.
* **Cost of the matrix's alternative:** some renderings get harder to author (a
  `date`-typed C1, a `boolean`-typed C4), and the pilot's 12 constraints stop
  being instances of the 24 schemas — which bears on ADR-0007's "dev constraints
  reuse the **same schemas** but different entity instantiations".

### E. Engineering or methodology?

**Methodology.** It changes what the measured class effect means, touches §4.3's
nuisance-control claim and ADR-0002's schema definitions, and alters the relation
between the dev set and the test set. Not mine to take, and not taken.

A third option exists and is worth having on the table alongside the other two:
hold answer type constant **within each family** (satisfying §4.3 literally)
while allowing the *mix* of types to differ across axes, then add answer-space
cardinality as a covariate or report per-class PSCR stratified by it. That
satisfies §4.3 without forcing every axis to render in all three types.

---

## The matrix's proposed 120-cell allocation, as it stands

Reported from `docs/BENCHMARK_COVERAGE_MATRIX.md`, unmodified.

Six axes, each supplying a family theme in all 5 domains and a schema in all 4
classes → 30 families, 24 schemas, 120 cells.

| axis | name | answer type | invariant |
|---|---|---|---|
| 1 | Unique designated role-bearer | `entity` | exactly one bearer of a named functional role |
| 2 | Disjoint category membership | `boolean` | membership of one category entails non-membership of the other |
| 3 | Part-whole containment | `entity` | each part sits in exactly one whole per level; containment composes |
| 4 | Event precedence | `boolean` | two dated events stand in a fixed order |
| 5 | Extremal uniqueness | `entity` | a superlative over a closed set has exactly one bearer |
| 6 | Interval boundary | `date` | a terminating boundary date bounds everything the entity did |

Allocation: family index = axis index within a domain; schema index = axis index
within a class. Test indices are 11..16, leaving 01..10 to pilot/dev. So the cell
for (axis *a*, domain *d*, class *c*) is `K-c-<DOM>-1a`, in family `F-<DOM>-1a`,
under schema `S-c-0a` — 120 cells, e.g. `K-C3-BIO-14` is axis 4 in biology at C3,
family `F-BIO-14`, schema `S-C3-04`.

The 30 family themes, by domain:

| axis | geography | history | biology | public_office | science_technology |
|---|---|---|---|---|---|
| 1 | capital city of a country | capital of a historical polity | type species of a genus | holder of a single-seat head-of-state office | SI base unit of a physical quantity |
| 2 | coastal vs landlocked states | wartime alliance membership | vertebrate class membership | constitutionally incompatible offices | periodic-table group membership |
| 3 | city within a first-level admin division | province within an empire | genus within a family | constituency within a federal unit | module within a crewed spacecraft |
| 4 | opening of major interoceanic canals | onset of the Atlantic revolutions | landmark results in molecular genetics | decolonisation independence dates | milestones in solid-state electronics |
| 5 | highest summit of a continent | longest reign in a named monarchy | largest extant species of a clade | longest-serving holder of a named office | heaviest naturally occurring element |
| 6 | dissolution of a federal state | end of a classical empire | extinction date of a named species | abolition of a colonial office | end of a crewed spaceflight programme |

**Verification status of the allocation.** Instantiated as 120 structural
placeholders (real ids, classes, domains, families, schemas; visibly fake
entities and gold answers, never written to `data/`) and run through
`design_validator.py` with `strict_schema_crossing=True`: **10/10 rules pass**,
schema × domain fully crossed, so Q12's balanced-incomplete fallback is not
invoked. Three cells are flagged in advance as the likeliest to force it:
`axis 5 / science_technology / C4`, `axis 5 / geography / C4`,
`axis 6 / biology / C2`.

**Two caveats on that PASS, both stated in the matrix itself.**
`sitelink_matching` is **vacuous**: every placeholder carries 0 sitelinks, so the
rule reports perfect matching by degeneracy. Entity-familiarity matching —
§4.3's "most damaging alternative explanation for any observed class effect" —
can only be tested once real entities are chosen. And `predicate_registered`
was not run: 12 of the 24 schemas name a D0 predicate that does not exist, 4
name the pilot's closed-space placeholders, and 8 name a real one.

**One wording correction the matrix needs** (not made, per your instruction):
§8's M2 says "§4.3 requires families to hold 'comparable answer type' constant".
It should read "approximately constant", and should state that the axis-fixed
allocation is an interpretation rather than a requirement. Issue #3 above is the
corrected version.

---

## DECISIONS REQUIRED FROM RESEARCHER

1. **ADR-0002 — the design lattice.** Approve, amend or reject. The 120-cell
   allocation, all 24 schema definitions and every constraint, family and schema
   id depend on it; rejection after authoring means re-keying all 120 records.
   Specifically: 6 schemas per class at 5 instances each (the uniform reading of
   §4.3's 6–8 × 4–5), and family as the 4-class nuisance-control block.

2. **ADR-0003 — probe factor balancing at K=8.** Approve, amend or reject.
   Rejection is cheap in authoring terms (probes regenerate from templates) but
   expensive once human probe validation has run against the probes it produces.

3. **Answer type versus class — issue #3.** Choose one, and it needs an ADR plus
   an `OPEN_QUESTIONS.md` entry either way:
   - (a) keep the pilot's class-tied answer types and record the confound in
     §4.14's limitations, noting that the confirmatory contrast is unaffected;
   - (b) adopt the matrix's axis-fixed allocation (15 `entity` / 10 `boolean` /
     5 `date` per class), accepting harder renderings and the knock-on to
     ADR-0007's "same schemas" clause;
   - (c) hold answer type constant within family but let the mix vary across
     axes, and carry answer-space cardinality as a covariate.

4. **Confirmation of ADR-0007's authoring bill.** ADR-0007 is already APPROVED
   and I am not reopening it; what needs your acknowledgement is the consequence
   now that it is quantified — **120 new test constraints plus 12 new dev
   constraints, 132 in all**, not 108 — together with the §5.6 reading that the
   12 pilot constraints are already tuning data and so cannot become test
   constraints.

5. **D0 predicate scope (methodology, from the matrix's M4).** 12 of 24 schemas
   name a predicate that does not exist. Either implement them (each then needs
   §4.8.2's three-instance schema audit before freeze) or implement fewer and
   report lower D0 coverage, which §4.8.1 treats as a result in its own right.
   This changes the authoring order, not the matrix.

### Not requiring your approval — taken and recorded as engineering

* **Test id indices 11..16**, leaving 01..10 to pilot/dev. The alternative
  collides with all 12 existing pilot ids, and renumbering the pilot instead
  would desynchronise the two byte-identical pilot result files that ADR-0005
  makes immutable.
* **Pinning the canonical family ordering** that defines `constraint_index`
  before probe generation, since source-file order currently determines probe
  syntax and must be stable once frozen.
* Fixing `_unique_ids`, whose docstring promises more than it checks, and adding
  the cross-split id uniqueness check it lacks.
