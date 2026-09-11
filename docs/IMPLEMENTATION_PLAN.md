# SemIntegrity — implementation roadmap

Authoritative spec: `proposal/semintegrity_proposal.docx` (v2).
Module map: [`BLUEPRINT.md`](BLUEPRINT.md) · Risks: [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) · Live state: [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md)

---

## 0. Dependency graph

```
                      ┌── P0 literature ──────────────┐ (independent; gates WORDING only)
                      │
P-1 infra probe ──┬── P1 representation ── P2 pipeline ── P3 pilot ── P4 prereg ── P5 benchmark
   (cluster,      │        │                   │            │            │             │
    env, weights) │        └── KB snapshot ────┘            │            │             │
                  │                                          └── go/no-go ┘             │
                  └──────────────────────────────────────────────────────────────── P6 inference
                                                                                          │
                                                                    P7 detection + annotation
                                                                                          │
                                                                              P8 analysis + figures
                                                                                          │
                                                                                    P9 writing
```

**Critical path:** P-1 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8.
**Parallelisable:** P0 (literature) runs alongside P1–P3. Cluster probing,
licence acceptance and weight caching (P-1) run alongside everything up to P6
and should start **now**, because gated-model access and quota are the longest
external lead times.

**Hard gates** (a downstream phase must not start until these pass):

| Gate | Blocks |
|---|---|
| Q1 dev/test split decided | P2 (D2 calibration), P4 |
| Q3 judge model decided | P2 (D3), P7 |
| Q4 GLMM formula resolved | P4, P8 |
| Q9 second annotator identified | P5 probe validation, P7 |
| Q14 HF licences accepted + quota verified | P6 |
| Gemma-2 soft-cap preflight passes | Gemma-2 arm of P6 |
| Phase 3 go/no-go all pass | P5 |
| Preregistration submitted **by the researcher** | any test-set collection |

---

## Phase −1 — Infrastructure reconnaissance  ·  *start immediately, runs in parallel*

**Why:** every later decision (torch/vLLM pins, tensor-parallel size, walltimes,
whether the 70B run is feasible at all) depends on facts about the cluster that
cannot be guessed.

| Step | Artefact | Who |
|---|---|---|
| Run read-only cluster probe | `docs/phase0/cluster_probe_*.md` | researcher runs the script |
| Fill in `configs/cluster/cluster.yaml` | config | me, from the probe output |
| Accept HF licences for Llama-3.1/3.3, Gemma-2, Mistral-v0.3 | HF account | **HUMAN-ONLY** |
| Create HF read token, export as env var (never committed) | environment | **HUMAN-ONLY** |
| Pin model revisions from the Hub | `configs/models/*.yaml` | me, `scripts/models/pin_revisions.py` |
| Build conda/venv on the cluster; freeze lock files | `requirements/lock/*.txt` | me (via Slurm/login-safe commands) |
| Cache weights from a non-GPU session | `$WORK/hf_cache` | me, after quota check |
| Env test + smoke inference through Slurm | `slurm/logs/` | me |

**Exit:** `00_env_test.sbatch` and `10_smoke_inference.sbatch` both succeed; every
`UNKNOWN` in `configs/cluster/cluster.yaml` is filled.

---

## Phase 0 — Literature verification and positioning  ·  *parallel*

**Why:** §2.3 states the positioning is provisional, and §4.12 gates the novelty
wording on this sweep. It gates *wording*, never methodology.

**Deliverables**
* `docs/phase0/literature_verification.md` — one row per cited work:
  claimed venue/year · verified venue/year · DOI/ACL-anthology/arXiv id · URL ·
  retrieval date · status ∈ {VERIFIED, CORRECTED, NOT_FOUND}.
* `data/raw/literature/*.json` — raw API responses, archived.
* `docs/phase0/positioning.md` and `docs/phase0/novelty_risk.md`.

**High-risk citations** — several entries in Appendix A.3 are cited as
*ICLR 2026* / *ACL 2026* (LogiConBench, ChaosBench-Logic, Tsujimura et al.,
Flip-Flop Consistency, "Logical Consistency as a Bridge"). These carry the
greatest chance of a mis-stated venue, a preprint-only status, or a title drift,
and they are also the ones that most constrain the contribution claims. They are
verified first.

**Rule:** no novelty claim is written anywhere until its row reads VERIFIED.
Verification is done against the real sources, never asserted.

---

## Phase 1 — Constraint representation and 12 pilot constraints

**Files created**
```
src/semintegrity/schemas/{constraint,probe,response,annotation,detection}.py
src/semintegrity/benchmark/{design_validator,schemas,loader}.py
src/semintegrity/kb/{wikidata,sitelinks,temporal,corroboration,cache}.py
src/semintegrity/detectors/d0/{registry,base}.py + predicates/{c1,c2,c3,c4}_*.py
data/benchmark/pilot/constraints.jsonl
data/benchmark/pilot/probes.jsonl
scripts/benchmark/{author_constraint.py,snapshot_kb.py,validate_benchmark.py}
tests/unit/test_schemas.py · test_design_validator.py · test_d0_predicates.py
```

**Steps**
1. Pydantic schemas for the 17-field constraint record and the 10-field formal
   probe representation, with strict validation (unknown fields rejected).
2. Design validator enforcing the lattice in `configs/benchmark/design.yaml`.
3. Wikidata client: SPARQL + `wbgetentities`, disk-cached, offline-replayable.
   **Compute nodes never touch the network** — they read the frozen snapshot.
4. D0 predicate framework: a registry keyed by `schema_id`, a typed base class,
   a three-instance audit harness, and a freeze manifest.
5. Author **12 pilot constraints** (3 per class) with real, sourced ground truth
   and second-source corroboration — researcher authors the facts, I build the
   tooling, fetch the KB evidence and run validation.
