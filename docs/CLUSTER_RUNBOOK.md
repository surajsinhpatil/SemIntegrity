# Cluster runbook — the one-model pilot

Every command you will run, in order, each classified before you run it.
**You run all of these** (ADR-0010). Nothing here is executed from the assistant
session, and no command asks for a password, token or key to be typed into a chat.

Legend — **R** read-only · **W** writes files (repo only) · **D** downloads ·
**S** submits a Slurm job · **N** needs network

---

## The cluster

| | |
|---|---|
| Host | `172.24.16.132` (BITS CSIS cluster — Dell R7525, NVIDIA A100) |
| SSH port | 22 |
| Username | *your cluster account — not your Mac username* |
| Working dir | `/nfs_home/users/yashsinha/H20250058_Suraj` |

`172.24.x.x` is a private address, so this is reachable only from the college
network or over the VPN.

**The password is never recorded here, in any script, or in this repository.**
`ssh` prompts for it in your own terminal each time.

## Step 0 — get the repository onto the cluster

```bash
rsync -av --exclude '.git' --exclude 'hf_cache' --exclude '.venv' \
  ~/Desktop/SemIntegrity/ CLUSTERUSER@172.24.16.132:/nfs_home/users/yashsinha/H20250058_Suraj/
```
`W` on the cluster, inside your designated directory only · no Slurm · no download.

Substitute your **cluster** username. Omitting `CLUSTERUSER@` makes SSH fall back
to your local Mac username, which is the most common cause of a rejected login.

---

## Step 1 — cluster probe  ← **the one that unblocks everything**

```bash
cd /nfs_home/users/yashsinha/H20250058_Suraj && bash scripts/cluster/probe_cluster.sh
```

**`R` + `W` (one file in the repo) + `N` (three HTTPS HEAD requests).
No Slurm job. No download. No installation.**

It runs `hostname`, `sinfo`, `sacctmgr show associations`, `squeue`, `df`,
`quota`, `module avail`, `nvidia-smi`, `nvcc --version`, `which R`, and three
`curl` status checks against Wikidata and Hugging Face. Every command is a query;
none creates, modifies or deletes anything outside this repository.

It writes exactly one file: `docs/phase0/cluster_probe_<timestamp>.md`, and
prints it to your terminal.

**Send me that file (or paste its contents) and I will fill in
`configs/cluster/cluster.yaml`.** It resolves 14 of the 16 remaining
unresolved markers — partitions, GPU models, VRAM, CUDA/driver, module system,
quota, whether the login node has internet, and whether R exists (which settles
the GLMM backend question, Q8).

---

## Step 2 — build the environment  *(after I have configured from the probe)*

Exact commands depend on the probe (conda vs venv vs modules), so I will write
this step once I see the report. It will be `W` + `D` (Python packages only,
no model weights) on the **login node**.

---

## Step 3 — pre-flight, locally on the login node

```bash
cd /nfs_home/users/yashsinha/H20250058_Suraj && make check
```
`R` + `W` (caches only) · no Slurm · no download. Runs config validation, lint
and 205 unit tests. **Must pass before anything is submitted.**

---

## Step 4 — cache the one model's weights

```bash
cd /nfs_home/users/yashsinha/H20250058_Suraj && \
HF_HOME="$PWD/hf_cache" python -c "
from huggingface_hub import snapshot_download
snapshot_download('Qwen/Qwen2.5-3B-Instruct',
                  revision='aa8e72537993ba99e69dfaafa59ed015b17504d1')
"
```

**`D` — downloads ≈ 6 GB. `N`. No Slurm. Login node, by design**
(§4.13: weights are cached once from a non-GPU session, never inside GPU time).

> The revision above is the **real pinned SHA**, already resolved from the Hub
> and recorded in `configs/models/qwen25-3b.yaml`. Run
> `python scripts/models/pin_revisions.py` (`R`+`N`, metadata only) to confirm it.

**Qwen2.5-3B-Instruct is not gated**, so this needs no licence acceptance and no
`HF_TOKEN`. That is why it is the one-model choice: it removes the longest
external dependency from the critical path. The Llama, Gemma and Mistral
downloads still need your licence acceptance, but not for this pilot.

Check quota first if the probe reports one is tight:
```bash
df -h /nfs_home/users/yashsinha/H20250058_Suraj
```
`R`.

---

## Step 5 — environment test on a real compute node

```bash
sbatch --partition=<FROM PROBE> --gres=gpu:1 slurm/00_env_test.sbatch
```

**`S` — submits a Slurm job. `R`+`W` (log files only). No download, no model load.**
15 min, 4 CPUs, 16 GB. Verifies imports, GPU visibility, **bf16 support** (§4.6
requires it), and re-runs the unit tests on the node.

Partition is **not** hard-coded anywhere — a guessed partition name produces a job
that queues forever. Pass it on the command line; it overrides the `#SBATCH`
directives.

```bash
squeue -u $USER                      # R
cat slurm/logs/semint-envtest-<jobid>.out   # R
```

---

## Step 6 — smoke test: the first real inference

