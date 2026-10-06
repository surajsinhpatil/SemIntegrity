# SemIntegrity — session checkpoint (2026-10-06)

Paste this at the start of a new chat. Then read, in order:
`HANDOFF.md` → `docs/RESULTS_STATUS.md` → `docs/OPEN_QUESTIONS.md`.
`proposal/semintegrity_proposal.docx` is authoritative and overrides everything else.

---

## Project

**SemIntegrity** — measuring semantic self-inconsistency in LLMs across four
constraint classes (C1 entity, C2 Boolean, C3 relational/quantified, C4
temporal). M.E. dissertation, BITS Pilani. Classes are **categorical**, never
ordered by difficulty. Target: 120 constraints × K=8 probes × 7 open-weight
models, detectors D0–D4 against blinded human annotation. Accuracy, consistency
and abstention stay **separate dimensions** throughout.

I (the researcher) run every cluster command manually and paste output back.
**Do not assume you can reach the cluster.**

## Repo state at checkpoint

- HEAD `8b9c0d9`, working tree clean, **473 passed / 1 skipped**, ruff clean, 32 configs valid.
- The cluster copy is BEHIND: it has not been synced since commit `81a9585`.
  **First action in a new session: sync, then verify, before anything else.**

## What is DONE

- Full infrastructure chain: cluster access → env audit → vLLM install → A100 →
  Qwen2.5-3B → smoke → 96-probe K=8 pilot → D0/D1.
- **All five detectors implemented and tested** (D0, D1, D2, D3, D4).
- Analysis layer: PSCR, PCS, Consistency@K, AOCR, truth accuracy, abstention,
  Recovery@k, D0/D1 coverage, cluster bootstrap (BCa), BH-FDR, per-class/domain
  aggregation, ADR-0009 pair-factor cells, detector P/R/F1/AUPRC interfaces.
- Pilot run TWICE, **96/96 byte-identical** across two days and two nodes.

## What is NOT done

- **Human validation — NOT STARTED.** No annotators, no gold, no IAA.
- **120-constraint benchmark — NOT AUTHORED.** Only the 12-constraint pilot exists.
- Six of seven models never loaded.
- PyMC beta-binomial fit; knowledge-screen analysis.
- Preregistration not submitted.

## THE CRITICAL FACTS

**Inference stack (ADR-0015).** vLLM **0.11.2** · torch 2.9.0+cu128 ·
transformers 4.57.6 · Python 3.11.16. vLLM 0.19.1 was IMPOSSIBLE here: the host
is glibc 2.28 and every CUDA-12 vLLM from 0.12.0 ships manylinux_2_31. Verified
by reading `DT_NEEDED` from the wheels — metadata misleads in both directions.

**Canonicaliser v1.1 (Q21 polarity mapping) is adopted.** Before it, a
*perfectly self-consistent* model scored PSCR **0.643** and the per-constraint
ordering was INVERTED. It is now 0.000, guarded by
`tests/unit/test_perfect_model_invariant.py`.
**Any number produced before v1.1 is uninterpretable.**

**Pilot numbers are DIAGNOSTIC, not results.** Canonicalisation 93.75%
(**FAILS** the ≥95% CANON gate), D1 PSCR 0.300 / coverage 0.551, D0 PSCR 0.209 /
coverage 0.485, truth accuracy 0.767, abstention 0.188. One model, no human
gold, failing gate. **Never present these as findings about Qwen2.5-3B.**

## TRAPS THAT HAVE ALREADY COST GPU JOBS

1. **JIT caches must stay node-local.** Putting Triton/Inductor caches on NFS
   caused **five SIGSEGV job failures**. `_common.sh` now sends them to
   `$SLURM_TMPDIR/semint-jit-$SLURM_JOB_ID`. Only `HF_HOME` and
   `XDG_CACHE_HOME` belong in `work_dir`.
2. **A fresh pilot MUST set `OUT=`** or the runner resumes and generates
   nothing, silently. One allocation was lost to this.
3. **Always verify a sync landed before spending a GPU.** Another allocation was
   lost to a stale script.