6. 5 probes per pilot constraint (§4.12 pilot spec).

**Exit:** predicates execute; ground truth resolves; validators pass; tests green.

---

## Phase 2 — Pipeline implementation

**Files created**
```
src/semintegrity/canonicalization/{labels,canonicaliser,alias_tables,trackb_extraction}.py
src/semintegrity/inference/{runner,vllm_backend,chat_template,provenance,determinism,smoke}.py
src/semintegrity/detectors/d1/exact_match.py
src/semintegrity/detectors/d2/{nli,templates,calibrate}.py
src/semintegrity/detectors/d3/{judge,schema,stability,prompt}.py
src/semintegrity/detectors/d4/{scoring,jsd}.py
src/semintegrity/annotation/{interface,blinding,probe_validation,adjudication,export}.py
src/semintegrity/analysis/{metrics,agreement}.py
scripts/models/{pin_revisions,audit_chat_templates,gemma2_softcap_check,cache_weights}.py
scripts/slurm/render_jobs.py
slurm/*.sbatch  (rendered with real partitions)
```

**Order within the phase** — canonicalisation first, because §4.7 makes it a
prerequisite for every detector and D1 is meaningless without it:

1. Stage 0 canonicaliser + alias tables + label taxonomy.
2. Inference runner: vLLM backend, chat-template rendering per model, full
   24-field provenance, append-only JSONL, resume, timeout→retry→FAILED.
3. D1 (trivial once Stage 0 exists) → D0 wiring → D2 → D3 → D4.
4. Annotation interface: a single self-contained local HTML page that loads a
   blinded JSONL batch and writes labels back as JSONL. No server, no accounts,
   works offline, output is diffable.
5. Metrics module with the proposal's three worked PSCR/PCS examples as
   regression tests.

**Exit:** the pipeline runs end to end on the 12 pilot constraints with 3 models.

---

## Phase 3 — Pilot  ·  *first real GPU spend*

12 constraints × 5 probes × 3 models × all detectors = 180 generations.

**Escalation, never skipped:** unit tests → config validation → `00_env_test`
→ `10_smoke_inference` → per-model load validation → Gemma-2 soft-cap preflight
→ pilot.

**Go/no-go criteria** are fixed in `configs/inference/pilot.yaml` *before* the
run (§4.12). Results are evaluated against them in
`docs/phase1/pilot_go_no_go.md`. Any failure triggers pipeline revision before
the full benchmark is authored — not a relaxed criterion.

---

## Phase 4 — Preregistration preparation

**Files:** `docs/prereg/{analysis_plan,hypotheses,metrics,exclusions,power}.md`,
plus a frozen snapshot of every tuned artefact hash.

Must resolve Q1, Q4, Q5, Q6, Q11 first — each is a preregistered quantity.

> **I prepare the materials. Submission to OSF is the researcher's action.
> Preregistration is never reported as complete until you tell me it is.**

---

## Phase 5 — Full benchmark authoring (120 constraints)

The largest human-effort phase. Tooling I provide:
* authoring CLI with live schema + design-lattice validation;
* Wikidata resolution, sitelink capture, temporal-qualifier extraction;
* second-source corroboration checklist per constraint;
* probe generator that emits exactly the balanced factor cells from Q2;
* automated pre-filter (format, entity presence, answer-type, no answer leakage);
* blinded two-annotator probe validation batches + discard-rate reporting;
* freeze: content hash over the benchmark, written to `results/manifests/`.

**Exit:** all `design_validator` rules pass; sitelink matching test passes;
≥90% probe survival; benchmark frozen. **No changes after this point.**

---

## Phase 6 — Full inference

Per model, submitted as Slurm array jobs with resume:
primary Track A → saturation → Track B → stochastic → knowledge screen →
determinism check.

Volume ≈ 21,750 generations plus ≈ 27,000 D4 scoring passes (Q18).
70B runs last and separately (tp=2, ~141 GB weights).

**Exit:** provenance verified for 100% of responses; no missing
`(model, probe, sample)` cells; manifests + checksums written.

---

## Phase 7 — Detection and annotation

D0 → D1 → D2 (per-class frozen thresholds) → D3 (archived judgements,
stability subset, family-affinity check) → D4 (exploratory).
Then sample A (~400) and sample B (~300) drawn, blinded, annotated by **two
humans**, adjudicated; α, raw agreement and confusion matrices computed;
detector P/R/F1 (+AUPRC for D2/D3) per constraint class.

---

## Phase 8 — Statistical analysis and figures

Cluster bootstrap (confirmatory) → beta-binomial mixed model (secondary) →
BH-FDR elsewhere → knowledge-conditioned reporting → figures.
Reliability triad reported jointly and never collapsed.

---

## Phase 9 — Writing support

Methods documentation, experiment logs, result tables, figure descriptions,
reproducibility appendix, limitations. Claims written only against verified
literature rows and realised results.

---

## Engineering standards applied throughout

* **Immutability.** `results/raw/**` is append-only; `write_json_exclusive`
  refuses to overwrite. Derived outputs record the `run_id` and config hash of
  their source.
* **Provenance.** Every experiment carries an experiment id, a config snapshot
  hash, model revision, timestamp and environment metadata.
* **Determinism of identifiers.** Ids are content-addressed pure functions
  (`src/semintegrity/utils/ids.py`), so the same input reproduces the same id on
  any machine.
* **Tests before spend.** Unit tests and config validation run before any
  `sbatch`; a smoke job runs before any large job.
* **Login-node discipline.** `scripts/_guard_login_node.sh` aborts heavy work
  outside a Slurm allocation.
* **No fabrication.** Experimental results, annotations, literature
  verification, model outputs and successful job execution are only ever
  reported from real artefacts on disk.
