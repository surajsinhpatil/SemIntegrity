# Implementation blueprint — proposal → code

Every normative statement in `proposal/semintegrity_proposal.docx` maps to a
concrete module, config or artefact below. Where a row says **UNRESOLVED**, the
proposal underdetermines the implementation and a decision is logged in
[`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).

## §2 Positioning / §4.12 Phase 0 — literature

| Proposal requirement | Module / artefact |
|---|---|
| Verify every citation against ACL Anthology or arXiv | `src/semintegrity/analysis/literature.py`, `scripts/analysis/verify_citations.py` |
| Literature verification table, citation status, source links | `docs/phase0/literature_verification.md` (+ `data/raw/literature/*.json`) |
| Positioning + novelty-risk notes | `docs/phase0/positioning.md`, `docs/phase0/novelty_risk.md` |
| **No novelty claim before verification** | enforced by review, not code; status tracked in `PROJECT_STATUS.md` |

## §4.2–4.3 Constraint taxonomy and benchmark construction

| Requirement | Module |
|---|---|
| 4 categorical classes, **not ordered** | `configs/project.yaml:constraint_classes.ordered=false`; `tests/unit/test_project_config.py` |
| Per-constraint record (17 fields) | `src/semintegrity/schemas/constraint.py` (pydantic) |
| 120 = 30 families × 4 classes; 6 per (domain, class) | `configs/benchmark/design.yaml`; `src/semintegrity/benchmark/design_validator.py` |
| Schema-based instantiation, 6 schemas × 5 instances | `src/semintegrity/benchmark/schemas.py` |
| Ground truth from Wikidata + second source, with provenance | `src/semintegrity/kb/wikidata.py`, `src/semintegrity/kb/corroboration.py` |
| Temporal qualifiers P580/P582 | `src/semintegrity/kb/temporal.py` |
| Entity familiarity via sitelinks, matched across classes | `src/semintegrity/kb/sitelinks.py`; matching test in `design_validator.py` |
| Frozen KB snapshot (compute nodes never hit the network) | `data/raw/wikidata_cache/`, `scripts/benchmark/snapshot_kb.py` |

## §4.4 Probe design

| Requirement | Module |
|---|---|
| Formal probe representation (10 fields); equivalence = identity | `src/semintegrity/schemas/probe.py` |
| K=8, 960 probes, 28 pairs/constraint | `configs/project.yaml:probes.primary` |
| Factors balanced exactly across classes | `configs/benchmark/probe_factors.yaml`; `src/semintegrity/probes/factor_design.py`; `tests/unit/test_probe_balance.py` |
| Track A constrained output | `configs/benchmark/answer_types.yaml`, `configs/inference/prompts.yaml` |
| Track B free-form (20 constraints) | `configs/inference/track_b.yaml`; `src/semintegrity/canonicalization/trackb_extraction.py` |
| Saturation tier 24×50, k∈{2,4,8,16,32,50} | `configs/inference/saturation.yaml`; `src/semintegrity/analysis/recovery.py` |
| Preregistered stratified subset selection, fixed before inspection | `scripts/benchmark/select_subsets.py` |
| Human probe validation (2 annotators primary / 1 saturation) | `src/semintegrity/annotation/probe_validation.py` |
| Discard rate recorded, extension vs primary | `results/analysis/probe_discard_rates.json` |

## §4.5–4.6 Models and inference

| Requirement | Module |
|---|---|
| 7 models, pinned open-weight revisions | `configs/models/*.yaml`; `scripts/models/pin_revisions.py` |
| bf16 uniformly, no selective quantisation | `configs/models/_defaults.yaml`; asserted in `tests/unit/test_project_config.py` |
| Model-specific official chat templates, constant semantic instruction | `src/semintegrity/inference/chat_template.py`; `scripts/models/audit_chat_templates.py` |
| Log the fully rendered prompt | `src/semintegrity/schemas/response.py` (required field) |
| 24-field provenance per response | `configs/inference/_provenance.yaml`; schema-enforced at write time |
| Empirical determinism check (100 prompts) | `configs/inference/determinism_check.yaml`; `src/semintegrity/inference/determinism.py` |
| Stochastic subset, variance decomposition | `configs/inference/stochastic.yaml`; `src/semintegrity/analysis/variance_decomposition.py` |
| Gemma-2 soft-capping preflight | `scripts/models/gemma2_softcap_check.py` — **gates the Gemma-2 arm** |
| Incremental JSONL, resumable | `src/semintegrity/utils/io.py` (done), `src/semintegrity/inference/runner.py` |

## §4.7 Stage 0 canonicalisation

| Requirement | Module |
|---|---|
| Labels {answer, ABSTAIN, INVALID, AMBIGUOUS, FAILED} | `src/semintegrity/canonicalization/labels.py` |
| Alias tables built at authoring time from the closed answer space | `src/semintegrity/canonicalization/alias_tables.py`; `data/benchmark/alias_tables/` |
| Timeout → 1 retry, identical config → FAILED | `src/semintegrity/inference/runner.py` |
| Question/cloze → declarative rendering for D2 | `src/semintegrity/detectors/d2/templates.py` |
| **Never manually cleaned after inspecting results** | rules-of-engagement; canonicaliser frozen with a recorded hash before test evaluation |

## §4.8 Detection

| Layer | Module |
|---|---|
| D0 symbolic | `src/semintegrity/detectors/d0/{registry,runner}.py`, `predicates/` |
| D0 three-instance schema audit + freeze | `scripts/detectors/audit_d0.py`; `results/manifests/d0_freeze.json` |
| D1 canonical exact match | `src/semintegrity/detectors/d1/exact_match.py` |
| D2 NLI, bidirectional, max contradiction prob, per-class calibrated threshold | `src/semintegrity/detectors/d2/{nli,calibrate}.py` |
| D3 pairwise judge, randomised A/B, structured output, archived | `src/semintegrity/detectors/d3/{judge,schema,stability}.py` |
| D4 teacher-forced candidate distributions + JSD | `src/semintegrity/detectors/d4/{scoring,jsd}.py` |
| D4 is never a detector | asserted in `tests/unit/test_d4_scope.py` |

## §4.9 Human annotation

| Requirement | Module |
|---|---|
| Blinded pair-level interface | `src/semintegrity/annotation/interface.py` (local single-file HTML app + JSONL export) |
| Field masking (model, detector, class, expected) | `src/semintegrity/annotation/blinding.py` |
| Sample A (~400 representative) / Sample B (~300 enriched), never blended | `scripts/annotation/draw_samples.py` |
| Krippendorff α, raw agreement, confusion matrix, per class | `src/semintegrity/analysis/agreement.py` |
| Adjudication of disagreements | `src/semintegrity/annotation/adjudication.py` |

## §4.10 Metrics / §4.11 Statistics

| Requirement | Module |
|---|---|
| PSCR, PCS, Consistency@K, AOCR, TruthAcc, Abstention, Recovery@k, D0 coverage | `src/semintegrity/analysis/metrics.py` |
| Detector P/R/F1/AUPRC per class | `src/semintegrity/analysis/detector_eval.py` |
| Cluster bootstrap over constraints (confirmatory) | `src/semintegrity/analysis/bootstrap.py` |
| Beta-binomial mixed model (secondary) | `src/semintegrity/analysis/glmm.py` — backend **UNRESOLVED** (Q8) |
| BH-FDR outside confirmatory contrasts | `src/semintegrity/analysis/multiplicity.py` |
| Knowledge screen, conditioned reporting | `src/semintegrity/knowledge_screen/` |
| Figures | `src/semintegrity/analysis/figures.py` → `results/figures/` |

## §4.13 Infrastructure

| Requirement | Artefact |
|---|---|
| Login node restrictions | `scripts/_guard_login_node.sh`, `configs/cluster/cluster.yaml:hard_rules` |
| Slurm jobs, logs, resume | `slurm/`, `slurm/templates/`, `scripts/slurm/render_jobs.py` |
| Weights cached once from a non-GPU session | `scripts/models/cache_weights.sh` (login-node, network-only, no GPU) |
| Single inference stack | vLLM only; mixing frameworks is forbidden |
| Fallback + quantisation ablation | `configs/cluster/cluster.yaml:fallback` |

## §5.6 Release

| Requirement | Artefact |
|---|---|
| Benchmark, predicates, raw outputs, detector outputs, annotations, provenance manifest | `scripts/release/build_release.py` → `results/manifests/release_manifest.json` |
| Dataset CC-BY-4.0, code OSI licence | `LICENSE`, `data/benchmark/LICENSE` |
| Frozen dev/test split | **UNRESOLVED** (Q1) |
| Preregistration on OSF | `docs/prereg/` — prepared by this repo, **submitted only by the researcher** |