4. **rsync must NEVER use `--delete`** — the cluster holds lock files the Mac
   does not. Delete stale files explicitly instead.

## Cluster runbook

```bash
# 1. Mac: sync
rsync -av --exclude '.git' --exclude '.venv' --exclude '.conda-env' \
  --exclude '.conda-pkgs' --exclude '.pip-cache' --exclude '.tmp' \
  --exclude '.cache' --exclude 'hf_cache' --exclude 'results/' \
  --exclude '*.egg-info' --exclude '__pycache__' --exclude '.pytest_cache' \
  --exclude '.ruff_cache' --exclude '.DS_Store' --exclude '.coverage' \
  -e "ssh -o IdentitiesOnly=yes -i $HOME/.ssh/semintegrity_cluster" \
  ~/Desktop/SemIntegrity/ \
  yashsinha@172.24.16.132:/nfs_home/users/yashsinha/H20250058_Suraj/

# 2. Cluster: VERIFY before any GPU job (expect 472 passed / 2 skipped)
cd /nfs_home/users/yashsinha/H20250058_Suraj && python -m pytest -q | tail -3

# 3. Readiness audit (read-only, no GPU)
python scripts/audit_benchmark_readiness.py
```

`yashsinha` is a **shared lab account**. Write only inside
`H20250058_Suraj`. `squeue -u yashsinha` shows other people's jobs — filter on
the `semint-` prefix. Never `scancel` a job you did not submit.

## Decisions WAITING ON ME (do not take these unilaterally)

1. **The polar-cloze probes — blocks the CANON gate.** All six remaining
   INVALIDs are cloze; four are bare echoes of a noun in the prompt. Confirmed
   reproducible across two runs. Rewording touches the frozen factor lattice
   (ADR-0003). The pilot split is DRAFT, not frozen, so nothing mechanically
   blocks it.
2. **entity/date fall-through on polar probes.** Deferred pending the re-run,
   which has now happened. Recovers one real contradiction
   (`K-C1-GEO-01-P06` → `'Melbourne'`): 6 → 5 INVALID, 93.75% → 94.79%.
   Still short of the gate.
3. **Q5 / D4 `distribution_construction` — see ADR-0016.** Narrowed to
   `softmax(mean_logprob / T)`; only `T` is open. Blocks D4 and nothing else.

## Detector status

| detector | code | can run? |
|---|---|---|
| D0 symbolic | ✅ tested | ✅ runs against the frozen KB |
| D1 exact match | ✅ tested | ✅ |
| D2 NLI | ✅ tested | ❌ no checkpoint chosen, no calibrated thresholds — **needs human gold** |
| D3 judge | ✅ tested | ⚠️ judge decided (phi-4, pinned, ADR-0008); never executed |
| D4 distributional | ✅ tested | ❌ Q5 unresolved (ADR-0016) |

D2's threshold and D4's distribution mapping **raise** rather than fall back to
a default, so neither can produce a number by accident.

## Working agreement

- **Never fabricate** results, annotations, model outputs or successful runs.
  Say NOT RUN, PARTIAL or BLOCKED.
- **Methodology vs engineering.** Engineering decisions are taken and recorded;
  methodology goes to `docs/OPEN_QUESTIONS.md` plus an ADR and is **never**
  decided unilaterally.
- A check that cannot run has **not** passed. BLOCKED ≠ PASS.
- A test can encode a mistake as confidently as a requirement — one I wrote
  asserted the caches belong on NFS and would have rejected its own fix.
- Commits end with: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`

## Suggested next moves (pick one)

- **A.** Author the remaining 108 constraints. §4.13 calls authoring the binding
  resource, not GPU time. Biggest unblock, needs no decision from me.
- **B.** Resolve the cloze question, then re-run the pilot to clear CANON.
- **C.** Implement the PyMC beta-binomial model + knowledge-screen analysis
  (the last two analysis gaps).
- **D.** Build the human-annotation infrastructure (sampling, blinding,
  adjudication, IAA) without running it — unblocks D2 the moment labels exist.
