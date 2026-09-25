# SemIntegrity — session handoff

**Written 2026-09-25.** Read this, then `PROJECT_STATUS.md`, then
`docs/OPEN_QUESTIONS.md`. The proposal in `proposal/semintegrity_proposal.docx`
is the authoritative spec and overrides anything here.

---

## What this project is

**SemIntegrity** — measuring semantic self-inconsistency in LLMs across four
structured integrity-constraint classes (C1 atomic, C2 conjunctive, C3
quantified, C4 temporal). M.E. dissertation, BITS Pilani, Surajsinh Patil.

Three quantities measured jointly: how inconsistency varies by constraint class,
how reliable the detectors are per class, and how many meaning-preserving probes
are needed to surface an inconsistency. Factual accuracy, consistency and
abstention are held apart throughout.

Target benchmark: 120 constraints (30/class, 5 domains) × K=8 probes = 960
probes, 7 open-weight models, detectors D0–D4 against blinded human annotation.

---

## State: working, verified

* **16 commits**, `255 tests passing`, `ruff` clean.
* **Phase 0 literature verification COMPLETE** — 12/12 citations resolved
  (7 verified, 4 venue corrections, 1 preprint). `docs/phase0/literature_verification.md`.
* **Phase 1 infrastructure COMPLETE** — schemas, design validator, Wikidata
  client + frozen cache, D0 framework with freeze policy and three-instance
  audit, probe factor generator.
* **Pilot benchmark BUILT** — 12 constraints, 96 probes, real records in
  `data/benchmark/pilot/`. All **DRAFT**: 21/21 Wikidata evidence checks pass,
  no human review, nothing frozen.
* **Cluster working** — env built, GPU verified, model cached.
* **Stage 0 canonicaliser + D1 detector** implemented and tested.

## State: NOT done

* No model has produced output yet. **Zero experimental results.**
* No human annotation (~5,721 judgements needed — `docs/HUMAN_EFFORT_BUDGET.md`).
* The 120-constraint benchmark is not authored.
* D2 (NLI), D3 (judge), D4 (distributional) are not implemented.
* No preregistration submitted.

---

## The cluster

| | |
|---|---|
| Host | `172.24.16.132` port 22 — BITS CSIS, campus network only |
| Account | `yashsinha` — **SHARED** lab account, several students |
| Work dir | `/nfs_home/users/yashsinha/H20250058_Suraj` |
| Hardware | 5 nodes × 2 A100 80GB, 128 CPUs, 240 GB RAM |
| Partitions | `gpu-short` 8h, `gpu-long` 12h, `gpu-1day`, `gpu-3day`, `cpu-short` (default) |
| Limits | **group-wide**: cpu=64, gres/gpu=3, mem=128G, MaxJobs=5 |
| Driver | 570.158.01 = **CUDA 12.8** — cu12x wheels mandatory |
| Stack | Python 3.11, torch 2.11.0+cu128, transformers 5.17.0. **vLLM unusable** |
| Login node | has internet; **compute nodes have NO DNS** |

**Never paste the password into chat.** The researcher runs all cluster commands
(ADR-0010); `ssh` prompts in their own terminal.

### Cluster workflow
```bash
# Mac tab — sync
rsync -av --exclude '.git' --exclude 'hf_cache' --exclude '.conda-env' \
  --exclude '.conda-pkgs' --exclude '.pip-cache' --exclude '.venv' \
  ~/Desktop/SemIntegrity/ yashsinha@172.24.16.132:/nfs_home/users/yashsinha/H20250058_Suraj/

# Cluster tab — activate (once per shell)
cd /nfs_home/users/yashsinha/H20250058_Suraj && module load miniconda/default && \
  source $(conda info --base)/etc/profile.d/conda.sh && conda activate ./.conda-env

# Submit (partition is never hard-coded)
sbatch --partition=gpu-short --gres=gpu:1 --cpus-per-task=8 --mem=64G slurm/<job>.sbatch
```

---

## THE IMMEDIATE NEXT STEP

```bash
sbatch --partition=gpu-short --gres=gpu:1 --cpus-per-task=8 --mem=64G slurm/10_smoke_inference.sbatch
squeue -u yashsinha; cat slurm/logs/semint-smoke-*.out | tail -40
```

Qwen2.5-3B, 8 fixed prompts, full provenance. **This is the first real model
output in the project.** Everything upstream is verified and waiting on it.

