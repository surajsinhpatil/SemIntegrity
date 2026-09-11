# PROJECT_STATUS

**Project:** SemIntegrity — Measuring Semantic Self-Inconsistency in LLMs Across Structured Integrity Constraints
**Last updated:** 2026-09-11 (session 2)
**Current phase:** Phase 1 (representation infrastructure) — *infrastructure complete and tested; pilot constraint CONTENT not yet authored*

> This file is the live state of the project. It is updated at the end of every
> working session. Nothing is marked complete that has not actually been done
> and verified against an artefact on disk.

---

## Phase board

| Phase | Name | Status | Gate |
|---|---|---|---|
| −1 | Infrastructure reconnaissance | **NOT STARTED** — needs cluster access | env test + smoke job pass |
| 0 | Literature verification | **NOT STARTED** | every citation VERIFIED |
| 1 | Constraint representation + 12 pilot constraints | **INFRASTRUCTURE DONE** · content pending | predicates execute; ground truth resolves |
| 2 | Pipeline implementation | **NOT STARTED** | pipeline runs end to end |
| 3 | Pilot (12×5×3) | **NOT STARTED** | go/no-go criteria |
| 4 | Preregistration preparation | **NOT STARTED** | **researcher submits to OSF** |
| 5 | Full benchmark (120 constraints) | **NOT STARTED** | benchmark frozen |
| 6 | Full inference | **NOT STARTED** | provenance verified |
| 7 | Detection + annotation | **NOT STARTED** | per-class detector P/R/F1 |
| 8 | Statistics + figures | **NOT STARTED** | — |
| 9 | Writing support | **NOT STARTED** | — |

---

## Completed

### Session 1 — 2026-09-11
* Read the complete proposal (`proposal/semintegrity_proposal.docx`, v2, 7,540 words).
* Produced the proposal→module blueprint: `docs/BLUEPRINT.md`.
* Produced the risk/ambiguity register: `docs/OPEN_QUESTIONS.md` (20 items).
* Produced the roadmap: `docs/IMPLEMENTATION_PLAN.md`.
* Created the repository structure and foundational configuration.
* Implemented and tested the foundation layer:
  `utils/{hashing,ids,paths,config,io,logging}.py`.
* **32 unit tests passing** (`pytest -q`), including arithmetic verification
  that the probe-factor design is exactly balanced at class level.
* Wrote read-only cluster probe script and Slurm templates (deliberately
  without guessed partition names).
* Six ADRs recorded.

**Verified by:** `python -m pytest -q` → `33 passed`; `scripts/validate_configs.py` → 34 configs parse.

* Four blocking decisions taken by the researcher and recorded (ADR-0007…0010):
  separate 24-constraint dev set · open-weight D3 judge · disaggregated GLMM
  cells · researcher-runs-cluster-commands. Unresolved markers: 19 → 16, of
  which 14 are answered by the cluster probe.


### Session 2 — 2026-09-11 · Phase 1 infrastructure

Built and tested the constraint-representation layer. **No pilot constraint
content was authored or frozen** — that is presented for approval first, as
instructed.

| Component | Module | Tests |
|---|---|---|
| Controlled vocabularies | `schemas/enums.py` | ordering on `ConstraintClass` is **disabled in code** |
| Constraint record (17 proposal fields + derived) | `schemas/constraint.py` | cross-field validation, C4 temporal requirement |
| Probe record (10 formal + 4 surface factors) | `schemas/probe.py` | equivalence key, cloze blanks, factor cells |
| Response + 22-field provenance | `schemas/response.py` | every field required, raw responses frozen |
| Benchmark design validator | `benchmark/design_validator.py` | 10 rules, all localised to offending ids |
| Benchmark loader + freeze | `benchmark/loader.py` | content hash, drift detection, write refusal |
| Wikidata client | `kb/wikidata.py` | resolves fully offline from the snapshot |
| Frozen KB cache | `kb/cache.py` | tamper/loss/untracked detection, archive-on-refresh |
| KB adapters | `kb/adapter.py` | `WikidataKB` records every fact used |
| D0 predicate framework | `detectors/d0/base.py` | pair-level + set-level verdicts |
| D0 registry + freeze policy | `detectors/d0/registry.py` | modification after freeze raises |
| Three-instance audit harness | `detectors/d0/audit.py` | human verdicts required, never generated |
| Reference predicates (C1, C4) | `detectors/d0/predicates/` | schema-general, carry no facts |
| Probe factor generator | `probes/factor_design.py` | exact balance verified at both levels |

**Verified:** `pytest -q` → **173 passed** · `ruff check` → **all checks passed**
· coverage **90%** · `validate_configs.py` → 34 configs parse, 16 markers pending.

**Bugs the tests caught and fixed:**
* `kruskal` raised on perfectly matched sitelinks — the *ideal* outcome was an error.
* `@register` bound to a global registry, so discovery was untestable and no-opped on re-import.
* `_defaults.yaml` nested keys under `defaults:`, so no model actually inherited `dtype: bfloat16`.
* `_schema_balance` carried dead code and an O(n²) scan.

**Deliverable:** `docs/HUMAN_EFFORT_BUDGET.md` — exact breakdown, **5,721 judgements**
(corrects the earlier ~4,500 undercount), ≈125 hours, ≈31 of them the second annotator's.

---

## Pending — immediate next steps

