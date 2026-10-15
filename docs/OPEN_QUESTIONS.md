# Open questions, ambiguities and technical risks

Raised from a complete read of `proposal/semintegrity_proposal.docx` (v2).

**Nothing in the proposal has been changed.** Where the proposal
underdetermines an implementation, a resolution is *proposed* and marked
`PENDING SIGN-OFF`. Where the proposal is internally inconsistent, it is marked
`CONFLICT` and no code depending on it will be written until the researcher
decides.

Severity: **BLOCKING** = the named phase cannot complete correctly without a
decision · **SIGNIFICANT** = affects validity or cost · **MINOR** = tidy-up.

---

## Q1 — The development/test split is undefined, and collides with the 60/60 confirmatory arms
**RESOLVED 2026-09-11** — separate 24-constraint dev set, disjoint from the 120. See `docs/decisions/ADR-0007`.
**Was: BLOCKING — Phase 2, Phase 4** · `CONFLICT`

§5.6 requires "a frozen development/test split so that NLI thresholds, judge
prompts and extraction rules are tuned only on development data", and §4.8.2
distinguishes dev-split from test-split behaviour for D0 predicates. But §4.3
sizes the benchmark at exactly 120 constraints and §4.11 rests the confirmatory
claim on "C1+C2 versus C3+C4 (60 constraints per arm)".

These cannot both hold if the dev split is carved out of the 120: a 20% dev
split leaves 48 per arm, and the sample-size argument in Appendix A.1 — which
explicitly rejected n=15 per class because intervals overlapped — is weakened by
the same reasoning.

**Proposed resolution (recommended):** the 120 constraints *are* the test set.
Author a **separate, disjoint development set** of ~24 constraints (6 per class,
same schemas, different entity instantiations), seeded by the 12 Phase-1 pilot
constraints. Cost: ~12 additional constraints and their probes. Benefit: the
confirmatory arms stay at 60/60 exactly as preregistered, and every tuned
artefact (D2 threshold, D3 prompt, extraction rules, alias tables, D0 fixes) is
demonstrably untouched by test data.

**Alternatives:** (b) split 120 into 96 test / 24 dev and restate the power
argument; (c) tune only on the 12 pilot constraints, accepting very thin
per-class calibration data for D2.

**Knock-on:** D2 thresholds are calibrated *per class* (§4.8.4). Per-class
calibration needs enough human-labelled contradiction pairs *per class* on the
dev split. 6 dev constraints × 28 pairs × models gives a workable pool; 3 does
not.

---

## Q2 — "Factors balanced exactly across classes" is impossible within a constraint at K=8
**RESOLVED 2026-10-06** — ADR-0003 approved by the researcher. See
`docs/decisions/ADR-0003-probe-factor-balancing.md`.
**Was: SIGNIFICANT — Phase 5** · `RESOLVED, PENDING SIGN-OFF`

§4.4.2 lists four factors: syntax (3) × polarity (2) × register (2) ×
directionality (2) = **24 cells**, but K = 8. A full crossing inside one
constraint cannot exist.

**Resolution (arithmetically exact, already implemented and tested):**
* (polarity × register × directionality) = 2×2×2 = **8 = K** → every constraint
  carries each of these cells **exactly once**;
* syntax rotates across constraints: `SYNTAX[(cell_index + constraint_index) % 3]`;
* per class: 30 × 8 = 240 slots over 24 cells = **exactly 10 per cell**;
* whole benchmark: 960 / 24 = **exactly 40 per cell**.

Within a constraint syntax must split 3/3/2 (8 is not divisible by 3). Balance is
therefore a **class-level** property — which is the level §4.4.2 actually argues
at ("a class effect cannot be an artefact of ... more negated phrasings appearing
at C4"). See `docs/decisions/ADR-0003` and `tests/unit/test_probe_balance.py`.

---

## Q3 — The D3 judge model is not named
**RESOLVED 2026-09-11** — open-weight judge: `microsoft/phi-4` primary, `allenai/OLMo-2-1124-13B-Instruct` cross-check. API cost eliminated. See `docs/decisions/ADR-0008`.
**Was: BLOCKING — Phase 2, Phase 7** · `MISSING SPECIFICATION`

§4.8.5 requires a judge "external to every evaluated model", version-pinned,
plus "a strong open-weight judge on a stratified subset as a reproducibility
check". No model is named. Appendix A.1 notes the reproducibility concern
"migrates to the LLM judge", implying a closed API judge was intended.

**Decision needed on two axes:** (a) closed API vs open-weight primary judge;
(b) which specific model, pinned to a snapshot/revision.

**Cost, if API:** upper bound 120 constraints × 28 pairs × 7 models =
**23,520 judgements** (fewer after ABSTAIN filtering), plus a 3× stability
subset. At roughly 600 input / 150 output tokens per judgement this is ~14M
input and ~3.5M output tokens. This is a real budget line and needs approval
before Phase 7.

**Note:** the judge cannot be Llama-3.3-70B, and cannot be any Qwen, Mistral or
Gemma model, because all four families are evaluated.

---

## Q4 — The beta-binomial formula mixes units of analysis
**RESOLVED 2026-09-11** — option (A), disaggregated binomial cells. Preregistered deviation. See `docs/decisions/ADR-0009`.
**Was: BLOCKING — Phase 4, Phase 8** · `CONFLICT`

§4.11 specifies:

```
contradictions / evaluable_pairs ~ class * model_family + log(entity_sitelinks)
  + probe_polarity + probe_syntax + probe_direction
  + (1 | schema/constraint) + (1 | domain)
```

The response is aggregated to **constraint × model**. But `probe_polarity`,
`probe_syntax` and `probe_direction` are properties of an individual **probe**,
and each observation in the numerator is a **pair of two probes** whose factor
levels generally differ. As written, these three covariates have no well-defined
value at the row's unit of analysis.

**Options:**
* **(A) Disaggregate (recommended).** Expand the binomial rows to
  `constraint × model × pair-factor-cell`, where a pair-factor cell is the
  unordered combination of the two probes' levels (e.g. polarity:
  `aff–aff` / `aff–neg` / `neg–neg`). Keeps the beta-binomial structure, makes
  the covariates well-defined, and directly answers "does negation drive
  contradictions".
* **(B) Pair-level binomial GLMM** with crossed random effects for probe A and
  probe B nested in constraint. Most faithful to the data, heaviest to fit, and
  in mild tension with §4.11's own warning against pair-level modelling.
* **(C)** Drop the three probe factors from the model and report them
  descriptively.

This changes a preregistered formula, so it needs an explicit decision before
Phase 4.

---

## Q5 — D4: length-normalised log-probabilities are not a probability distribution
**SIGNIFICANT — Phase 7** · `MISSING SPECIFICATION`

§4.8.6 requires candidate sequences to be "length-normalised to per-token
log-probability" and then a Jensen–Shannon divergence over the resulting
"distribution". Per-token means do not sum to 1 over the candidate set, so the
mapping to a distribution must be specified and frozen, and the JSD value
depends on which mapping is chosen.

**Proposed:** `p_i = softmax_i(mean_token_logprob_i)` over the closed candidate
set, with no temperature. Alternatives: renormalise `exp(sum logprob)` (drops
length normalisation, which §4.8.6 rejects) or `softmax(mean_logprob / T)` with
a frozen `T`. Whichever is chosen goes in the preregistration, because JSD
magnitudes are not comparable across choices.

---

## Q6 — "Evaluable probe pair" is never defined, and PSCR can have a zero denominator
**BLOCKING — Phase 8** · `MISSING SPECIFICATION`

PSCR is "contradictory probe pairs ÷ evaluable probe pairs" (§4.10). The
proposal does not say which pairs are evaluable, and §4.7 creates four
non-answer labels (ABSTAIN, INVALID, AMBIGUOUS, FAILED).

**Proposed:** a pair is evaluable iff **both** responses canonicalise to an
ANSWER. Consequence: a constraint × model cell where the model abstains on ≥7 of
8 probes has 0 evaluable pairs and **PSCR is undefined**.

**Proposed policy:** such cells are `NA`, carried through the cluster bootstrap
as missing and **never imputed as 0**. Imputing 0 would score an abstaining
model as perfectly consistent — exactly the failure §4.10's reliability triad
exists to prevent. The count and per-class rate of NA cells must be reported
alongside abstention rate.

**Risk:** §4.7 expects abstention to rise at C4, and the pilot go/no-go
criterion `ABSTAIN` exists for this. If NA cells cluster at C4, the confirmatory
contrast is computed on a class-imbalanced subset. A sensitivity analysis
(worst-case and best-case imputation bounds) should be preregistered.

---

## Q7 — AUPRC is not computable for D0 and D1
**MINOR — Phase 7** · `AMBIGUITY`

§4.10 lists "Detector P/R/F1, AUPRC ... per detector, per constraint class".
D0 and D1 are deterministic and binary: they yield a single operating point, not
a curve. **Proposed:** report P/R/F1 for all detectors, and AUPRC only for D2
(contradiction probability) and D3 (judge confidence). State this in the table
caption rather than leaving blanks.

---

## Q8 — Beta-binomial mixed-model backend is undecided
**SIGNIFICANT — Phase 8** · `TOOLING`

The canonical tool is `glmmTMB` (R). There is **no R on the local machine**, and
cluster R availability is unknown until the probe runs. Python has no mature
frequentist beta-binomial GLMM.

**Proposed:** fit in **PyMC** (Bayesian beta-binomial with random intercepts for
schema/constraint and domain), report posterior means and credible intervals,
and — if R turns out to be available — cross-check against `glmmTMB`. Either way
§4.11's precedence rule holds: the cluster bootstrap carries the confirmatory
claim.

Whichever is chosen must be documented exactly, as §4.11 requires.

---

## Q9 — The second annotator does not exist yet
**BLOCKING — Phase 5, Phase 7** · `HUMAN RESOURCE`

§4.9 requires two annotators with adjudication, and §4.4.5 requires two-annotator
semantic validation of the primary-tier probes. The proposal itself says the
binding resource is "authoring and annotation effort, not GPU time" (§4.13).

**Estimated human load:**

| Task | Items | Annotators | Judgements |
|---|---|---|---|
| Primary probe equivalence validation | 960 | 2 | 1,920 |
| Saturation probe screen | 1,008 | 1 | 1,008 |
| Annotation sample A | ~400 pairs | 2 | 800 |
| Annotation sample B | ~300 pairs | 2 | 600 |
| Adjudication | disagreements only | 1 | ~200–400 |
| **Total** | | | **~4,500–4,700** |

A named second annotator, their training/calibration batch, and any required
ethics/consent paperwork are prerequisites. **I will build the interface,
sampling, blinding and agreement analysis; I will never generate an annotation.**

---

## Q10 — Which three models for the Phase 3 pilot?
**MINOR — Phase 3** · `MISSING SPECIFICATION`

§4.12 specifies "12 constraints × 5 probes × 3 models" without naming them.
**Proposed:** `qwen25-3b` (cheapest, fastest iteration), `llama31-8b` (second
family), `gemma2-9b` (third family **and** the model with the known silent
degradation hazard — surfacing it at pilot time is the point).

---

## Q11 — "Inter-annotator agreement is acceptable" has no number
**SIGNIFICANT — Phase 4** · `AMBIGUITY`

A pilot go/no-go criterion (§4.12) that is not quantified cannot gate anything,
and fixing it after seeing pilot results defeats its purpose. A threshold on
Krippendorff's α for the `relation` label must be fixed at preregistration.
**Proposed:** α ≥ 0.67 as the minimum for tentative conclusions, α ≥ 0.80 as the
target, following the conventional reporting bands — to be confirmed by the
researcher.

---

## Q12 — Can all six schemas per class be instantiated in all five domains?
**PARTIALLY RESOLVED 2026-10-06.** The *lattice* half is settled: ADR-0002 is
approved, and the adopted allocation in `docs/BENCHMARK_COVERAGE_MATRIX.md` is
**fully crossed** 6 × 5, verified by a 120-placeholder dry-run through
`design_validator.py` with `strict_schema_crossing=True`. The *feasibility* half
stays open until the constraints are authored: whether every cell can actually be
written is not knowable before authoring, and three cells are recorded in advance
as the likeliest to force the balanced-incomplete fallback
(`axis 5 / science_technology / C4`, `axis 5 / geography / C4`,
`axis 4 and axis 6 / biology / C2`). The fallback remains available and
`strict_schema_crossing=False` still permits it.
**Still: SIGNIFICANT — Phase 5** · `FEASIBILITY`

