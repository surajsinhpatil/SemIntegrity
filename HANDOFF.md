# SemIntegrity — session handoff

**Updated 2026-09-25, 21:00 IST.** Read this, then `PROJECT_STATUS.md`, then
`docs/OPEN_QUESTIONS.md`. `proposal/semintegrity_proposal.docx` is the
authoritative spec and overrides anything here.

---

## The project in one paragraph

**SemIntegrity** — measuring semantic self-inconsistency in LLMs across four
structured integrity-constraint classes (C1 atomic, C2 conjunctive, C3
quantified, C4 temporal). M.E. dissertation, BITS Pilani, Surajsinh Patil.
Three quantities measured jointly: how inconsistency varies by constraint class,
how reliable the detectors are per class, and how many meaning-preserving probes
are needed to surface an inconsistency. Factual accuracy, consistency and
abstention are kept as separate dimensions throughout. Target: 120 constraints
× K=8 probes × 7 open-weight models, detectors D0–D4 against blinded human
annotation.

---

## WHAT WE ARE DOING RIGHT NOW

Getting the **first real model output**. One command:

```bash
cd ~/Desktop/SemIntegrity && python -m semintegrity.inference.smoke --model qwen25-3b --out results/raw/_smoke/local-mps.jsonl
```

Runs on the MacBook's Apple M4 GPU via MPS. First run downloads Qwen2.5-3B
(~6 GB, ungated, no token) into `hf_cache/` — that is the slow part. Then 8 real
prompts with full 22-field provenance.

If that works, the pilot follows immediately:

```bash
python -m semintegrity.inference.run_pilot --model qwen25-3b --split pilot --out results/raw/pilot/qwen25-3b-mps.jsonl
python -m semintegrity.analysis.pilot_report --raw results/raw/pilot/qwen25-3b-mps.jsonl --split pilot --out results/analysis/pilot_mps.json
```

That is 12 constraints × 8 probes → Stage 0 → D1 → **the first PSCR number**.

---

## The two-track approach (important)

| | Machine | Purpose | Status |
|---|---|---|---|
| **Development** | MacBook Air M4, 16 GB | authoring, pilots, Qwen2.5-3B, all analysis | **working now** |
| **Final results** | BITS CSIS cluster, A100 80GB | all 7 models, uniform hardware, Phase 6 | **access blocked** |

**Results from the Mac must never appear in the paper** (ADR-0013). Merging is
technically trivial — append-only JSONL keyed by
`(experiment_id, model_id, probe_id, sample_index)` — but different kernels give
different numerics, and inconsistency is the dependent variable. If Qwen-3B ran
on MPS while 7B and 14B ran on CUDA, the within-family scale axis would be
confounded with hardware, which is the one comparison it exists to make.
Provenance records `apple-mps:Apple M4` vs the A100, so mixing is detectable.

Only Qwen2.5-3B (6.2 GB) fits in 16 GB. Quantising the others is forbidden by
§4.6 — it would confound quantisation with model family.

---

## Cluster — currently unreachable

| | |
|---|---|
| Host | `172.24.16.132` port 22, campus network only |
| Account | `yashsinha` — **SHARED** lab account (Aadit, Swayam, Vineet, Harsh) |
| Work dir | `/nfs_home/users/yashsinha/H20250058_Suraj` |
| Hardware | 5 nodes × 2 A100 80GB, 128 CPUs, 240 GB RAM |
| Limits | **group-wide**: cpu=64, gres/gpu=3, mem=128G, MaxJobs=5 |
| Driver | 570.158.01 = **CUDA 12.8** — cu12x wheels mandatory |
| Env there | Python 3.11, torch 2.11.0+cu128, transformers 5.17.0, built and tested |
| Model | Qwen2.5-3B cached at the pinned revision |

**Blocked since ~18:30 IST on 2026-09-25.** Port 22 refuses; the subnet gateway
`172.24.16.1` pings fine, so it is a firewall rule on the host, not a dead
machine or a network outage. Almost certainly fail2ban after a mistyped username
earlier.

Poll without attempting a login (a failed attempt can restart a ban timer):
```bash
nc -G 8 -vz 172.24.16.132 22
```

To unblock: ask a labmate to try from their machine (tells you whether it is your
IP or the host); ask **Yash Sinha**, whose account it is, who administers the
cluster; or try a different campus IP.

**Never paste the cluster password into chat.** The researcher runs all cluster
commands (ADR-0010).

### Cluster workflow when access returns
```bash
# Mac tab
rsync -av --exclude '.git' --exclude 'hf_cache' --exclude '.conda-env' \
  --exclude '.conda-pkgs' --exclude '.pip-cache' --exclude '.venv' \
  ~/Desktop/SemIntegrity/ yashsinha@172.24.16.132:/nfs_home/users/yashsinha/H20250058_Suraj/

# Cluster tab — once per shell
cd /nfs_home/users/yashsinha/H20250058_Suraj && module load miniconda/default && \
  source $(conda info --base)/etc/profile.d/conda.sh && conda activate ./.conda-env

# Submit (partition is never hard-coded in the job files)
sbatch --partition=gpu-short --gres=gpu:1 --cpus-per-task=8 --mem=64G slurm/10_smoke_inference.sbatch
```

---

## State

**20 commits · 259 tests passing · ruff clean · installed editable on the Mac**

Done:
* **Phase 0 literature verification** — 12/12 citations resolved (7 verified,
  4 venue corrections, 1 preprint). `docs/phase0/literature_verification.md`.
* **Phase 1 infrastructure** — schemas with a verification ladder, design
  validator, Wikidata client + frozen cache, D0 framework with freeze policy and
  three-instance audit, probe factor generator.
