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
**SIGNIFICANT — Phase 5** · `RESOLVED, PENDING SIGN-OFF`

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
**SIGNIFICANT — Phase 5** · `FEASIBILITY`

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
**PARTIALLY RESOLVED 2026-09-11** — interaction model decided (researcher runs all cluster commands, ADR-0010). Cluster *facts* still unknown until the probe runs.
**Was: BLOCKING — Phase 6** · `INFRASTRUCTURE`

The working directory `/nfs_home/users/yashsinha/H202500058_Suraj` sits under
another user's home directory. Worth confirming this is the intended designated
space and that it is writable by your account, since §"Cluster environment"
forbids modifying other users' folders.

Also unknown until `scripts/cluster/probe_cluster.sh` runs: partition names, GPU
models and counts, CUDA/driver versions, module system, storage quota, whether
the login node has internet (needed to cache Wikidata and weights), and whether
R is available (Q8).