```bash
sbatch --partition=<FROM PROBE> --gres=gpu:1 slurm/10_smoke_inference.sbatch
```

**`S`. `W` (`results/raw/_smoke/*.jsonl` + a manifest + logs). No download**
(weights are already cached from step 4). 40 min, 8 CPUs, 64 GB, 1 GPU.

One model, 8 fixed prompts containing **no benchmark content**, so it runs before
any constraint is authored. It prints each response, confirms all 22 provenance
fields are populated, shows the fully rendered prompt, and checks the model's
declared system-role support against its real chat template.

This is the deliverable that demonstrates the pipeline works on real hardware.

---

## Step 7 — one-model pilot  *(blocked on constraint approval)*

```bash
sbatch --partition=<FROM PROBE> --gres=gpu:1 slurm/20_pilot_one_model.sbatch
```

**`S`. `W`. No download.** 1 h, 1 GPU.

Runs 12 pilot constraints × 5 probes on one model, then Stage 0 and D1, and
writes `results/analysis/pilot_qwen25-3b.json`.

**Blocked until you approve the 12 pilot constraints.** The job checks for
`data/benchmark/pilot/constraints.jsonl` and exits with code 2 rather than
burning an allocation if it is absent.

---

## What is NOT in this runbook

Deliberately excluded, per your instructions and the phase gates:

* downloading any model other than Qwen2.5-3B;
* the full 120-constraint benchmark;
* D2 (NLI), D3 (judge) or D4 — the one-model pilot uses Stage 0 and D1 only;
* the saturation, stochastic and Track B tiers;
* anything that would need human annotation.

---

## Safety properties built into these scripts

| Risk | Guard |
|---|---|
| Inference started on the login node | `smoke.py` and `run_pilot.py` exit unless `SLURM_JOB_ID` is set |
| A guessed partition wasting queue time | no partition is hard-coded; it must be passed explicitly |
| Job killed by walltime losing work | append-only JSONL with `fsync`; re-submitting resumes and never duplicates |
| Weights downloaded inside paid GPU time | compute jobs run `HF_HUB_OFFLINE=1` |
| Unpinned model silently substituted | `VLLMBackend` refuses to load without a real 40-hex revision |
| Results silently overwritten | manifests are create-exclusive; raw JSONL is append-only |
| Fake output mistaken for a result | stub responses carry a `stub://` model id and analysis refuses them |
| Caches polluting shared space | `HF_HOME` is forced inside your working directory |

---

# Part 2 — the PRIMARY run (added 2026-10-08)

The pilot sections above are unchanged and still correct. This part covers the
**frozen 120-constraint benchmark**: 960 probes × 7 models = **6,720
generations** (`configs/inference/primary.yaml`).

**You run every command here** (ADR-0010). Nothing below is executed from the
assistant session, and no cluster fact is asserted without your pasted output.

## Before anything: sync and re-verify

The cluster copy is behind — construction finished on 2026-10-08 and the
benchmark records changed.

| | command | class |
|---|---|---|
| 1 | `rsync -av --exclude '.git' --exclude '.ruff_cache' --exclude 'hf_cache' --exclude 'results' ./ <user>@172.24.16.132:/nfs_home/users/yashsinha/H20250058_Suraj/` | W |
| 2 | `python scripts/cluster/verify_implementation.py` | R |
| 3 | `python -m pytest -q` | R |
| 4 | `python -m semintegrity.benchmark.validate --split test --k 8 --strict-lattice` | R |

Expected: **33 PASS · 0 FAIL** · **1096 passed / 1 skipped** on the Mac
(**1095 / 2** on the cluster, because the sync excludes `.git` and
`test_no_source_directory_is_hidden_by_gitignore` skips without a checkout) ·
validate reports **120 constraints, 960 probes** with **0 errors**.

**NEVER `rsync --delete`.** And lint explicit directories on the login node —
`ruff check src scripts tests`, never bare `ruff check .`.

## Staging weights, one model at a time

The readiness audit records **244 GB of weights against 286 GB of SHARED
headroom**. The seven models do not coexist on disk. Stage one, run it, evict
it, stage the next.

```bash
# LOGIN NODE ONLY — compute nodes have no internet.
# CORRECT PATH AND FORM. The script takes a POSITIONAL short name and lives
# under scripts/models/, not scripts/env/. An earlier revision of this
# runbook said `scripts/env/cache_weights.sh --model <name>`, which does not
# exist; following it staged nothing and jobs 13032/13033 died at preflight 2.
df -h /nfs_home/users/yashsinha | tail -1                  # R  CHECK SPACE FIRST
bash scripts/models/cache_weights.sh <short-name>          # D, N
python scripts/models/verify_cache.py <short-name>         # R, offline
```

`verify_cache.py` is the **offline** check and is what the job preflight calls. **Check free space before downloading:** 7B is ~15 GB and 14B ~28 GB, and a quota exhaustion lands the small JSON files while silently dropping every `.safetensors` shard — which is exactly how 13032/13033 failed.
`cache_weights.sh --check` hits the network and must never run on a compute node.

## The run — one job per model