* **Pilot benchmark** — 12 constraints, 96 probes, real records in
  `data/benchmark/pilot/`. All **DRAFT**: 21/21 Wikidata checks pass, no human
  review, nothing frozen.
* **Stage 0 canonicaliser, D1 detector, inference runner** with resume.
* **Cluster fully configured** (when reachable).

Not done:
* **No model output yet. Zero experimental results.**
* No human annotation (~5,721 judgements — `docs/HUMAN_EFFORT_BUDGET.md`).
* The 120-constraint benchmark is not authored.
* D2 (NLI), D3 (judge), D4 (distributional) not implemented.
* No preregistration submitted.

---

## HOW WE PROCEED FROM HERE

**1. Now — first model output (Mac).** Smoke test → pilot → first PSCR. No
dependencies on anyone.

**2. Then — D2 (NLI).** The NLI model is ~1.5 GB and runs fine on the Mac.
Needs a dev split to calibrate thresholds on (ADR-0007: 24 constraints, disjoint
from the 120 — not yet authored).

**3. When the cluster returns** — re-run the pilot on the A100 to confirm the
Mac and cluster agree, then the remaining six models.

**4. Blocked on the researcher** (any time, no cluster needed):
   * approve or reject the pending ADRs
   * decide **Q21** and **Q22**
   * adjudicate the **1787/1789** discrepancy on the two POL constraints
   * check the professor's six notes with him
   * identify a second annotator (~31 hours of their time)

**5. Phase 5** — author the full 120-constraint benchmark. The largest human
effort, and the real critical path. §4.13 says so outright: the binding resource
is authoring and annotation, not GPU time.

---

## Decisions AWAITING THE RESEARCHER

Six methodology ADRs are `PROPOSED — AWAITING RESEARCHER APPROVAL`:
0002 (design lattice), 0003 (probe balancing), 0004 (PyMC — forced, no R on the
cluster), 0006 (Gemma-2 preflight), **0012 (transformers not vLLM)**,
**0013 (MPS for development only)**.

Two open methodology questions, both concretely visible in the pilot data:
* **Q21** — is `polarity` inside the probe equivalence key? Currently excluded
  (`EQUIVALENCE_KEY_FIELDS` in `schemas/probe.py`). Including it drops each
  constraint from 28 comparable pairs to 12.
* **Q22** — is "D0" the pairwise verdict or the set-level one? Both implemented
  and stored, so the decision can wait for data.

**The 1787/1789 discrepancy**: Wikidata gives the US presidency's inception as
1787; `K-C1-POL-01` and `K-C4-POL-01` concern 1789. Both are blocked from
EVIDENCE_VERIFIED until a human adjudicates.

**The professor's notes** — from a conversation the researcher only partly
remembers: *"Rare"*, *"Harry Potter or Harry Styles"*, *"Multiple hops"*,
*"Competing facts e.g. President of America"*, *"Tool calling"*, and use cases
*"misinformation spread, toxic content generation"*. My reading: the use cases
are cheap and strong (§2 framing only); "competing facts" is partly already
built; **"rare", "Harry Potter/Harry Styles" and "multiple hops" would each
reopen frozen methodology** — §4.3 deliberately *matches* entity familiarity and
*requires* unambiguous ground truth, and those point the other way; "tool
calling" is effectively a second study. **Confirm with the professor before
building on any of it.**

---

## Working agreement

* **Never fabricate** results, annotations, literature verification, model
  outputs or successful job runs.
* **Methodology and engineering are separate.** Engineering decisions are taken
  and recorded; methodology decisions are raised in `docs/OPEN_QUESTIONS.md`
  plus an ADR and **never taken unilaterally** (`docs/decisions/README.md`).
* **Verification ladder**: DRAFT → EVIDENCE_VERIFIED → HUMAN_VALIDATED → FROZEN.
  The schema *rejects* HUMAN_VALIDATED without a named human and date.
* `PROJECT_STATUS.md` carries an integrity ledger of claims not yet backed by an
  artefact.

---

## Bugs found so far, and the pattern

1. **scipy absent → validity check FAILED OPEN**, silently passing the
   entity-familiarity confound check it never ran.
2. **`.gitignore` `models/` unanchored** — hid all seven model configs, with
   their pinned revisions, from git for several sessions.
3. **128-core BLAS thread explosion** — stalled at the first `import scipy.stats`.
4. **conda hooks vs `set -u`** — would have killed every Slurm job.
5. **CUDA 13 wheels vs a CUDA 12.8 driver** — only visible on a GPU node.
6. **Env test printed a fatal error and exited 0** — same fail-open pattern as (1).
7. **A config edit whose anchor did not match silently did nothing**, leaving
   `backend: vllm` contradicting ADR-0012 until a run failed.

Recurring lesson: **a check that cannot run has not passed**, and **an edit that
matches nothing is an error, not a no-op**. Each now has a regression test.

---

## Key files

| Path | What |
|---|---|
| `PROJECT_STATUS.md` | live phase board, blockers, integrity ledger |
| `docs/OPEN_QUESTIONS.md` | 22 questions, 5 resolved |
| `docs/decisions/` | 13 ADRs, each tagged ENGINEERING or METHODOLOGY |
| `docs/CLUSTER_RUNBOOK.md` | every cluster command, classified |
| `docs/PILOT_BENCHMARK_PREVIEW.md` | the 12 constraints, for the professor |
| `docs/PILOT_EXAMPLES.md` | 3 worked examples with all 8 probes each |
| `docs/HUMAN_EFFORT_BUDGET.md` | 5,721 judgements, ≈125 hours |
| `configs/cluster/cluster.yaml` | everything known about the cluster |
| `scripts/benchmark/inspect_pilot.py` | full pilot inspection, read-only |
| `scripts/demo_pipeline.py` | end-to-end demo, no GPU needed |
