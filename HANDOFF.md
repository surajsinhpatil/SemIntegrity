# SemIntegrity — session handoff

**Updated 2026-09-26.** Read this, then `PROJECT_STATUS.md`, then
`docs/OPEN_QUESTIONS.md`. `proposal/semintegrity_proposal.docx` is the
authoritative spec and overrides anything here.

---

## The project in one paragraph

**SemIntegrity** — measuring semantic self-inconsistency in LLMs across four
constraint classes (C1 entity, C2 Boolean, C3 relational/quantified, C4
temporal). M.E. dissertation, BITS Pilani, Surajsinh Patil. Classes are
CATEGORICAL, never ordered by difficulty. Target: 120 constraints × K=8 probes ×
7 open-weight models, detectors D0–D4 against blinded human annotation. Factual
accuracy, consistency and abstention stay separate dimensions throughout.

---

## WHERE THINGS ACTUALLY STAND

**Infrastructure is done and verified. The pilot runs. It fails a preregistered
gate, and that is the current work.**

| | |
|---|---|
| Cluster access | ✅ working (researcher runs all commands manually) |
| vLLM 0.11.2, CUDA-12, on Rocky 8.10 / glibc 2.28 | ✅ ADR-0015 |
| A100, bf16, pinned revision, fully offline | ✅ |
| Qwen2.5-3B, 96-probe K=8 pilot | ✅ run TWICE, byte-identical |
| Q21 polarity mapping in production | ✅ PSCR artifact 0.643 → 0.000 |
| **CANON gate (≥95%)** | ❌ **93.75%** |
| D2 / D3 / D4 | ❌ not implemented; D4 method unresolved |
| Human validation | ❌ not started |
| Full benchmark (120 × 8 × 7) | ❌ not run |

**PSCR 0.300 is a pipeline-validation number, not a result about Qwen2.5-3B.**
One model, one detector, no human gold, gate still failing.

---

## The stack that works (ADR-0015)

vLLM 0.19.1 was IMPOSSIBLE here and ADR-0013 had to be superseded: this host is
glibc 2.28, and every CUDA-12 vLLM from 0.12.0 on ships `manylinux_2_31`. The
first `manylinux_2_28` release is 0.22.0, which is already CUDA-13. The only
overlap is the `manylinux1` line.

| component | version |
|---|---|
| vLLM | **0.11.2** (last `manylinux1`; links `libcudart.so.12`) |
| torch | 2.9.0+cu128 |
| transformers | 4.57.6 (`>=4.56,<5`, required by vLLM 0.11.2) |
| Python | 3.11.16 |

Verified from the binary, not the metadata — a wheel's torch pin and its
dependency markers BOTH mislead here; 0.20.0 and 0.21.0 declare no cu13
dependency and link `libcudart.so.13` anyway.

The transformers downgrade was measured before being accepted: Qwen2.5-3B at the
pinned revision renders a byte-identical prompt and the same
`chat_template_hash` (`cd8e9439…`) under 4.57.6 and 5.0.0, confirmed again
against a real model load on the cluster.

---

## Cluster runbook

```bash
# Mac: sync (NEVER use --delete; the cluster holds lock files the Mac does not)
rsync -av --exclude .git --exclude .conda-env --exclude .conda-pkgs \
  --exclude .pip-cache --exclude .tmp --exclude .cache --exclude hf_cache \
  --exclude 'results/' --exclude '*.egg-info' --exclude __pycache__ \
  -e "ssh -o IdentitiesOnly=yes -i $HOME/.ssh/semintegrity_cluster" \
  ~/Desktop/SemIntegrity/ \
  yashsinha@172.24.16.132:/nfs_home/users/yashsinha/H20250058_Suraj/

# Cluster: ALWAYS verify the sync landed before spending a GPU
cd /nfs_home/users/yashsinha/H20250058_Suraj && python -m pytest -q | tail -3

# A fresh pilot MUST set OUT, or resume silently generates nothing
OUT=results/raw/pilot/qwen25-3b-runN.jsonl \
  sbatch --partition=gpu-short --gres=gpu:1 slurm/20_pilot_one_model.sbatch
```