**STAGE AND VERIFY FIRST.** `cache_weights.sh` now ends by running the offline
verifier, so it exits non-zero on a half-populated cache. Never submit a job for
a model whose staging did not print `USABLE OFFLINE`.

```bash
# every model except the 70B (1 GPU). Partition named, not guessed:
# gpu-short has an 8 h limit and the header asks for 6 h.
MODEL=qwen25-7b sbatch --partition=gpu-short --gres=gpu:1 slurm/30_primary_one_model.sbatch

# llama33-70b ONLY (2 GPUs; tensor_parallel_size=2). gpu-1day for the 24 h limit.
MODEL=llama33-70b sbatch --partition=gpu-1day --gres=gpu:2 --time=24:00:00 \
    slurm/30_primary_one_model.sbatch
```

**SERIALISE. Do not submit several at once.** `GrpTRES mem=128G` is an
**aggregate** limit over the whole shared `faculty` account. At the old 64G two
jobs summed to exactly 128G and starved every labmate — that is why 13032/13033
pended 8 h with `Reason=AssocGrpMemLimit`. The header is now 32G (measured; see
the script's comment), so two fit, but chain them anyway so a failure stops the
line instead of wasting the next slot:

```bash
JOB=$(MODEL=qwen25-7b sbatch --parsable --partition=gpu-short --gres=gpu:1 \
        slurm/30_primary_one_model.sbatch)
MODEL=qwen25-14b sbatch --dependency=afterok:$JOB --partition=gpu-short \
        --gres=gpu:1 slurm/30_primary_one_model.sbatch
```

**The account has 2 GPUs, not 3** (re-observed 2026-10-14:
`cpu=64,gres/gpu=2,mem=128G`, `MaxTRES gres/gpu=2`). So `llama33-70b` at tp=2
consumes the entire account GPU allowance and cannot run beside any other GPU
job of ours. Run it alone, last.

Submit in this order, cheapest first, so a configuration error surfaces on a
3B model rather than after a 70B allocation:

`qwen25-3b` → `mistral7b-v03` → `qwen25-7b` → `llama31-8b` → `gemma2-9b` →
`qwen25-14b` → `llama33-70b`

The job refuses rather than burning GPU time when:

| exit | preflight |
|---|---|
| **9** | **the allocated GPU is already occupied, or CUDA cannot create a context** |
| 3 | the test benchmark fails `--strict-lattice` |
| 4 | the weights are not in the offline cache |
| 5 | the resolved run plan is inconsistent |
| 6 | `tensor_parallel_size` exceeds the GPUs Slurm gave it |
| 7 | inference itself failed |
| 8 | the finished file holds fewer than 960 records |

**Exit 9 is contention, not a bug in your config.** `ConstrainDevices=no` on this
cluster means cgroups do not fence GPUs between jobs, so a co-tenant process can
hold the A100 you were allocated. `gpu_memory_utilization=0.90` needs ~90% of the
card free, so the preflight refuses below 80% and prints `nvidia-smi` plus the
PIDs already on the device. Resubmit, or target a node whose GPUs are idle.
Jobs 14935 and 14956 died this way *after* passing every other preflight, and
their logs did not record the GPU state — which is why this check now exists.

**Resume is on, and it cuts both ways.** The runner resumes on
`(experiment_id, model_id, probe_id, sample_index)`, so a walltime kill is
restartable — but a deliberate re-run against a complete file generates nothing.
For a genuinely fresh run, name a new output:

```bash
OUT=results/raw/primary_trackA/qwen25-3b-rerun2.jsonl MODEL=qwen25-3b sbatch ...
```

## Outputs to expect

| path | what |
|---|---|
| `results/raw/primary_trackA/<model>.jsonl` | 960 records, one per probe, 22 provenance fields each |
| `slurm/logs/semint-primary-<jobid>.{out,err}` | provenance block + per-stage log |

## Then paste back

For each model, paste: the job's provenance block, the final
`N record(s) in …` line, and

```bash
wc -l results/raw/primary_trackA/*.jsonl
```

Analysis is run from the repo once the raw files exist:

```bash
python scripts/analysis/evaluate_primary.py \
    --raw results/raw/primary_trackA/*.jsonl \
    --split test \
    --out-dir results/analysis/primary_trackA
```

That writes `statistics.json`, `per_constraint.csv`, `metrics_by_model.csv` and
`MANIFEST.json` (with input/output checksums). It **refuses stub output** unless
`--allow-stub`, which stamps every artefact `NOT_REAL`.

## What the evaluation will and will not report

* **Reported:** Stage 0 labels with the CANON gate, D0 and D1, per-constraint
  PSCR/PCS/truth-accuracy/abstention, the descriptive four-class profile, the two
  pre-specified confirmatory contrasts (cluster bootstrap over constraints, BCa,
  10,000 replicates, seed 20250058), and paired cross-model contrasts.
* **NOT reported, by refusal in code:** D2 (checkpoint unselected, thresholds
  uncalibrated — needs dev human labels), D3 (no judge run yet), D4 (Q5/ADR-0016
  unresolved), and every detector precision/recall/F1/AUPRC (no human gold).