| # | Task | Blocked by |
|---|---|---|
| 1 | **Approve Q21** — polarity inside vs outside the equivalence key | **researcher** — blocks probe authoring |
| 2 | **Approve Q22** — which D0 verdict is "D0" in the paper | **researcher** — both implemented |
| 3 | Approve pending methodology ADRs 0002, 0003, 0004, 0006 | **researcher** |
| 4 | Run `scripts/cluster/probe_cluster.sh` | **researcher** — unblocks 14 of 16 markers |
| 5 | Accept HF licences; create a read token | **HUMAN-ONLY** (Q14) |
| 6 | Draft 12 pilot constraints → **present for approval before freezing** | me, then researcher |
| 7 | Phase 0 literature sweep | *unblocked* |
| 8 | Identify the second annotator (~31 h commitment) | **researcher** (Q9) |

## Blockers

| ID | Blocker | Severity | Owner |
|---|---|---|---|
| Q20 | Cluster facts unknown; probe not yet run | BLOCKING P−1 → P6 | researcher runs the script |
| Q14 | Gated HF weights + ~244 GB storage, quota unknown | BLOCKING P6 | researcher (licences) + probe |
| Q9 | Second annotator not identified (~4,700 human judgements incl. dev probes) | BLOCKING P5/P7 | researcher |
| Q11 | "Acceptable IAA" has no number | SIGNIFICANT, needed by P4 | researcher |
| Q6 | "Evaluable probe pair" definition + zero-denominator policy | BLOCKING P8 | proposal stands in Q6; confirm at P4 |
| Q5 | D4 log-prob → distribution mapping | SIGNIFICANT | proposal stands in Q5; freeze at P4 |
| Q8 | GLMM backend (PyMC vs glmmTMB) | SIGNIFICANT | answered by the cluster probe (R availability) |
| Q12 | Schema × domain crossing feasibility | SIGNIFICANT | emerges during P5 authoring |
| Q13 | Gemma-2 soft-capping preflight not run | SIGNIFICANT | runs at P3 |

**Cleared 2026-09-11:** Q1 (ADR-0007) · Q3 (ADR-0008) · Q4 (ADR-0009) · cluster interaction (ADR-0010).

Full detail for every item: [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md).

---

## Decisions taken

| ADR | Decision | Status |
|---|---|---|
| 0001 | Package layout `src/semintegrity/<module>/` | PROPOSED |
| 0002 | 30 families × 4 classes design lattice | PROPOSED |
| 0003 | Probe-factor balancing: 2×2×2 within constraint + syntax rotation | PROPOSED |
| 0004 | PyMC as the beta-binomial backend, glmmTMB as cross-check | PROPOSED (blocked on Q8) |
| 0005 | Append-only JSONL, create-exclusive manifests, keyed resume | **ACCEPTED — implemented** |
| 0006 | Gemma-2 soft-capping preflight gate | PROPOSED |
| 0007 | Separate 24-constraint development set, disjoint from the 120 | **ACCEPTED** |
| 0008 | Open-weight D3 judge: Phi-4 primary, OLMo-2 cross-check | **ACCEPTED** |
| 0009 | Disaggregated binomial cells for probe-factor covariates | **ACCEPTED** — preregistered deviation |
| 0010 | Researcher runs all cluster commands; no SSH driven from here | **ACCEPTED** (engineering) |
| 0011 | Frozen, content-addressed knowledge-base cache | **ACCEPTED** (engineering) |

Methodology ADRs 0002, 0003, 0004 and 0006 are **PROPOSED — AWAITING RESEARCHER
APPROVAL**. Code depending on them is written behind a single named switch so the
decision can still go either way (see `EQUIVALENCE_KEY_FIELDS` for the pattern).

## Human-only tasks (never automated, never simulated)

- [ ] Accept model licences on Hugging Face; create and export an access token
- [ ] Run the cluster probe over SSH (credentials are entered locally, never here)
- [ ] Author the factual content of the constraints and verify ground truth
- [ ] Human semantic validation of probe equivalence (2 annotators)
- [ ] Annotation samples A and B (2 annotators) and adjudication
- [ ] Fix the numeric IAA threshold before the pilot (Q11)
- [ ] Submit the preregistration to OSF
- [ ] Any ethics / institutional approval required for annotation
- [ ] Final interpretation of results and authorship decisions

---

## Integrity ledger

Claims made in this repository that are **not yet** backed by a real artefact:

| Claim | Status |
|---|---|
| Model revision hashes | **unpinned** (`revision: null`) — never fabricated; resolved by `scripts/models/pin_revisions.py` |
| Judge model Hub ids (`microsoft/phi-4`, `allenai/OLMo-2-1124-13B-Instruct`) | **selected, not yet verified against the Hub** — `status: SELECTED_PENDING_HUB_VERIFICATION` |
| Cluster partitions / GPUs / quota | **UNKNOWN** — no guesses written anywhere |
| torch / vLLM versions | **unpinned** — depend on the cluster CUDA version |
| Literature verification | **not started** — no citation is asserted as verified |
| Any experimental result | **none exist** |
| Any human annotation | **none exist** |
| Pilot constraint content | **not authored** — infrastructure only; content goes to the researcher for approval before it is treated as benchmark data |
| Synthetic test fixtures | factually invented, confined to `tests/`, and `test_no_synthetic_leak.py` asserts they never reach `data/` or `results/` |