Then: `slurm/20_pilot_one_model.sbatch` — 12 constraints × 5 probes → Stage 0 →
D1 → first PSCR number.

---

## Decisions AWAITING THE RESEARCHER

Five methodology ADRs are `PROPOSED — AWAITING RESEARCHER APPROVAL`:
0002 (design lattice), 0003 (probe balancing), 0004 (PyMC backend),
0006 (Gemma-2 preflight), **0012 (transformers not vLLM)**.

Two open methodology questions, both concretely visible in the pilot data:

* **Q21** — is `polarity` inside the probe equivalence key? Currently excluded
  (`EQUIVALENCE_KEY_FIELDS` in `schemas/probe.py`). If included, each constraint
  yields 12 comparable pairs instead of 28.
* **Q22** — is "D0" the pairwise verdict or the set-level one? Both implemented
  and stored.

Also pending: the **1787/1789 discrepancy** on `K-C1-POL-01` and `K-C4-POL-01`
(Wikidata gives the US presidency's inception as 1787; the constraints concern
1789). Both are blocked from EVIDENCE_VERIFIED until adjudicated.

### The professor's notes — UNRESOLVED, possibly significant
From a conversation the researcher only partly remembers: *"Rare"*,
*"Harry Potter or Harry Styles"*, *"Multiple hops"*, *"Competing facts e.g.
President of America"*, *"Tool calling"*, and use cases *"misinformation spread,
toxic content generation"*.

My reading: the last is cheap and strong (§2 framing only). "Competing facts" is
partly already built (C4, and the pilot hit it twice). **"Rare", "Harry
Potter/Harry Styles" and "multiple hops" would each reopen frozen methodology** —
§4.3 deliberately *matches* entity familiarity and *requires* unambiguous ground
truth; those notes point the opposite way. "Tool calling" is effectively a second
study. **Needs checking with the professor before anything is built.**

---

## Working agreement

* **Never fabricate** results, annotations, literature verification, model
  outputs or successful job runs.
* **Methodology vs engineering are separate.** Engineering decisions are taken
  and recorded; methodology decisions are raised in `docs/OPEN_QUESTIONS.md` and
  an ADR, and **never taken unilaterally** (`docs/decisions/README.md`).
* **Verification ladder**: DRAFT → EVIDENCE_VERIFIED → HUMAN_VALIDATED → FROZEN.
  The schema *rejects* HUMAN_VALIDATED without a named human and date.
* No unanchored claims: model revisions, cluster facts and citations are recorded
  only from real artefacts. `PROJECT_STATUS.md` has an integrity ledger.

---

## Bugs found on the cluster that a laptop could not find

Worth knowing, because each has a regression test and the pattern recurs:

1. **scipy absent → validity check FAILED OPEN**, silently passing the
   entity-familiarity confound check it never ran. Now fails closed.
2. **`.gitignore` `models/` unanchored** — hid `configs/models/` (all seven
   model configs *with pinned revisions*) from git for several sessions.
3. **128-core BLAS thread explosion** — stalled at the first `import scipy.stats`.
   All five thread vars now capped before any import.
4. **conda hooks vs `set -u`** — would have killed every Slurm job.
5. **CUDA 13 wheels vs a CUDA 12.8 driver** — only visible on a GPU node.
6. **Env test printed a fatal error and exited 0** — same fail-open pattern as (1).

The recurring lesson: **a check that cannot run has not passed.**

---

## Key files

| Path | What |
|---|---|
| `PROJECT_STATUS.md` | live phase board, blockers, integrity ledger |
| `docs/OPEN_QUESTIONS.md` | 22 questions, 5 resolved |
| `docs/decisions/` | 12 ADRs, each tagged ENGINEERING or METHODOLOGY |
| `docs/CLUSTER_RUNBOOK.md` | every cluster command, classified |
| `docs/PILOT_BENCHMARK_PREVIEW.md` | the 12 constraints for the professor |
| `docs/HUMAN_EFFORT_BUDGET.md` | 5,721 judgements, ≈125 hours |
| `configs/cluster/cluster.yaml` | everything known about the cluster |
| `scripts/benchmark/inspect_pilot.py` | full pilot inspection, read-only |
| `scripts/demo_pipeline.py` | end-to-end demo, no GPU needed |