**JIT caches must stay node-local.** Putting Triton/Inductor caches on NFS cost
five SIGSEGV job failures on 2026-09-26. `_common.sh` now sends them to
`$SLURM_TMPDIR/semint-jit-$SLURM_JOB_ID`; only `HF_HOME` and `XDG_CACHE_HOME`
belong in `work_dir`.

---

## DECISIONS WAITING ON THE RESEARCHER

**1. The four polar-cloze probes — blocks the CANON gate.**
`"<assertion>: ___"` does not cue YES/NO, so the model completes the sentence
instead. All six remaining INVALIDs are cloze; four are bare echoes of a noun in
the prompt (`'Au'`, `'Au'`, `'Canberra'`, `'CANBERRA'`). **Confirmed reproducible
across two runs.** They are the only reason canonicalisation is 93.75% rather
than 100%. Rewording touches the factor lattice (ADR-0003). The pilot split is
DRAFT, not frozen, so no freeze blocks it.

**2. entity/date fall-through on polar probes.** Deferred until after the
re-run, which has now happened. Strict rule discards `K-C1-GEO-01-P06`
(`'Melbourne'`), previously a counted contradiction. Allowing fall-through for
entity/date only — where the answer space is disjoint from {YES,NO} and cannot
be confused with a polarity inversion — recovers it: 6 → 5 INVALID, 93.75% →
94.79%. Still short of the gate.

**3. D2 needs the dev split** (ADR-0007: 24 constraints, disjoint from the 120,
unauthored). **D4 needs its `distribution_construction` resolved** (Q5).

Also outstanding from earlier: the 1787/1789 adjudication on the two POL
constraints, a second annotator (~31 h), and the professor's six notes.

---

## Working agreement

* **Never fabricate** results, annotations, model outputs or successful runs.
  Say NOT RUN, PARTIAL or BLOCKED.
* **Methodology vs engineering.** Engineering decisions are taken and recorded;
  methodology goes to `docs/OPEN_QUESTIONS.md` plus an ADR and is never decided
  unilaterally.
* **Verification ladder**: DRAFT → EVIDENCE_VERIFIED → HUMAN_VALIDATED → FROZEN.

---

## Bugs found, and the pattern

1. scipy absent → validity check FAILED OPEN.
2. `.gitignore` `models/` unanchored — hid all seven model configs.
3. 128-core BLAS thread explosion.
4. conda hooks vs `set -u`.
5. CUDA 13 wheels vs a CUDA 12.8 driver.
6. Env test printed a fatal error and exited 0.
7. A config edit whose anchor did not match silently did nothing.
8. **A drift guard that could not fire** — it tested for `"SUPERSEDED"` while
   the ADR said `"superseded"`, so it missed the exact event it existed to catch.
9. **`| head` under `pipefail`** — SIGPIPE killed the installer at exit 141.
10. **A co-installed cu13 wheel deleted cu12's `.so`** on uninstall, leaving a
    recorded package with no files.
11. **The config said tp=2 and the code passed tp=1** — never plumbed through;
    would have OOM'd the 70B after a two-GPU queue wait.
12. **JIT caches on NFS → five SIGSEGV failures.** The run that WROTE the cache
    succeeded; every run that READ it died.
13. **A PSCR artifact of 0.643** — a perfectly consistent model scored as
    two-thirds self-contradictory, because affirmative YES and negated NO were
    recorded as different answers. It did not merely inflate PSCR, it INVERTED
    the per-constraint ordering.

**The recurring lesson:** a check that cannot run has not passed — and a test
can encode a mistake as confidently as a requirement. The test written alongside
bug 12 asserted the caches belong on NFS, and would have rejected the fix.

---

## Key files

| Path | What |
|---|---|
| `PROJECT_STATUS.md` | phase board, blockers, integrity ledger |
| `docs/OPEN_QUESTIONS.md` | 22 questions; Q21 now carries the pilot evidence |
| `docs/Q21_polarity_mapping_spec.md` | the adopted mapping, in full |
| `docs/decisions/ADR-0015-vllm-0112-glibc228.md` | the inference stack |
| `configs/cluster/cluster.yaml` | everything known about the cluster |
| `scripts/analysis/inspect_stage0.py` | why Stage 0 labelled each response |
| `scripts/analysis/compare_runs.py` | run-to-run determinism check |
| `tests/unit/test_perfect_model_invariant.py` | the guard that must never fail |