The counts in §4.3 (30 per class; 6 schemas × 5 instances; 6 per domain per
class) close exactly **iff** schema × domain is fully crossed 6×5. That requires
every schema to have an instance in every domain — plausible for C1 ("X is the
Y of Z") but strained for C2/C4 in biology (offices, tenures and appointment
dates have no natural biological analogue).

**Proposed:** allow a *balanced incomplete* schema × domain allocation: keep 6
constraints per (domain, class) and 5 instances per schema, but do not require
each schema to appear in every domain. The allocation matrix is authored
explicitly, validated by `design_validator.py`, and published. A fully crossed
design is attempted first and relaxed only where authoring proves infeasible.

---

## Q13 — Gemma-2 silent degradation is a single point of failure for one model arm
**SIGNIFICANT — Phase 6** · `TECHNICAL RISK`

§4.6 flags it: attention logit soft-capping and sliding-window attention are
dropped by some FlashAttention-2/vLLM builds, producing degraded output that is
"indistinguishable from a high contradiction rate". A silent failure here would
not invalidate the study — it would produce a *plausible-looking wrong result*
for one of the four families.

**The proposal requires a "known-good reference" but does not define one.**
**Proposed preflight gate** (`scripts/models/gemma2_softcap_check.py`), which
must pass before any Gemma-2 result is admitted:
1. assert the serving stack reports soft-capping enabled (config + version);
2. generate a fixed prompt set under vLLM **and** under HF `transformers`
   eager attention (the reference path, slow but correct) and require exact or
   near-exact agreement;
3. record both outputs and the version matrix in `results/manifests/`.

---

## Q14 — Gated weights and ~244 GB of storage
**BLOCKING — Phase 6** · `ACCESS / CAPACITY` · **HUMAN-ONLY**

* `meta-llama/Llama-3.1-8B-Instruct`, `meta-llama/Llama-3.3-70B-Instruct`,
  `google/gemma-2-9b-it` and `mistralai/Mistral-7B-Instruct-v0.3` are gated on
  Hugging Face. **The researcher must accept each licence with their own
  account and create a read token.** I will not handle the token; the scripts
  read it from the environment and never log or store it.
* bf16 weights for all seven models ≈ **244 GB** (3B ~7 + 7B ~16 + 7B ~15 +
  8B ~16 + 9B ~19 + 14B ~30 + 70B ~141). The cluster quota is unknown. If quota
  is tight, models can be staged and evicted in a fixed order — but the 70B alone
  needs ~141 GB free.
* Weights are cached **once from a non-GPU session** (§4.13), never inside GPU
  time.

---

## Q15 — Track B needs an extraction rule that Track A was designed to avoid
**SIGNIFICANT — Phase 6** · `MISSING SPECIFICATION`

§4.4.3 justifies Track A's constrained format because it "removes hedging,
elaboration and extraction error". Track B reintroduces all three by design, so
it needs an explicit extraction step that the proposal does not specify.

**Proposed:** a rule-based extractor over the constraint's closed answer space
plus alias tables (the same machinery as Stage 0), tuned on the development
split only, frozen before test evaluation, with its extraction error rate
measured against a small human-checked subset and reported. Using an LLM
extractor would import judge-model bias into a track whose purpose is to
validate Track A.

---

## Q16 — The distractor-context secondary experiment is unscoped
**MINOR — later** · `AMBIGUITY`

§4.4.2 excludes distractor context from the primary set and promises "a separate
secondary experiment". Its size, probe count, model coverage and analysis plan
are not specified anywhere, and it is not in the §4.12 phase table. **Proposed:**
treat it as out of scope for the main deliverable, with a stub design recorded
so the claim in §4.4.2 remains honest.

---

## Q17 — Consistency@K inherits AOCR's saturation problem
**MINOR — Phase 8** · `OBSERVATION`

§4.10 demotes AOCR because it saturates as a function of K and measures detector
false positives. Consistency@K ("proportion of constraints with **no**
contradiction among K probes") is `1 − AOCR` under the same detector and the
same K, so it inherits the identical sensitivity. It is already listed as
secondary; the suggestion is simply that it carry the same K-dependence label in
every table and caption.

---

## Q18 — Generation volume recount
**MINOR — planning** · `OBSERVATION`

§4.13 estimates "roughly 19,000 short generations". Itemised:

| Workload | Per model | × 7 models |
|---|---|---|
| Primary Track A (960 probes) | 960 | 6,720 |
| Saturation (1,008 extra probes) | 1,008 | 7,056 |
| Track B (20×8) | 160 | 1,120 |
| Stochastic (20×8×3) | 480 | 3,360 |
| Knowledge screen (~2.5 facts × 120) | ~300 | ~2,100 |
| Determinism check (100 × 2 modes) | 200 | 1,400 |
| **Total** | | **≈ 21,750** |

Consistent with the proposal's "roughly 19,000" as an order-of-magnitude figure.
**Not counted there:** D4 teacher-forced scoring — 960 probes × 7 models ×
|candidate set| forward passes (≈ 27,000 at 4 candidates). These are scoring
passes, not generations, and are cheap, but they need GPU time and a code path
that exposes log-probabilities.

---

## Q19 — The determinism check needs a defined comparison
**MINOR — Phase 6** · `AMBIGUITY`

§4.6 says determinism is "verified empirically by re-running 100 prompts and
diffing". Batched GPU inference is non-deterministic mainly through *batch
composition*, so a rerun that reproduces the original batching may show zero
variance and prove little. **Proposed:** run both modes — identical batch
composition (isolates kernel non-determinism) and shuffled batch composition
(isolates batch-composition non-determinism) — and report exact-string and
canonical-label agreement separately for each. Already encoded in
`configs/inference/determinism_check.yaml`.

---

## Q20 — Cluster access logistics
**PARTIALLY RESOLVED** — 2026-09-11: interaction model decided (researcher runs all cluster commands, ADR-0010). 2026-09-25: host `172.24.16.132`, port 22, account `yashsinha` (a **shared lab account**), and the working directory `/nfs_home/users/yashsinha/H20250058_Suraj` all **confirmed by the professor** — the "another user's home" concern is closed; it is a shared account, and the subfolder is this researcher's designated space. Shared-account rules are now encoded in `configs/cluster/cluster.yaml`. Remaining: the cluster *facts* (partitions, GPUs, CUDA, quota) still need the probe.
**Was: BLOCKING — Phase 6** · `INFRASTRUCTURE`

The working directory `/nfs_home/users/yashsinha/H20250058_Suraj` sits under
another user's home directory. Worth confirming this is the intended designated
space and that it is writable by your account, since §"Cluster environment"
forbids modifying other users' folders.

Also unknown until `scripts/cluster/probe_cluster.sh` runs: partition names, GPU
models and counts, CUDA/driver versions, module system, storage quota, whether
the login node has internet (needed to cache Wikidata and weights), and whether
R is available (Q8).

---

## Q21 — `polarity` sits inside the formal representation *and* is a meaning-preserving factor
**BLOCKING — Phase 5** · `CONFLICT` · **METHODOLOGY — AWAITING APPROVAL**

§4.4.1 defines semantic equivalence as identity of the formal representation and
lists ten fields, one of which is `polarity`. §4.4.2 simultaneously makes
polarity a *meaning-preserving transformation factor*, balanced across classes.

Read literally, both cannot hold: an affirmative probe and its negated
counterpart would have different representations, therefore not be equivalent,
therefore not be paraphrases of one another — which empties the polarity factor
of its purpose and would make 4 of every 8 probes ineligible for the pairwise
comparison that PSCR counts.

**Proposed resolution (implemented behind one switch, not decided).**
`logical_form` is polarity-normalised, so an affirmative and a negated probe of
the same question share one `logical_form`, and the equivalence key is:

```python
EQUIVALENCE_KEY_FIELDS = ("logical_form", "subject", "predicate",
                          "object", "time_scope", "quantifier")
```

`polarity` is recorded on every probe and governs the Stage 0 mapping instead —
exactly as §4.7 already handles directionality, where "Is A the X of B?" (yes/no)
and "What is the X of B?" (entity) reach a common canonical space. A negated
probe's `YES` and an affirmative probe's `NO` map to the same canonical answer.

**This is a single tuple in `src/semintegrity/schemas/probe.py`.** Changing it
changes what the study treats as "the same question asked differently", so it
needs your decision, not mine.

**Alternative:** keep polarity in the equivalence key and treat affirmative and
negated probes as two separate paraphrase sets per constraint, comparing within
but never across. That halves the pairs per constraint from 28 to 12 and removes
the negation-sensitivity finding §5.5 promises.

### Empirical evidence from the first cluster pilot (2026-09-25, job 11969)

This stopped being hypothetical. Qwen2.5-3B, 96 probes, K=8, on the A100:

```
ANSWER 46 (47.9%) · INVALID 32 (33.3%) · ABSTAIN 18 (18.8%)
canonicalisation rate 66.7%  -- CANON go/no-go requires >= 95%  -> FAIL
```

INVALID is structural, not noise:

| cell | INVALID rate |
|---|---|
| `answer_type=entity` | 58.3% |
| `answer_type=date` | 58.3% |
| `answer_type=boolean` | 8.3% |
| `directionality=reverse` | 45.8% |
| `directionality=direct` | 20.8% |

28 of the 32 are polar answers to non-boolean constraints, e.g.

```
K-C1-GEO-01 [entity] space ['Canberra','Sydney','Melbourne']
  P02 [affirmative/interrogative/reverse]
      asked: Is Canberra the capital city of Australia?
      said : 'yes'   -> INVALID
```

**The discarded third contains the signal the study exists to measure.** Reading
those answers under the mapping proposed above:

* `K-C1-SCI-01`: P05/P06/P08 -> "Au", but P02 `'NO'` and P07 `'YES'` -> "not Au".
  The model contradicts itself about gold's symbol across equivalent probes.
* `K-C4-GEO-01`: four probes -> 1927, but P05 `'YES'` to *"Is it false that...1927?"* -> not-1927.
* `K-C4-POL-01`: three -> 1789, P04 `'NO'` -> not-1789.

So **PSCR 0.185 from this run is very likely an underestimate with a known
direction**: contradictions are being converted into INVALID and dropped, not
counted. Coverage was 0.253.

**What this does and does not settle.** The directionality half is already
specified by §4.7 and is an implementation gap, not a decision. The polarity
half is this question. They cannot be implemented separately: P08
`[negated/interrogative/reverse]` needs both. A third case is undecided by
either -- affirmative + `NO` maps to `¬X`, a *set* rather than a member of the
closed answer space, which needs Q6's definition of an evaluable pair.

Reproduce with:
`python scripts/analysis/inspect_stage0.py --raw results/raw/pilot/qwen25-3b.jsonl --split pilot`

---

## Q22 — D0's reference implementation is set-level; PSCR is pairwise
**SIGNIFICANT — Phase 7** · `AMBIGUITY` · **METHODOLOGY — AWAITING APPROVAL**

§4.8.2's worked example iterates over responses and checks each against the
knowledge base, returning a single `VIOLATION`/`SATISFIED` for the constraint.
§4.10 defines the primary endpoint PSCR as *contradictory probe pairs ÷ evaluable
probe pairs*. §4.8.1 then routes "the primary profile" through D0 wherever D0
applies. The unit does not match.

**Implemented (both, so the decision does not have to precede the data):**

* `check_pair(constraint, a, b, kb)` — whether two canonicalised responses are
  jointly satisfiable. **This is what feeds PSCR.**
* `check_set(constraint, responses, kb)` — the §4.8.2 reading, defaulting to
  "SATISFIED unless some pair contradicts", reported as the integrity view.

Both verdicts are computed and stored for every constraint × model.

**Decision needed:** which one the paper reports as "D0", and whether the
set-level verdict appears as a separate integrity statistic. My recommendation:
`check_pair` is D0 for all detector-comparison and PSCR purposes (it is the only
one commensurable with D1/D2/D3, which are all pairwise), and the set-level
verdict is reported alongside D0 coverage as a descriptive integrity measure.

---

## Q23 — Answer type is confounded with class in the pilot
**RESOLVED 2026-10-06** — answer type is fixed by schema axis, with answer-space
cardinality retained as a covariate, and two `date` axes.
See `docs/decisions/ADR-0017-answer-type-allocation.md`.
**Was: SIGNIFICANT — Phase 5** · `VALIDITY`

§4.3 asks families to hold nuisance variation "approximately constant across
classes", listing "comparable answer type". The 12 pilot constraints do the
opposite: answer type is a perfect function of class (C1 `entity`, C2/C3
`boolean`, C4 `date`), so chance agreement differs by class before any model
behaviour is involved — 1 − 1/*m* is 0.667 at m=3 and 0.500 at m=2.

The confound does **not** reach the confirmatory contrast: C1+C2 and C3+C4 each
hold one 3-option and one 2-option class, so both arms sit at 0.583. It reaches
the descriptive four-class profile (spread 0.167) and the planned C4-versus-
pooled contrast (0.111), and H1 makes a per-class claim.

Three options were compared in `docs/DESIGN_RESOLUTION_2026-10-06.md` §3.
Options (b) and (c) turned out to be the same design — under ADR-0002's lattice
every axis contributes one constraint to every (class, domain) cell, so *any*
axis-determined answer type is automatically balanced across classes — which
reduced the decision to a binary one. The adopted allocation gives every class
chance-PSCR 0.611.

Accepted cost, recorded in ADR-0017: D0's structural coverage on C4 drops from
30/30 to 10/30, because the temporal-anchor predicate needs a date answer and
class-level balance forbids C4 holding more date constraints than C1.

---

## Q24 — The polar-cloze probe form gives no answer-type cue
**RESOLVED 2026-10-06** — Variant A adopted:
`The statement "<stem>" is ___.` Applied to the two templates in
`src/semintegrity/probes/surface.py`; record in `docs/PROBE_REWRITE_LOG.md`.
**Was: BLOCKING — the CANON go/no-go gate** · `PROBE AUTHORING`

The frame `"<assertion>: ___"` does not signal that a YES/NO is wanted. On pilot
jobs 11969 and 12095, **6 of the 28** polar-cloze probes (21.4%) came back as a
bare noun from the prompt, and the echoed token was the assertion's *subject*
rather than the one adjacent to the blank (`"...its atomic number is 79: ___"`
→ `Au`). Colon-plus-blank reads as a `label: value` gloss.

The declarative polar frame already carried `"— YES or NO?"` and the
interrogative frame cues a yes/no by its syntax; only cloze had no cue, so the
Track A instruction ("if the expected answer is yes or no, reply with exactly
YES or NO") could not fire.

Three routes were considered and two rejected: strengthening the Track A
instruction would differentially help the cloze probes and so **confound the
syntax factor** §4.4.2 exists to control; dropping polar cloze would break
ADR-0003's exact class-level balance. Accepting a failing gate is not available —
§4.12 fixes the ≥95% criterion in advance and states that failure "triggers
pipeline revision before the full benchmark is authored".

**This is probe *wording*, not the factor lattice.** §4.4.1 defines equivalence
on the formal representation, which excludes probe text; the rewrite changed
**0 of 96** formal representations. Earlier notes describing it as touching
ADR-0003's lattice overstated it.

**VERIFIED EMPIRICALLY 2026-10-07.** Pilot run3 on the rewritten probes returned
**0/96 INVALID = 100.00%**, against the unchanged ≥95% gate: all six previous
INVALIDs resolved and no new ones appeared. The result is frozen in
`docs/RESULTS_STATUS.md`, and the canonicaliser, threshold and wording are not to
be modified on the strength of it.

**Side effect on a still-open question.** With 0 INVALID, no polar probe remains
whose reply names an answer-space member, so the entity/date fall-through
question has no live instance in this dataset. It remains OPEN and undecided —
this run removed the evidence rather than supplying it.

---

## Q25 — §4.3's "second authoritative source" has no approved provider list and no independence criterion
**BLOCKING — benchmark authoring (promotion of 81 of 132 constraints)** · `METHODOLOGY`

§4.3 requires that "all historical and temporal facts are corroborated against a
second authoritative source". The **mechanism is implemented and enforced** —
`src/semintegrity/kb/corroboration.py`, `CorroboratingSource` in the constraint
schema, the gate in `design_validator._corroboration`, freeze verification in
`validate_corroboration_freeze` — and
`configs/benchmark/corroboration_policy.yaml` is **deliberately unconfigured**:
`approved_independent_providers: []`, `independence_criterion: null`,
`status: NOT_CONFIGURED`. Until both are set, every corroboration is rejected and
the system reports *"corroboration mechanism implemented; approved independent
source policy not yet configured"*. **That is the correct state, not a bug.**

What has to be decided is methodology, in three parts:

1. **the independence criterion** — what makes a source independent of Wikidata;
2. **the approved provider list** — which providers count, per domain;
3. **whether a Wikidata reference / P248 "stated in" value may ever count.**

**Scope, from the current manifest** (`data/benchmark/authoring_manifest.json`):
**81 of 132** rows carry `corroboration_required` — 72 test, 9 dev; history 28,
science_technology 16, biology 13, geography 12, public_office 12; axis 4 (24)
and axis 6 (20) dominate. Those 81 cells are **30 distinct fact families**, so
provider choice is a 30-way problem.

**Analysis prepared, decision not taken:**
`docs/CORROBORATION_SOURCE_FEASIBILITY.md` — the independence principle applied
to 15 candidate provider categories (ten-point analysis each), a family-by-family
coverage map of all 81 cells, and proposed ADR-0019 text. Its headline findings:

- 43 of the 81 are reachable at **Tier 1** (first-party instruments, standards
  bodies, official registries); 38 at Tier 2; **none unreachable**;
- **26 cells unblock on two providers** (`national-legislation`, `crossref`) with
  **no bespoke adapter at all** — the provider list need not be complete to be
  useful;
- **only 2 provider-specific adapters** look genuinely necessary (`iucn` token,
  UN Treaty Collection retrieval); one generic throttled-GET fetcher covers 11 of
  15 candidates;
- the real ambiguity in "independent" is **directional**: a provider Wikidata
  *bot-imported from* is admissible under the stated principle yet agrees with
  Wikidata necessarily, giving a PASS with no error-detection power.
  Recommended: admit on non-derivation, but **disclose** `same-witness` vs
  `independent-witness` per source;
- `CorroborationArtifact.content` is `str`, so **PDF-first providers force an
  encoding decision before the first adapter is written** (recommended: base64
  the original bytes);
- `duplicate_groups` treats a shared `url_host` as the same source and the
  validator makes a duplicate an **error at any status**, so a **C2** conjunction
  cannot cite two documents from one official host — it needs one document
  stating both facts, or two providers;
- **16 history cells** (end of a classical empire · capital of a historical
  polity · province within an empire · longest reign) are the residual risk: only
  a scholarly reference work states the proposition, which raises a **paywall
  reproducibility** question;
- the 81 can be **authored to DRAFT now** — absent corroboration is a warning at
  DRAFT and an error only at EVIDENCE_VERIFIED or above, so retrieval is a
  separable batch, not a precondition for authoring;
- **no entity in the 81 is fixed yet** (the manifest is allocation only), so
  provider feasibility can steer instance selection at zero design cost. Changing
  a *theme* would need the approved coverage matrix revisited.

**Not verified:** every claim in that document about an external provider's URL
stability, authentication or media type is prior knowledge, marked
`[UNVERIFIED]`, and needs the one-GET-per-provider retrieval probe in its §8
(`scripts/kb/probe_corroboration_sources.py`, **NOT WRITTEN**) before any
provider is approved.

**Nothing has been configured, no adapter has been written, and no constraint has
been promoted.** The decision belongs to the researcher and then to ADR-0019.

### Q25 — UPDATE 2026-10-07: probed, reassessed, and a draft decision prepared

**Still BLOCKING and still undecided.** `corroboration_policy.yaml` remains
`NOT_CONFIGURED`. What has changed is that the provider analysis is now
empirical rather than recalled.

**98 HTTP probes** were run (probe-only instrumentation, kept out of `src/`;
one request per host per 1.2 s; no bot challenge solved or circumvented). They
**contradicted four load-bearing claims** of the first analysis:

| was claimed | is false |
|---|---|
| `legislation.gov.uk` is the highest-value provider (14 cells), plain GET sufficient | AWS WAF challenge — `202`, `Content-Length: 0`, `x-amzn-waf-action: challenge` on six requests including `/robots.txt`. Légifrance `403`, Planalto times out, EUR-Lex WAF-challenged |
| the UN Treaty Collection is the one unavoidable adapter | **reversed** — plain GET of a path-addressable XML, **byte-identical across three GETs over 35 minutes**; the best artefact in the whole catalogue, and no adapter |
| IUCN needs "a small adapter" | needs an **issued token**; the website returns `200` with a Cloudflare interstitial; API v3 is retired |
| scholarly reference works are a paywall caveat | `403` **before** any authentication, both via `doi.org` and directly |

**Three findings that change the design, not just the provider list:**
1. **HTTP 200 is not evidence of retrieval** — seven hosts return `200` with a
   challenge body or an empty JS shell. A fetcher must detect these or
   interstitials get frozen as §4.3 evidence.
2. **`content_hash` is not a re-retrieval identifier** — 12 of 41 artefacts
   double-fetched returned different bytes (per-response nonce or live content).
   Freeze verification still works; "re-fetch and compare" does not.
3. **Index endpoints are not artefacts** — NTRS search, TNA Discovery and S3
   listings are fetchable, unstable, and legitimate only for discovery.

**Recomputed coverage of the 81 cells** (superseding "43 T1 / 38 T2 / 0
unreachable", which counted provider categories rather than retrievable
artefacts):

| | cells |
|---|---|
| **VERIFIED** — artefact fetched, hash-stable, real document returned | **34** |
| **COVERABLE** — provider verified, this instance's document not yet identified | **42** |
| **GAP** — no verified provider route | **5** |

Proposition-level support remains **unknown for all 81** and stays unknown until
the cells are authored.

**Smallest defensible provider set: 8** — `crossref`, `un-treaties`, `govinfo`,
`nasa`, `standards-body`, `official-gazette`, `taxonomic-authority`,
`national-archives`. All plain unauthenticated GET, all hash-stable, **zero
credentials, zero provider-specific adapters**.

**The allocation survives unchanged** — 120 test · 12 dev · 132 new · 81
corroboration-required, with ADR-0017, ADR-0018, CANON, K and the factor lattice
untouched. Every repair is instance selection, which is free because the
manifest holds no entities. One already-authored DRAFT cell is affected
(`K-C4-GEO-11`, Brazil, all Brazilian statute hosts blocked).

**The one place design and sourcing actually collide:** *"the end of a classical
empire"* (4 cells). No first-party instrument, no verified institutional record,
scholarly route `403`, tertiary route hash-unstable. **Instance selection cannot
fix it** — it needs a researcher choice between a recorded tertiary exception, an
open-access scholarly publication, or revisiting the theme in the approved
coverage matrix. *"Coastal versus landlocked states"* (1 cell) is probably
instance-fixable via a treaty, unverified.

**Recommended on the methodology question (D-1):** admit on **directional
non-derivation** and require every source to declare `independent-witness` or
`same-witness` — strict mutual non-derivation would exclude 24 of the 81 cells
and is unsatisfiable; directional-only would let agreement pass as confirmation.
Expected split: ≈52 independent-witness, ≈24 same-witness. Convention only; no
code change needed to proceed.

**Recommended on D-3 (P248):** a pointer, never evidence; the named document may
corroborate only after independent retrieval from the provider's own host, and
is recorded as `same-witness`.

**Full analysis:** `docs/CORROBORATION_SOURCE_FEASIBILITY.md` **Revision 2**,
including the probe record (§2), the 30-family cell map (§6) and the corrections
list (§12). **Draft decision:**
`docs/decisions/ADR-0019-corroboration-source-policy.md`, marked **DRAFT — NOT
APPROVED**, with proposed `corroboration_policy.yaml` values presented in its
§11 and **not written to the file**.

### Q25 — UPDATE 2026-10-07 (2): witness rule tightened by the researcher

**Researcher correction, now reflected throughout:** `same-witness` **does not
satisfy §4.3** and must not permit promotion past the corroboration gate.
Only `independent-witness` — a source the Wikidata claim does **not** cite —
counts as the second authoritative source. `same-witness` may be recorded as
descriptive provenance.

**Two things this changed in the proposal, beyond the wording:**

1. **Witness status is a property of the (claim, source) pair, not of the
   provider.** The earlier provider-level estimate ("≈24 same-witness / ≈52
   independent-witness") was adequate while the classification was reporting
   metadata and is **inadequate now that it gates promotion**. It is withdrawn
   and not replaced: the split is not knowable before the instances are chosen.
2. **A validator rule is now required.** A convention cannot block a promotion.
   The determination is mechanical — a Wikidata claim's references are already
   in the entity JSON the frozen cache stores — so `_corroboration` would
   compute it rather than trust `note`. ≈40 lines plus tests, **not
   implemented**.

**Wikidata reference census** (probe-only, 16 statements over 9 entities
representing the affected families; indicative, not conclusive):
**11 of 16 statements (69%) carry no references at all** — including
Czechoslovakia's dissolution date, Brazil's capital statements (the authored
`K-C4-GEO-11`), the Byzantine Empire's end date and uranium's atomic mass. Where
Wikidata cites nobody, every admissible provider is `independent-witness`, so
the tightened rule mostly does not bind. Taxonomy claims cite **ITIS** and
**Mammal Species of the World (3rd ed.)**, not WoRMS or Catalogue of Life, so
the proposed `taxonomic-authority` provider is **safer** than assumed.
**One confirmed conflict:** metre's `P31` cites the SI Brochure, so BIPM is
`same-witness` there — instance-fixable.

**Recomputed coverage** (retrieval unchanged; a second, per-cell gate added):
33 retrieval-verified with no witness conflict · 1 with a confirmed conflict ·
42 coverable, witness to be determined at authoring · 5 gap.

**Blocked-host re-probe: nothing changed.** All eleven blocked hosts returned
identical results, so the blocks are site policy rather than a transient;
`doaks.org` was newly found to be WAF-challenged too. The **cluster login-node
re-probe has not been run** — per ADR-0010 the researcher runs it, and the exact
`curl` command is in `docs/CORROBORATION_SOURCE_FEASIBILITY.md` §14.6. A
different result there would mean only that the same plain GET succeeds from
that network.

**The four classical-empire cells remain OPEN and are the researcher's
decision.** Witness status is not the obstacle — the Byzantine Empire's `P576`
is unreferenced. Retrieval and proposition support are. Option A was **probed
and failed**: `nomisma.org`'s Byzantine Empire record is hash-stable and serves
RDF/JSON-LD, but states **no terminal date** and declares `skos:exactMatch` to
`wikidata.org/entity/Q12544`, DBpedia and Freebase — a Wikimedia-ecosystem
concordance. Pleiades, papyri.info and Trismegistos date places, documents and
coins, not empire ends. Options B (open-access scholarship; Cambridge, Brill,
De Gruyter, OpenEdition, Persée, Zenodo, JSTOR all answered 200 at root,
document level unverified), C (successor-polity archive; speculative), D (relabel
the theme, which touches the matrix table and the manifest's `theme` string and
**nothing structural**, then instantiate on the Ottoman Empire via `un-treaties`
or Austria-Hungary via ALEX) and E (tertiary exception; **not proposed** —
Britannica is tertiary *and* hash-unstable) are set out in §14.5 with two
**conflicting** rankings: cleanest evidence favours D, preserving approved
documents favours B. **Not decided here.** If none is approved, the benchmark
reports **77 of 81 corroborated** and §4.3 is not weakened to close the gap.

**Draft decision:** `docs/decisions/ADR-0019-corroboration-source-policy.md`,
**Revision 2, still DRAFT — NOT APPROVED**, and deliberately **not** added to
the decisions index. Proposed `corroboration_policy.yaml` values are in its §11
and have **not** been written to the file.

### Q25 — RESOLVED 2026-10-07 (provider policy) · the four-cell gap stays OPEN

**ADR-0019 APPROVED and IMPLEMENTED 2026-10-07.**
`docs/decisions/ADR-0019-corroboration-source-policy.md` is now the record, and
`configs/benchmark/corroboration_policy.yaml` reads `status: CONFIGURED` with
eight approved providers. The readiness audit's corroboration check moved
**BLOCKED → PASS**.

**Approved:** the corrected independence rule (`independent-witness` alone
satisfies §4.3; `same-witness` is descriptive provenance and cannot permit
promotion; witness status is a property of the `(claim, source)` pair, enforced
mechanically by a validator rule rather than recorded in a note) · the
**eight-provider** core set `crossref`, `un-treaties`, `govinfo`, `nasa`,
`standards-body`, `official-gazette`, `taxonomic-authority`,
`national-archives` · the exclusions, including the Wikimedia-ecosystem
concordances `nomisma`, `pleiades`, `trismegistos`, `papyri-info` alongside
`gbif` and `openalex` · the P248 pointer rule · the frozen-artefact suitability
rule. **The three optional providers were deliberately NOT approved.**

**STILL OPEN — the four classical-empire cells (`F-HIS-16`).** A limited final
check of options B and C was run on 2026-10-07 and **neither yielded a
qualifying artefact**: the DOAJ API returns 118 open-access articles matching
*byzantine AND 1453* and the publisher hosts answer, but **no matched document
states the proposition**; the Turkish state archives answer `200` but an Ottoman
archive does not assert when the Byzantine Empire ended. So the gap is
**retained and recorded** in the policy's `recorded_gaps`, the benchmark will
report **77 of 81 corroborated**, and §4.3 is not weakened. **No tertiary
exception exists.**

**Option D (relabelling the theme) is an UNRESOLVED METHODOLOGICAL CHOICE, not a
rejected one.** It remains the only route to a first-party instrument for those
cells, it would need a coverage-matrix revision, and it was **not** adopted —
making a coverage number look complete is not a reason to change an approved
document. It must not be made silently.

---

## Q26 — ADR-0019's witness test matches a reference URL's HOST, but five of the eight approved providers span several hosts
**BLOCKING — promotion of corroboration-required constraints** · `METHODOLOGY`
**Found 2026-10-07 while authoring, by running the approved implementation against live data. Not decided.**

ADR-0019 §2 defines `same-witness` as the Wikidata claim citing "this provider or
source (a P248 "stated in" value, or a reference URL **on the same host**)".
`semintegrity.kb.witness` implements exactly that. The empirical case that
exposes the gap:

- `K-C4-SCI-13` rests on Wikidata's `Q533336 P361 → Q2025902` (Unity is part of
  the US Orbital Segment, P580 1998-12-06). That statement carries **one
  reference: a reference URL on host `www.nasa.gov`**.
- The natural corroborating artefact is NASA's NSSDCA master-catalogue record
  for Unity (COSPAR 1998-069F), on host **`nssdc.gsfc.nasa.gov`** — fetched
  live, 7,521 bytes, double-fetched hash-stable, frozen and verified.
- Both are the approved provider **`nasa`**. The hosts differ, so the classifier
  returns **`independent-witness`** — while the honest reading is that the claim
  already cites this provider, which ADR-0019 says must **not** satisfy §4.3.

**This is not a coding error; it is the approved wording applied literally.** It
matters because most approved providers are deliberately multi-host categories:

| provider | hosts seen in the feasibility study |
|---|---|
| `nasa` | `nssdc.gsfc.nasa.gov`, `ntrs.nasa.gov`, `www.nasa.gov` |
| `official-gazette` | `gesetze-im-internet.de`, `psp.cz`, `alex.onb.ac.at` |
| `taxonomic-authority` | `marinespecies.org`, `api.checklistbank.org`, `zoobank.org` |
| `standards-body` | `bipm.org`, `ciaaw.org` |
| `crossref` | requested `doi.org`, resolved `api.crossref.org` |

So **host equality under-detects `same-witness` for 5 of the 8 providers**, in
the direction that wrongly permits promotion.

**Options (none adopted):**
- **(a) Keep host equality as approved.** No change; the under-detection becomes
  a stated limitation of every `independent-witness` verdict. Cheapest, weakest.
- **(b) Declare a `provider_hosts` map in the policy** and match a reference URL
  against the hosts of the candidate's provider. Mechanical, auditable, and the
  same shape as the already-approved `wikidata_stated_in_qids` map: explicitly
  populated by a human, empty until then, erring toward refusal. **Recommended**,
  and it needs one policy key plus a few lines in the classifier.
- **(c) Match on registrable domain** (`nasa.gov`). Catches the NASA case and
  nothing else: `official-gazette` spans unrelated domains, and it could
  over-match an unrelated subdomain of a large host.
- **(d) Have the author declare the class and let the classifier only veto.**
  Reintroduces the hand-written note that ADR-0019 deliberately removed.

**Current effect, measured:** of the 3 corroboration-required constraints
authored so far, `K-C4-SCI-13` is directly affected. No corroborating source has
been attached to any constraint, so nothing has been promoted on the strength of
an under-detected `same-witness` — the cell is DRAFT and its `ambiguity_notes`
records why. **No rule was invented and the policy was not edited.**

### Q26 — RESOLVED 2026-10-07: witness identity is decided at provider level

**Approved and implemented.** ADR-0019 §2.1 carries the amendment; the policy
gains `witness_classification.provider_hosts`.

The rule: if the Wikidata claim cites a source belonging to the **same approved
provider** as the candidate, the classification is `same-witness` — **even when
the cited host and the corroborating artefact are different authoritative hosts
of that provider**. A different approved provider may still be an
`independent-witness`. If the provider/host relationship cannot be established
from the explicit map — for the cited host **or** for the source's own host — the
verdict is `undetermined`. Neither `same-witness` nor `undetermined` satisfies
§4.3. **Ownership is never inferred from domain similarity**; only an explicit
entry establishes it.

`provider_hosts` covers all 8 approved providers and 15 hosts, every one
retrieved in the feasibility study (the one exception, `www.nasa.gov`, is NASA's
primary host and is the reference host in the Q26 case itself). No optional
provider was added. Listing a host can only make the classifier more likely to
refuse.

**Verified on live data, not only in tests:** the real case
(`Q533336 P361 → Q2025902` citing `www.nasa.gov`, corroborated from
`nssdc.gsfc.nasa.gov`) now returns **`same-witness`, qualifies=False**, where it
previously returned `independent-witness`. An unreferenced claim
(`Q155 P36`) still correctly returns `independent-witness`.

9 focused tests cover: same provider/same host · **same provider/different
declared host (the NASA case, reproduced exactly)** · a different approved
provider staying independent · an unmapped cited host → undetermined · three
lookalike domains (`nasa.gov.example.net`, `fake-nasa.gov`,
`sub.nssdc.gsfc.nasa.gov`) owning no provider · a source from an undeclared host
→ undetermined · a provider with no declared hosts → undetermined ·
`same-witness` still blocking the promotion gate · and the shipped policy mapping
exactly the 8 approved providers with no suffix matching.

**`K-C4-SCI-13` remains DRAFT** and is now blocked for the right reason, stated
by the classifier rather than by a note.

---

## Q27 — The approved provider-host set cannot reach the one fact I tried hardest to corroborate
**BLOCKING — promotion of corroboration-required cells** · `METHODOLOGY`
**Found 2026-10-07 by attempting a real corroboration, not by reasoning about one. Not decided.**

`F-GEO-16` ("the dissolution of a federal state") was chosen as the first
corroboration target because everything lined up: Wikidata's
`Q33946 P576 = +1992-12-31` carries **zero references**, so any approved
provider would be an `independent-witness` under ADR-0019 §2 as amended by Q26,
and the instance is the canonical one with an approved provider
(`official-gazette`) and a verified host (`www.psp.cz`).

**It still could not be corroborated.** Two approved-provider artefacts were
fetched and inspected:

| artefact | host | declared? | what it states |
|---|---|---|---|
| Sbírka zákonů entry for Constitutional Act 542/1992 | `www.psp.cz` | **yes** | the citation, the title *"Ústavní zákon o zániku České a Slovenské Federativní Republiky"*, gazette issue 110, and the act's **effective date, 8 December 1992**. **Not the dissolution date.** |
| MTDSG status page, Chapter IV-4 (ICCPR), 1,166,562 B, hash-stable | `treaties.un.org` | **yes** | the succession of the Czech Republic **"1 January 1993"**. **Not 31 December 1992.** |

The act's **text** — which does state that the CSFR ceases to exist on 31
December 1992 — is linked from the gazette entry but hosted on
**`aplikace.mvcr.cz`** (the Ministry of the Interior's Sbírka archive) and
**`e-sbirka.cz`** (the official electronic collection). **Neither is declared in
`provider_hosts`**, and Q26 rule 6 forbids inferring ownership, so a source from
either is `undetermined` and cannot promote.

This is the failure mode the feasibility study named as the largest substantive
risk — **proposition mismatch** — arriving on the first real attempt. A catalogue
entry about an act is not the act. A succession date one day later is not the
dissolution date. Taking either would have produced a PASS on the wrong
proposition.

**Options (none taken):**
- **(a) Extend `official-gazette`'s declared hosts** to `aplikace.mvcr.cz` and/or
  `e-sbirka.cz`. Both are Czech state publishers of the Sbírka, so the
  substantive case is strong — but this is a **provider-membership** decision the
  researcher reserved, neither host was in the feasibility research, and neither
  has been probed for fetchability, hash-stability or charset. **Recommended, as
  a scoped amendment with those three probes run first.**
- **(b) Re-instantiate the family** on a dissolution whose date a declared host
  states. Keeps the policy untouched; costs one instance and no structure.
- **(c) Re-word the cell** to the fact a declared host does state (the Czech
  Republic's inception on 1 January 1993). **Not recommended** — it changes which
  fact the cell tests in order to make a source fit, which is the wrong direction
  of fit.
- **(d) Leave the four cells DRAFT.** What is in effect now.

**Scope of the consequence.** This is not peculiar to Czechoslovakia. For a
first-party legal instrument the pattern is general: the approved host often
publishes the *catalogue record*, while the instrument's text lives on a sibling
state host. The same question will recur across the `official-gazette`,
`govinfo` and `national-archives` cells — **up to 24 of the 81** by family count.
Deciding it once, as a host-verification procedure rather than per cell, is the
cheap path.

**Not affected:** the 36 constraints already at EVIDENCE_VERIFIED need no second
source, and nothing has been promoted on a mismatched proposition.

### Q27 — ANALYSIS 2026-10-07: recommendation is **A** (change nothing), on evidence

**Nothing was implemented. No host was added, no provider was created, no policy
or ADR was edited.**

#### What Q27 actually is

Three concepts that ADR-0019 treats as one:

| | concept | decided by | risk of listing a host |
|---|---|---|---|
| **A** | **provider identity** — is this host *the provider*, for self-citation detection? | `witness_classification.provider_hosts` | **conservative**: more hosts → more `same-witness` → more refusals. Under-listing is the dangerous direction |
| **B** | **artefact authority and proposition support** — does this document come from an approved authority, and does it *state the fact*? | provider name only, plus a human's `fact_supported` | **permissive**: a listed host asserts "artefacts here count as this approved authority". Over-listing is the dangerous direction |
| **C** | **witness independence** — is this source independent *of this claim*? | the classifier, over A | — |

**ADR-0019 does conflate A and B, and here is the mechanism.** Admissibility is
enforced by provider **name** alone: `provider_hosts` appears nowhere in
`kb/corroboration.py` or `kb/fetchers.py`, only in `kb/witness.py`. But because
an undeclared host yields `undetermined`, and `undetermined` blocks promotion,
the identity map (A) in practice gates qualification and therefore promotion —
so **one list is doing two jobs whose risk asymmetries point in opposite
directions**. A single edit to it is simultaneously a safe tightening (A) and a
consequential broadening (B). That is Q27, stated exactly.

Separately, §3's approval table justified each *provider* with host-specific
artefact evidence ("verified artefact"), which is how the two got entangled in
the first place: the institution was approved on the strength of particular
hosts' behaviour.

#### Narrow investigation — 3 requests, no campaign

**The Q27 pattern is not general to document publishers.** Of the declared
hosts, these serve the **instrument itself**: `www.govinfo.gov` (Federal
Register PDF), `www.gesetze-im-internet.de` (the Grundgesetz text),
`www.archives.gov` (the Declaration transcript), `treaties.un.org` (MTDSG XML
and chapter PDFs). Only inside `official-gazette` is there a catalogue problem,
and it affects **two of its three hosts**:

| host | probed | what it serves |
|---|---|---|
| `www.gesetze-im-internet.de` | earlier | **instrument** (305,445 B, contains "Artikel 1") |
| `www.psp.cz` | earlier + now | **catalogue record** — citation, title, gazette issue, effective date; text only via off-host links |
| `alex.onb.ac.at` | **now** | 2,558 B navigation page, no "Gesetz"/"1867" — **catalogue** |

**And option B is not viable on the evidence.** Both candidate sibling hosts were
probed:

| candidate | result |
|---|---|
| `aplikace.mvcr.cz` (MoI Sbírka PDF, the link the gazette page itself advertises) | **HTTP 404** |
| `e-sbirka.cz` (official e-Collection) | **200, 1,039 bytes, a JS shell** — contains neither "542" nor "zánik" |

So adding them would broaden a provider's meaning **and buy nothing**: one is
dead, the other serves no text.

#### Why not C either

`www.psp.cz` is the **Chamber of Deputies** — the legislature, running a
reproduction service. `aplikace.mvcr.cz` / `e-sbirka.cz` are the **Ministry of
the Interior** — the statutory publisher. They are *different institutions*
reproducing *the same instrument*. Making the MoI a separate approved provider
would therefore mean that a Wikidata claim citing `psp.cz`, corroborated from
`mvcr.cz`, classifies as **`independent-witness`** — two providers — when the
two are the same text twice, with no error-detection power. That is the Q26
failure mode re-created by splitting instead of by under-listing, and it
contradicts ADR-0019's own `duplicate_detection` note, which already says a
"mirror on another domain" is "a human-review matter and is **NOT** silently
accepted as independent".

**The policy as written already covers this case — by routing it to human
review, not by host arithmetic.** Option B would convert a human-review matter
into a mechanical pass; option C would convert a reprint into two independent
witnesses. **A is the only option that keeps ADR-0019's semantics.**

D ("same institution") and E (government-domain inference) are rejected as
proposed: both re-admit exactly the inference Q26 rule 6 forbids, and neither is
auditable. The Czech case shows D would also be *wrong on the facts* — the
hosts are not the same institution.

#### Measured exposure

| | cells |
|---|---|
| corroboration-required, total | 81 |
| planned on a document-publisher provider | 31 (`govinfo` 15, `official-gazette` 12, `national-archives` 4) |
| of those, on a provider whose declared host serves instruments (`govinfo`, `archives.gov`) | 19 — **not exposed** |
| **genuinely exposed: the `official-gazette` families** | **12** (`F-GEO-16` 4, `F-HIS-11` 4, `F-HIS-13` 4) |

**And the exposure is per instance, not per family.** Routing those families
through a German instance reaches `gesetze-im-internet.de`, which serves the
instrument on a declared host. So the 12 are addressable by instance selection —
the lever that is still free — without touching the policy.

#### Sub-finding, reported not fixed

The 1,039-byte `e-sbirka.cz` shell **passed** the suitability gate's
`min_document_bytes: 512` and was refused only by the propositional check a human
performs. The threshold is too low for a JS shell. Recommended, and **not
implemented** because it is an approved policy value: raise it for `text/html`,
or add a content-word test alongside the byte count.

#### Consequence for authoring

The safety property holds and was re-verified against the shipped policy:
`www.psp.cz → official-gazette`, while `aplikace.mvcr.cz`, `e-sbirka.cz`,
`psp.cz` and `mvcr.cz` all → **None**, so no suffix or similarity inference
occurs and an undeclared host stays `undetermined`. The four `F-GEO-16` cells
and the other three DRAFT corroboration cells remain DRAFT.

### Q27 — RESOLVED 2026-10-08: Option A accepted, nothing broadened

**Decision: keep the existing 8-provider set and the existing `provider_hosts`
mapping unchanged.** Unmapped hosts remain `undetermined`; same-provider sources
remain `same-witness`; different institutions reproducing the same instrument
are not automatically independent. The **12 exposed cells are an
authoring/instance-selection problem, not a policy problem**, and the four
classical-empire gaps are unchanged.

No provider was created, no sibling host was added, and the independence rule is
untouched. ADR-0019 §2.2 carries the approved **documentation-only**
clarification that `provider_hosts` has two uses — identifying provider
ownership for witness classification (where listing a host is conservative), and
marking the explicit boundary of approved provider-host identity (where listing
a host is permissive) — so that a future edit is made with the right risk
asymmetry in view.

**The one engineering change authorised by Q27 is done** (see below): the
HTML-shell hole in the suitability gate is closed.

---

## Q28 — Is a corroborating source classified against the claim it corroborates, or against the constraint's whole gold basis?
**BLOCKING — promotion of multi-claim corroboration-required cells** · `METHODOLOGY`
**Found 2026-10-08 by completing a corroboration chain and discovering it still could not be attached. Not decided; the implementation was NOT relaxed.**

ADR-0019 §2 says a source is classified "against **the specific Wikidata claim**
it is offered for" — singular — and `CorroboratingSource.fact_supported` records
"the exact proposition this source corroborates". The implementation is
**stricter**: `WitnessClassifier.classify` takes the strictest verdict over
**every** `supports_gold` Wikidata claim of the constraint, on the documented
reasoning that "a source offered for a constraint is offered for that
constraint's whole gold basis". That choice was mine, and it is now load-bearing.

**The case that exposes it — a chain that passes every other test:**

| step | result |
|---|---|
| proposition | "Watson and Crick's structure paper was published on 25 April 1953" |
| Wikidata claim | `Q1895685 P577 = +1953-04-25`, **zero references** → clean |
| provider | `crossref` (approved), host `api.crossref.org` (declared) |
| artefact | retrieved live, 4,481 B JSON, passed the suitability gate, double-fetched, hash `7f788c76e6d1c616` |
| **proposition support** | `published`, `published-print` and `issued` all = `[[1953, 4, 25]]` — stated in **machine-readable fields**, not prose |
| witness, against that claim alone | **`independent-witness`** |
| witness, as implemented (over all claims) | **`undetermined`** — the constraint's *other* event, `Q22122440 P577`, cites `eutils.ncbi.nlm.nih.gov`, which maps to no approved provider |

So the only fully verified corroboration chain in the project is blocked by a
**sibling** claim it does not corroborate.

**Options (none taken):**
- **(a) Per-claim classification, matching the ADR's wording.** A source is
  classified against the claim named in `fact_supported`. Unblocks this case and,
  by the same logic, any multi-event cell where one event is clean. **But it
  loosens a gate**, and a constraint could then promote while part of its gold
  basis has no independent corroboration at all — which for a C2 conjunction is
  precisely the weakness §4.3 is meant to close.
- **(b) Keep the stricter whole-basis rule** (current behaviour) and accept that
  multi-event cells need *every* event's claim witness-clean. Safest; it is why
  axis-4 and axis-6 cells are hard to corroborate.
- **(c) Per-claim classification plus a coverage requirement**: a constraint
  promotes only when every `supports_gold` claim is covered by some qualifying
  source. Faithful to the ADR's wording *and* to §4.3's purpose, at the cost of
  needing one artefact per event — which for C2 collides with the same-host
  duplicate rule when both artefacts come from one provider.

**Recommended: (c)**, because it is the only option that neither weakens the gate
nor contradicts the ADR's own singular wording. It needs one validator change and
no policy change. **Not implemented.**

**Measured consequence:** of the 16 corroboration-required cells authored, the
single-claim ones are unaffected; the multi-event axis-4 cells (9 authored) are
all blocked this way or by an unmapped citation.

---

## Q29 — Six C4 cells have no machine-checkable date in Wikidata, and the lattice is valid only at 120

**Status: OPEN — AWAITING RESEARCHER DECISION.** Raised 2026-10-08, after the
ADR-0020/0021/0022 batch took authoring from 106 to 126 of 132.

### The structural fact that makes this a decision and not a backlog item

ADR-0002's lattice is **saturated**: 6 schemas × 5 domains × 4 classes = 120, and
`schema_domain_crossing` holds every (schema, domain) cell to at most one
constraint. So `total_count`, `class_balance`, `domain_class_balance`,
`family_completeness` and `schema_balance` are satisfiable at **exactly one test
size, 120** — there is no valid benchmark at 115, and no "maximum defensible
count" below 120. Measured on the current records:

```
[FAIL] total_count            115 constraints (expected 120)
[FAIL] class_balance          C4=25
[FAIL] domain_class_balance   (geography,C4)=5 (biology,C4)=3 (science_technology,C4)=5
[FAIL] family_completeness    F-BIO-11, F-BIO-12, F-BIO-13, F-GEO-15, F-SCI-11 = [C1,C2,C3]
[FAIL] schema_balance         S-C4-01=3 S-C4-02=4 S-C4-03=4 S-C4-05=4
```

An Axis-5 or C4 cell also **cannot be swapped for a cell on another axis**: the
axis is a property of the schema, and `schema_balance` requires exactly 5
instances of each schema, one per domain. The only authoring freedom inside a
cell is which fact instantiates its theme.

### The six cells, and why each is blocked

All six are C4. None is blocked by ADR-0020's evidence-route question — that is
resolved, and the other 20 cells in this batch were authored under it.

| cell | axis / answer | why no date exists |
|---|---|---|
| `K-C4-BIO-11` | 1 / entity | type-species designation; taxon carries no `P574`/`P835` |
| `K-C4-BIO-12` | 2 / boolean | class membership; `Chiroptera` has only `P580 = -52000000` |
| `K-C4-BIO-13` | 3 / entity | genus-in-family; `Panthera` has only `P580 = -5950000` |
| `K-C4-BIO-03` (dev) | 3 / entity | same theme as `F-BIO-13`; `Felis` has `-6200000` / `-3000000` |
| `K-C4-GEO-15` | 5 / boolean | `Q7296` (Kilimanjaro) carries **no dated statement at all** — only P31, P30, P610, P2044. No `P1427` first ascent |
| `K-C4-SCI-11` | 1 / entity | the SI redefinitions are undated in Wikidata: `kilogram` and `metre` have no date property, and the IPK has `P571` but **no `P576`** |

Two distinct causes, both verified rather than assumed:

1. **Deep time is unrepresentable.** The taxonomic cells' only dates are
   first-appearance dates of order −10⁶ to −10⁷. `parse_wikidata_time` returns
   `None` for them (Python `date` spans years 1–9999), so a check reads them as
   ABSENT. A test now pins that behaviour
   (`test_p585_deep_time_is_not_silently_accepted`).
2. **The fact has no date to read.** Kilimanjaro and the SI units are atemporal
   in Wikidata. The only P585-qualified statements on the blocked taxa and on
   Kilimanjaro are Wikimedia **curation** metadata — `on focus list of Wikimedia
   project`, `Baidu Tieba name`, `described by source`. Anchoring a gold
   proposition on those would make the constraint a fact about Wikidata's own
   editorial process, not about the subject, and was rejected on that ground.

`K-C4-SCI-11` additionally has a **degeneracy** problem: the one usable date is
the IPK's own `P571 = 1889`, which yields "the artefact adopted in 1889 as the
international prototype of the kilogram is ___" → *the International Prototype of
the Kilogram*. The answer is contained in the question. It was not authored,
because reaching 120 with a cell that cannot discriminate would buy the count at
the cost of the measurement.

### Options

**(a) Re-theme the five affected (axis, domain) cells in the Revision-4 matrix.**
Four of the six are the biology/C4 axis-1/2/3 themes plus the geography axis-5
theme — all intrinsically atemporal. Replacing those themes with ones whose facts
Wikidata dates would make all six authorable. **Cost:** this edits
`scripts/propose_coverage_matrix.py`, regenerates the matrix and the 132-row
manifest, and changes the approved Revision-4 coverage matrix —
`test_test_cells_are_exactly_the_matrix` pins the manifest to it. It is a
**design change**, which is why it is not taken here. The C1/C2/C3 cells of those
families are already authored and EVIDENCE_VERIFIED, so a re-theme would also
discard or re-author up to 15 good cells unless the new theme is chosen to keep
them.

**(b) Admit a second measure/date provenance for C4, as ADR-0022 did for axis-5
measures.** Taxonomic publication dates are available from an approved
`taxonomic-authority` provider even where Wikidata lacks `P574`, and the
BIPM/`standards-body` provider publishes the SI redefinition dates. This reuses
machinery that now exists and is verified working (5 frozen artefacts check out
against the store). **Cost:** a C4 cell's temporal anchor would no longer be
re-checkable from the Wikidata cache alone, and `gold_source` would need a
stated policy for the case where the primary source has no date at all. A real
extension of the ground-truth rule, so a researcher call.

**(c) Accept 126 and change the lattice.** Lower `design.yaml`'s counts so the
design is valid at what is authorable. **Cost:** this is the one option that
touches the confirmatory design. §4.3's 120 and the exactly-60/60 arms come from
the proposal; 115 breaks `domain_class_balance` in three domains and would make
the four-class contrast unbalanced. **Not recommended.**

**(d) Accept 126 as the authored state and leave the lattice failing.** Honest,
and it is the current recorded state — but the benchmark cannot be frozen or
scored while five lattice rules fail, so this is a holding position, not an
outcome.

**Recommended: (a)**, scoped to the four biology/C4 themes and the geography
axis-5 theme, with the replacement themes chosen so the already-verified
C1/C2/C3 cells of those five families survive. (b) is the fallback if the
Revision-4 matrix is to stay fixed. **Neither is implemented.**

### What is NOT in question

ADR-0020, ADR-0021 and ADR-0022 are approved and applied; 20 of the 26 formerly
blocked cells are authored under them, with 287/287 evidence checks passing,
19 frozen comparison universes and `dev_test_disjoint` passing. CANON, K=8, the
factor lattice, the pilot and every detector are untouched.

---

### Q29 — RESOLVED 2026-10-08: option (a), re-theme, carried out in two revisions

**Researcher decision: option (a) — re-theme the affected Revision-4 matrix
cells rather than weaken the C4 evidence methodology.** Done. The benchmark is
**132/132** and every lattice rule passes. No gate was weakened, no date
invented, no curation metadata used, and **not one authored C1/C2/C3 cell was
re-authored or discarded**.

#### Revision 5 — four cells

Each replacement is a **widening**, chosen so the family's existing
EVIDENCE_VERIFIED cells stay truthful instances of the new theme.

| axis | domain | was | now | C4 now anchored on |
|---|---|---|---|---|
| 1 | biology | the type species of a genus | the designated reference standard for a taxon | GRCh38 `P577` 2013-12-17 supersedes GRCh37 2009-02-27 |
| 1 | sci_tech | the SI base unit of a physical quantity | the designated standard for a physical quantity | International Prototype Metre `P571` 1879 → **`P576` 1960** |
| 2 | biology | vertebrate class membership | category membership of a vertebrate taxon | southern elephant seal NZTCS *nationally critical*, `P585` 2024 |
| 5 | geography | the highest summit of a continent | the highest summit of a named region | highest summit within the USSR; window closed by `Q15180 P576` 1991-12-26 |

Why each preserves its family: a type species **is** the nomenclatural
reference standard for a genus name; taxonomic class membership **is** category
membership; an SI base unit **is** a designated standard; a continent **is** a
named region.

#### Revision 6 — the fifth cell, axis 3 / biology

Revision 5 left this one unfilled, and the first analysis concluded it was
impossible. **That conclusion was too broad.** It rested on a true premise —
taxonomic `P171` carries no date qualifiers anywhere in Wikidata (re-verified
across Felidae, viruses, diseases, and taxa holding several competing `P171`
values) — but inferred a false one: that therefore no dated taxonomic
containment exists.

**It does, on the superseded placement rather than the current one.** Wikidata
records the **original combination** (`P1403`) as its own taxon item, whose
`P225` carries a **`P574` publication-year qualifier** and whose `P171` names
the **original** genus:

```
lion   Q140    P1403 -> Q15294488 "Felis leo"    P171 -> Felis Q228283   P574 1758
tiger  Q19939  P1403 -> Q41083521 "Felis tigris" P171 -> Felis Q228283   P574 1758
both   P171 -> Panthera Q127960 today
```

So the containing taxon genuinely **differs by date**, with an entity answer —
exactly axis 3's `in_at(E, ?x, t)`. Theme: **"genus within a family" → "a taxon
within a higher taxon"**. This widening makes the matrix *more* faithful to what
was already authored, not less: the dev family `F-BIO-03`'s C1 cell is
tiger → Panthera, a **species within a genus**, which the Revision-4 wording
never described.

**The transfer date is not recorded and is not invented.** `P574` dates the
publication of the *name*, not the move to *Panthera*, so both cells carry
`end: null` with `end_unknown: true` — the treatment `K-C4-HIS-12` already gives
a missing `P580` — and the claim says "originally described, in 1758" rather
than implying the placement itself was dated.

#### One new evidence reader

`claim_qualifier_time` reads **any** time-valued qualifier named by the check.
`P574` sits on `P225`, so no existing reader could see it. It generalises
`claim_interval_end` (P582) and `claim_point_in_time` (P585) instead of adding a
third per-property reader, and introduces **no new evidence requirement**
(ADR-0020). `TimeQualifiedClaim` now collects every time-valued qualifier, so a
future qualifier needs no new field. 5 tests, including that it fires on a wrong
year, that it selects on the statement's own value rather than reading a date off
a sibling value, and that a missing qualifier reads as ABSENT rather than as an
invented year.

#### Final state

132/132 · test 120/120 · dev 12/12 · 1,056/1,056 probes · **313/313 evidence
checks passed** · all 20 axis-5 universes frozen · every lattice rule PASS,
including `schema_domain_crossing` **fully crossed** for the first time ·
`sitelink_matching` p=0.409 · readiness **`[PASS] 120-constraint benchmark
authored`**.

**What Q29 does NOT resolve:** 81 constraints are `corroboration_required` and
**0** have a qualifying second source, so 81 remain DRAFT. That is the next
phase's work, not a construction defect — the mechanism is built, the policy is
configured, and 5 sources are already frozen and verified against the store.

---

## Q30 — Corroboration is reachable, but Q28's whole-gold-basis rule blocks it, and the propositional check is human

**Status: OPEN — AWAITING RESEARCHER DECISION.** Raised 2026-10-08 after the
first end-to-end §4.3 corroboration attempt. **No gate was weakened and no
unverified source was recorded.**

### What was established, by doing it

81 of 132 constraints are `corroboration_required` (28 history domain · 26 C4
temporal · 10 axis-4 · 9 date answer · 8 axis-6) and **0** have a qualifying
second source. One cell was taken end to end to find out why.

`K-C4-SCI-11` asserts that the International Prototype Metre defined the metre
until 1960. The obvious witness is the **BIPM**, the statutory authority for the
SI and an approved `standards-body` provider on an approved host.

1. **The artefact is retrievable and freezable.** The SI Brochure (9th ed.)
   fetched through `kb.fetchers.HttpDocumentFetcher`, 3,503,078 bytes,
   `content_hash 6385c4e1…`, frozen at snapshot `0fc0157c…`, and
   `CorroborationStore.verify` passes.
2. **It states the proposition verbatim.** Extracted with `pypdf` (214 pages,
   565,476 characters), Appendix 1 contains
   *"11e CGPM, 1960 : redéfinition du mètre au moyen de la radiation du krypton
   86"* and *"La définition du mètre en vigueur depuis 1889, fondée sur le
   Prototype international en platine iridié, **est abrogée**."*
3. **The dated claims cite nobody.** `Q1929537` `P571` and `P576` carry **zero
   references**, so under the policy an admissible source is an
   independent-witness for them.
4. **And yet it does not qualify.** Verdict: **`same-witness`** —
   *"the Wikidata claim Q11573 P31 cites Q19606873, which the policy records as
   provider 'standards-body'"*.

### Why, exactly

ADR-0019 classifies a source against the constraint's **whole gold basis**, and
a same-witness on **any** claim disqualifies it. `K-C4-SCI-11`'s basis includes a
third, incidental claim — metre (`Q11573`) `P31` → SI base unit — for which
Wikidata cites **`Q19606873` = the BIPM SI Brochule (8th edition)**, publisher
BIPM. So BIPM is cited for a claim the constraint happens to rest on, and is
therefore disqualified from corroborating the 1960 abrogation it is the world
authority for.

**This is Q28's consequence, now observed rather than predicted.** Under Q28's
recommended option (c) — promote when every `supports_gold` claim is covered by
*some* qualifying source — BIPM would qualify for the 1960 claim, and the
`P31` claim would need its own source. Its other citation, `Q26711930` =
**ISO 80000-1:2009** (publisher ISO), is not an approved provider.

### Two things fixed in passing (engineering, not methodology)

* **`wikidata_stated_in_qids` is now populated**, with
  `standards-body: [Q19606873]`. The policy explicitly sanctions this ("a
  researcher adds an entry here once, per observed 'stated in' item, after
  checking it"); the item was checked — `P123` publisher → `Q229478` (BIPM),
  `P953` → bipm.org. Mapping can only move a verdict from `undetermined` to
  `same-witness`, both of which fail to qualify, so it is strictly more
  informative and never more permissive.
* **A shape guard on that map.** Written inverted (`Q19606873: standards-body`)
  it silently iterated the provider string character by character, so
  `_known_stated_in()` returned `{'s','t','a','n','d',…}` and every real
  citation looked unmapped. A map that decides whether a source may corroborate
  a benchmark fact must fail loudly; it now does, with 4 tests.

### The second blocker: the propositional check is human

`frozen_artifact_suitability` checks retrievability, hash stability, charset and
document-vs-index. It does **not** check that the document states the
proposition — Q27 recorded that a 1,039-byte JS shell passed every mechanical
check "and was caught only by the human propositional check", and the policy
says "established mechanically where possible; anything subtler is human
review". Keyword extraction (now demonstrated) narrows a candidate to an exact
passage but does not establish that the passage asserts the gold proposition.

**So corroboration is genuinely coupled to the human phase**, which the
professor has placed last. That is a sequencing fact, not a weakened gate.

### Options

**(a) Resolve Q28 to per-claim classification (its own recommendation (c)).**
One validator change, no policy change. Makes BIPM qualify for the claim it
actually witnesses. Each remaining `supports_gold` claim then needs its own
qualifying source — which is the honest cost, and is what §4.3 arguably always
meant. **Recommended.**

**(b) Add ISO as an approved provider.** An ADR-0019 change. Unblocks the `P31`
claim specifically. Should be decided on ISO's independence from Wikidata, not
on convenience.

**(c) Narrow the gold basis of affected constraints** by dropping incidental
evidence checks so they stop attracting citations. **Rejected as stated** — it
weakens evidence to pass a gate, which is exactly backwards.

**(d) Defer all 81 to the human phase.** Honest, and the current state. The
artefacts can be fetched, frozen and passage-located now, and confirmed by a
human later, so the work is not wasted.

### Current recorded state

**No corroborating source is attached to any of the 81.** The BIPM artefact is
frozen in the store and its passage located, ready for whichever option is
taken. The 5 sources that *are* attached (on `F-BIO-15` C1/C2/C3) are ADR-0022
**measure provenance** and are explicitly **not** §4.3 corroboration; those
three cells do not require it.

---

## Q31 — The entity/date fall-through question is now LIVE, and it decides whether Mistral is in the study

**Status: OPEN — AWAITING RESEARCHER DECISION.** Raised 2026-10-15 from the
first real primary run. **Nothing was changed in response; CANON is FROZEN.**

### What was observed

First primary run over the frozen 120, three models, 960 probes each:

| model | canonicalisation rate | CANON gate (>=95%) |
|---|---|---|
| Qwen2.5-3B-Instruct | 98.65% | PASS |
| Qwen2.5-7B-Instruct | 99.17% | PASS |
| **Mistral-7B-Instruct-v0.3** | **63.02%** | **FAIL** |

Mistral's failure is **structural, not noise**, and it is entirely explained by
one probe factor:

```
syntax=declarative      2 / 320    0.6%  INVALID
syntax=cloze          165 / 320   51.6%  INVALID
syntax=interrogative  188 / 320   58.8%  INVALID
```

The mechanism, from `scripts/analysis/inspect_stage0.py`:

```
asked : Is it false that the type species of the genus Felis is Felis catus?
said  : ' Felis catus'
why   : polar probe (negated) answered with no recognisable YES/NO
```

Mistral answers a **polar** probe by naming an **answer-space member** instead
of YES/NO. Canonicaliser v1.1 is strict and discards that as INVALID.

### Why this matters beyond Mistral

**This is exactly the open question the project recorded as having no live
instance.** `docs/RESULTS_STATUS.md` states that after the Variant A rewrite
the pilot reached 0 INVALID, so "the entity/date fall-through question
(HANDOFF decision 2) has **no live instance in this dataset**. It stays OPEN and
undecided." `docs/Q21_polarity_mapping_spec.md` §7 describes the single pilot
instance — `K-C1-GEO-01-P06`, answered `'Melbourne'` — as "an answer-space
member given to a *polar* probe, which the strict rule discards rather than
reading as a contradiction", and labels the fall-through rule "an open,
undecided option".

**There are now ~355 live instances.** The question can be decided on evidence
for the first time.

A second finding is implicit and arguably more important for the paper: **the
CANON gate was frozen on ONE model** (Qwen2.5-3B, 12 pilot constraints, 100%).
A different model family fails it at 63%. Whether CANON measures *response
canonicalisability in general* or *Qwen-shaped output* is now an open empirical
question, and the answer bears on every model still to be run.

### Options

**(a) Keep the strict rule; report Mistral as CANON-FAIL and exclude its scores.**
Defensible and already the rule. Cost: a whole model family drops out, and the
exclusion is arguably an artefact of a gate tuned on one model.

**(b) Adopt the entity/date fall-through rule.** On a polar probe, an
answer-space member is read as the assertion it names rather than discarded.
Q21 §7 simulated this on the pilot: 94.8% vs 93.75%, 27 responses recovered.
Cost: **CANON is FROZEN and this modifies the canonicaliser.** It would require
unfreezing, re-running the CANON gate on the pilot, and re-canonicalising every
model already run — including the two Qwens, whose numbers would change.

**(c) Treat it as a model-level instruction-following result.** Mistral's
failure to emit YES/NO on polar probes is a real, measurable property, reported
as such rather than as a pipeline defect. Compatible with (a).

**Recommended: (a) + (c) for this run, and decide (b) deliberately before the
freeze**, with the fall-through question resolved on the Mistral data rather
than on the single pilot instance. Adopting (b) mid-study would invalidate
already-collected numbers; adopting it never leaves a known artefact in place.
**Not implemented either way.**

### What is NOT affected

The confirmatory contrast is unchanged and consistent across all three models
(C1+C2 vs C3+C4, negative in every case, interval excluding zero). Mistral's
estimate is **not reportable** because its gate failed, but the two Qwens'
are diagnostic-quality and agree in direction.


### Q31 — UPDATE 2026-10-15: OLMo-2 passes, so the gate is NOT Qwen-shaped

The full five-model primary run settles the second-order worry raised above.

| model | family | canonicalisation | CANON (>=95%) |
|---|---|---|---|
| Qwen2.5-7B | qwen | 99.17% | PASS |
| Qwen2.5-14B | qwen | 99.06% | PASS |
| Qwen2.5-3B | qwen | 98.65% | PASS |
| **OLMo-2-7B** | **olmo** | **97.29%** | **PASS** |
| Mistral-7B-v0.3 | mistral | **63.02%** | **FAIL** |

**A second non-Qwen family clears the gate comfortably.** The concern that CANON
might measure "Qwen-shaped output" because it was frozen on one Qwen model is
therefore NOT supported: an AI2-lineage model at a different scale, different
tokenizer and different pretraining corpus canonicalises at 97.3%.

That makes Mistral's 63% a **property of Mistral**, not an artefact of the gate.
It answers polar probes by naming an answer-space member instead of YES/NO, on
51.6% of cloze and 58.8% of interrogative probes, while declarative probes fail
at 0.6%.

**This strengthens recommendation (a)+(c) and weakens (b).** Adopting the
entity/date fall-through rule would now be changing a frozen canonicaliser to
accommodate one model of five, when the other four comply — and it would alter
numbers already collected for all of them. The question of whether to adopt it
is still open and still worth deciding deliberately before freeze, but it should
be decided as a question about *what Stage 0 ought to mean*, not as a repair.

**Unchanged:** Mistral's PSCR values remain NOT reportable, and its 355 INVALID
responses remain the first live dataset for deciding the fall-through rule.

---

## Q32 — The D3 judge prompt was never rendered through phi-4's chat template

**Status: FIXED AS ENGINEERING — two sub-decisions await the researcher.**
Raised 2026-10-15 from the archive of D3 job 15127.

### What was observed

`results/detectors/d3/raw/Qwen__Qwen2.5-3B-Instruct.jsonl`, inspected by the
researcher on the cluster, contains:

* rows with `raw_output: ''` and `parse_error: "no JSON object found in judge
  output"` — the judge generated **nothing**;
* parsed rows whose output begins `- [Response]: {"label": "CONTRADICTION", ...` —
  the judge invented transcript scaffolding around its answer.

### Diagnosis

Both are the signature of an instruction-tuned model handed a **bare** prompt.
`run_d3_judge.py::_generate` passed the filled `d3_prompt.txt` string straight
to `backend.generate`, and `VLLMBackend.generate` passes prompts
unchanged to `self._llm.generate()`. **No chat template was applied anywhere in
the D3 path.** phi-4 therefore ran as a *completion* model: it continued the
document rather than answering as an assistant, and for prompts that read as an
already-finished document it emitted EOS immediately.

§4.6 already requires the opposite, and `inference/chat_template.py` quotes it:
"Each model uses its own official chat template while the semantic instruction
is held constant, and the fully rendered prompt string is logged for every
response." The **primary** inference runner has always done this — the measured
`cd8e9439…` template hash is evidence of it. Only this driver did not.

### Consequence for the NONDEGEN criterion

`parse_failure_rate` over that archive measures *the harness*, not the judge.
Read as-is it would have supported the false conclusion "phi-4 is a poor
structured-output judge". **No D3 number from job 15127 is reportable**, and the
NONDEGEN go/no-go criterion cannot be evaluated against it.

### What was changed (engineering, under §4.6)

1. `_generate` renders each prompt through the judge's own template via
   `tokenizer.apply_chat_template`, and `chat_template_hash` **raises** if the
   judge has no official template rather than substituting a generic one.
2. Decoding now comes from `configs/models/_judge.yaml:protocol.decoding`
   instead of literals. **The configured `seed: 20250058` was previously
   dropped**, so no judging run was reproducible even though the config pinned
   one.
3. Every archived row records `judge_chat_template_hash`. A resume against an
   archive whose rows lack it, or whose hash differs, is **refused** — an
   archive must not become a mixture of two renderings. `--summary-only` is
   exempt, because summarising a known-bad archive is how its damage is measured.
4. The summary separates `n_empty_raw_output` from `parse_failure_rate`, so a
   serving failure can never again be read as judge indecision.

Seven tests pin this, including one asserting the configured seed is really
pinned so the others cannot pass vacuously.

### THE TWO SUB-DECISIONS — RESEARCHER'S, NOT MINE

**(a) Does re-rendering touch the prompt freeze?** `d3_llm_judge.yaml` sets
`prompt_frozen_before: test_evaluation`. The prompt **text** is byte-identical —
`d3_prompt.txt` is unmodified and goes in whole — and only the model's own turn
markers are added around it. I treated that as *rendering*, which §4.6 mandates,
rather than a change to a frozen artefact. If you read the freeze as covering the
rendered string, then this is a pre-freeze amendment and should be recorded as one.

**(b) One user turn, or system + user?** The prompt is a single block containing
both the instruction and the two statements. I render it as **exactly one user
turn, no system role**, because splitting it would change the frozen delivery and
because `_judge.yaml` declares no `supports_system_role` for the judge. Splitting
the instruction into a system turn is plausibly better for adherence and is the
shape the primary runner uses for evaluated models — but it is a change to how a
frozen prompt is delivered, so it is not taken here.

### Consequence for the existing archive

The qwen25-3b archive must be **moved aside, not resumed into**. The driver now
refuses it by name and prints the `mv` command. Judging that model again is ~2
min of A100 time, so nothing material is lost.

### QUANTIFIED 2026-10-15 — the whole 15127 archive is unusable

`--summary-only` over the pre-fix archive, researcher-run on the cluster and
pasted into the session:

```
2325 of 2325 judgement(s) with no judge_chat_template_hash
constraints: 0 pending of 120
labels: {'None': 2305, 'CONTRADICTION': 19, 'COMPATIBLE': 1}
coverage 0.005952380952380952   parse_failure_rate 0.9913978494623656
```

**parse_failure_rate = 99.14%.** Untemplated phi-4 produced parseable JSON in
**20 of 2,325** attempts. Coverage against the 3,360 possible pairs is **0.6%**.

This settles the diagnosis beyond argument. A 99% parse failure rate is not a
judge that adheres poorly to a structured-output schema; it is a model that was
never asked in its own input format. **Every figure from job 15127 is void**, and
`2325 of 2325` confirms the archive is uniformly pre-fix with no salvageable
partition.

**The 19:1 CONTRADICTION:COMPATIBLE split among the 20 that parsed must not be
read as near-degenerate labelling.** n=20, non-randomly selected (they are the
prompts that happened to survive completion mode), and NONDEGEN is a criterion
about a judge's label distribution over a proper run. It remains **unevaluated**.

### One fact from that run DOES survive, because it is not about the judge

`constraints: 0 pending of 120` with 2,325 archived means every *judgeable* pair
was attempted: **2,325 of 3,360 pairs (69.2%) are judgeable for qwen25-3b**, and
1,035 are not because at least one response canonicalised to something other
than ANSWER/NEGATED. That figure comes from Stage 0 and `render_claim`, not from
phi-4, so the templating defect does not touch it. It also confirms the identity
predicted from the code — D3's judgeable set is exactly D1's evaluable set, since
`render_claim`'s None-set is `NON_EVALUABLE_LABELS` — which gives the detector
agreement work a free integrity check on every future judge archive.

### RESOLVED — the fix is verified on real phi-4, job 15140

Job 15140, `COMPLETED 0:0`, 00:04:22 on csis.cn1, researcher-run and pasted:

```
wrote 2325 new judgement(s) -> results/detectors/d3/raw/Qwen__Qwen2.5-3B-Instruct.jsonl
labels: {'CONTRADICTION': 1017, 'COMPATIBLE': 1308}
coverage 0.6919642857142857   parse_failure_rate 0.0
```

| quantity | job 15127 (untemplated) | job 15140 (templated) |
|---|---|---|
| parse_failure_rate | **0.9914** | **0.0** |
| judgements parsed | 20 / 2,325 | **2,325 / 2,325** |
| coverage (of 3,360 pairs) | 0.0060 | **0.6920** |
| labels | None 2305 · CONTR 19 · COMP 1 | CONTR 1017 · COMP 1308 |

Coverage is now at its **ceiling**: 0.6920 = 2,325/3,360, i.e. every judgeable
pair received a decision and the only uncovered pairs are those where a response
makes no claim. There are **zero UNCLEAR** labels and zero parse errors.

**Q32 is closed as an engineering defect, correctly diagnosed and fixed.** The
two sub-decisions above — whether re-rendering touches the prompt freeze, and
one user turn versus system+user — remain the researcher's and are unaffected by
this result: both readings produce a working judge, so the choice is about what
the freeze means, not about whether the judge functions.

### NONDEGEN — what this does and does NOT establish

The label distribution is **1017 : 1308 (43.7% / 56.3%)**, so the *all-one-label*
failure mode is cleared decisively.

**That is not the same as the NONDEGEN criterion passing.** `_judge.yaml` states
it as "dev-split **judge-vs-human** agreement must be non-degenerate", and no
human labels exist. A balanced label distribution is a *necessary* condition that
is now met; the criterion as written needs annotators and remains **BLOCKED on
human validation**. NONDEGEN must not be marked PASS on the strength of a
marginal distribution.

### A trap for the detector-agreement work that follows

D3 judged **1017/2325 = 0.4374** of judgeable pairs CONTRADICTION. The mean of
qwen25-3b's four per-class D1 PSCR values is **≈0.444**. These are close, and
that closeness means **nothing about agreement**: two detectors with identical
marginals can disagree on every single pair. The §4.8.2 result is per-pair
concordance, computed pair-by-pair over the joint-coverage set, and it must not
be inferred from matching rates.


---

## Q5 — RESOLVED 2026-10-15 by ADR-0024

`D4 distribution_construction` is fixed at `p_i = softmax_i(mean_token_logprob_i / T)`
with **`T = 1` frozen as primary** and `T ∈ {0.5, 1, 2, 4}` reported as an
exploratory sensitivity band. `T = 1` is the only value §4.8.6's text determines.
ADR-0016 is SUPERSEDED. D4 moves from BLOCKED to **PENDING one GPU run**; the
blocker was the decision, what remains is compute. JSD values stay comparable
only within a single `T`, and D4 remains EXPLORATORY and exposes no verdict.

---

## Q31 — SETTLED 2026-10-15 BY ARITHMETIC (not by decision)

Q31 asked whether the entity/date fall-through rule should be adopted, and
framed that as the decision determining whether Mistral is in the study.
**It is not that decision, and cannot be.**

Measured by `scripts/analysis/classify_invalid.py` over all five models:
Mistral has **71** `POLAR_ENTITY_DATE_MEMBER` cases of 355 INVALID. Recovering
**every one of them** yields a CANON ceiling of **0.7042** — an upper bound, not
a correction — still far below the frozen >=0.95 gate. No entity/date
fall-through rule rescues Mistral.

**Q31's characterisation of the failure was also wrong.** It describes Mistral
as answering polar probes by naming an answer-space member: that is 98 of 355
(27.6%, and only 71 of those are the entity/date case — the other 27 are the
canonicaliser's deliberate boolean anti-bypass guard, a different thing). The
dominant mode is **244 of 355 (68.7%)**, answered with neither a yes/no nor a
space member.

**The sharpest result:** Mistral's out-of-space count is **13, identical to
Qwen2.5-3B's 13**. Its failure is **format compliance, not knowledge** — 342 of
355 (96.3%) are polar-format failures.

**What remains open** is the narrow, original question: what *ought* Stage 0 to
mean when a polar probe is answered with an answer-space member? That is now
decidable on its merits, with no model's inclusion resting on it. CANON and the
canonicaliser remain FROZEN. See ADR-0023 D8.

---

## Q11 — MOOT 2026-10-15

A numeric IAA threshold is no longer needed: **IAA is removed** by ADR-0023 D5.
With no annotators there is no agreement to measure, and it is *not* replaced by
inter-detector agreement — D0 and D1 share their pairwise implementation, so
their concordance is near-tautological.

---

## Q33 — Does the polar-cloze probe pathology affect the measurement? RESOLVED

**Raised 2026-10-15 from the PROBE-C audit (ADR-0023 D2). Measured, not
speculative, but its consequence is unquantified.**

`semintegrity.probes.pathology` run over the frozen test split flags **43 of 960
probes (4.5%)** as `POLAR_CLOZE_STEM_EMBEDS_GOLD_ANSWER` — a polar cloze whose
own text contains the gold answer, so the blank invites completion from the
embedded answer rather than a yes/no. They are confined to **three factor cells:
04 (16), 06 (11), 07 (16)**.

**Cells 04 and 07 are exactly the cells observed failing** in the Qwen2.5-14B,
OLMo-2 and Mistral diagnostics, which is why the concentration matters. And
`K-C1-HIS-16-P04` fails identically in two different model families — a probe
property, not a model property.

**A first version of this check was wrong and is recorded so it is not
repeated.** Flagging any polar probe containing the gold answer caught **362 of
960 (37.7%) spread evenly across all eight cells**, because a polar question
*must* state the proposition it asks about. `cloze` is the load-bearing
condition: an interrogative cues a yes/no by its form, a blank does not.

**What is NOT established.** This does **not** explain Mistral's CANON failure —
its 71 entity/date cases span **P02–P08**, not just the three flagged cells.
And the 43 probes are a property of the frozen benchmark, so the question is
what to *report*, not what to change.

**THE OPEN QUESTION, for the researcher.** 43 of 960 probes have a structural
feature that plausibly depresses canonicalisation for every model. Options:
(a) report as a limitation and leave the benchmark untouched; (b) add a
prespecified sensitivity analysis excluding the 43 and report both;
(c) something else. **(b) is my recommendation** — it costs no new data and
bounds the effect — but the benchmark is frozen and excluding probes changes the
K=8 design per constraint, so it is a design decision and not mine. No probe has
been rewritten or discarded.


### Q33 AUDIT COMPLETE — 2026-10-15

The 43 flagged probes were inspected individually. Findings:

**They are not defective probes. They are an unavoidable form.** Every one is a
polar cloze on an entity or date constraint, e.g.

```
K-C1-GEO-13-P04  gold='Kanagawa Prefecture'  expected='YES'
  The statement "Kanagawa Prefecture is the prefecture of Yokohama" is ___.
```

To ask whether a proposition holds you must state it, and stating it names the
answer. So the gold answer's presence is **necessary**, not a mistake. What is
specific to the cloze form is that a blank does not say what kind of token
belongs in it, where an interrogative cues yes/no by its syntax.

**Composition, measured:** 27 of 120 constraints affected; 11 lose one probe and
16 lose two; **no constraint falls below K=6**; 285 of 3,360 pairs (8.5%) would
be lost. By class: C1 22, C4 21 — zero in C2/C3, which are entirely boolean.

**An alternative predicate was tested and is equivalent.** "Contains the gold
answer" and "contains ANY answer-space member" flag **exactly the same 43**:
this benchmark has no distractor-embedding polar cloze, and the other 17
entity/date polar clozes contain no answer-space member at all. The narrower
predicate is therefore not a restriction, and the question is closed by
measurement rather than assumption.

**Empirical impact on the CANON-passing models is small.** Their entity/date
fall-through cases total **7** (Qwen2.5-14B 3, OLMo-2 4), all in flagged cells —
about 4% of the flagged probe-responses, and 0.18% of their 3,840 responses.
**Mistral is unaffected by this explanation**, its 71 cases spanning P02–P08.

### S4 IS IMPLEMENTED, AND IS DEFENSIBLE. K=8 REMAINS PRIMARY.

`analysis.sensitivity.s4_probe_exclusion` plus its plan function. It is
defensible for one specific reason worth stating:

> **The exclusion criterion is response-independent.** PROBE-C flags a probe on
> its *text*, with no reference to any model's reply. Excluding on an outcome —
> "probes that went INVALID" — would be selection on the dependent variable and
> would bias PSCR by construction. Excluding on text does not.

Its cost is reported rather than hidden: dropping probes breaks the ADR-0003
within-constraint factor balance for the 27 affected constraints and reduces
their pair counts, widening their per-constraint PSCR. The constraint remains
the bootstrap unit, so the interval absorbs this. S4 carries
`is_primary: False` structurally and an interpretation limit stating that a
non-zero estimate shows PSCR *depends* on the probe type without establishing
which figure is correct.

### THE ONE DECISION STILL YOURS

S4 is implemented and will run on the existing responses with no GPU. What
remains is **whether its result is reported in the dissertation**:

* **(a) report S4 alongside the primary** — my recommendation. It costs nothing,
  it bounds the effect, and declaring it secondary in advance is cleaner than
  being asked about it at the viva with no answer.
* **(b) report the pathology as a limitation only**, without the S4 number.
  Defensible if you judge a secondary PSCR figure more confusing than helpful.

**No probe has been rewritten, discarded or reordered, and the benchmark is
unchanged.** Either option is available from the artifacts; nothing is
foreclosed.


### Q33 RESOLVED — 2026-10-15

**The researcher chose option (a): report S4 as a secondary sensitivity analysis
alongside the unchanged K=8 primary results.** Implemented and measured.

**S4, four models, paired over the identical constraints:** -0.0030
(-0.0087, +0.0034) · -0.0022 (-0.0047, -0.0001) · +0.0066 (-0.0006, +0.0145) ·
+0.0052 (-0.0018, +0.0139). Magnitudes of 0.002-0.007 are **one to two orders of
magnitude below H1_primary's 0.090-0.182**, and the signs are mixed. One of four
intervals excludes zero at an estimate of -0.0022; with four comparisons, mixed
signs and no multiplicity correction, that is consistent with noise and is not
reported as an effect.

**The 43 flagged probes do not materially affect the primary metric.** K=8
remains the primary design, no probe was rewritten, discarded or reordered, and
the finding is reported as a limitation with its effect bounded rather than as a
defect to be repaired.

**One consequence worth recording.** The `PROBE-C` gate originally required ZERO
pathology findings. That was never achievable — the benchmark is FROZEN, and
these 43 probes are polar clozes whose statement necessarily names the gold
answer, which is a property of the probe FORM rather than a defect in any probe.
The criterion was therefore revised to require findings to be **quantified and
their effect bounded**, which S4 satisfies. Revising a gate after seeing data is
a researcher degree of freedom and is recorded as one in
`configs/inference/pilot.yaml` under `criterion_revised_2026_10_15`.
