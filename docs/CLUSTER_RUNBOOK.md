# Cluster runbook — the one-model pilot

Every command you will run, in order, each classified before you run it.
**You run all of these** (ADR-0010). Nothing here is executed from the assistant
session, and no command asks for a password, token or key to be typed into a chat.

Legend — **R** read-only · **W** writes files (repo only) · **D** downloads ·
**S** submits a Slurm job · **N** needs network

---

## Step 0 — get the repository onto the cluster

```bash
rsync -av --exclude '.git' --exclude 'hf_cache' --exclude '.venv' \
  ~/Desktop/SemIntegrity/ <user>@<cluster-host>:/nfs_home/users/yashsinha/H202500058_Suraj/
```
`W` on the cluster, inside your designated directory only · no Slurm · no download.
Replace `<user>@<cluster-host>` with your login. Your terminal will ask for
credentials; nothing is stored.

---

## Step 1 — cluster probe  ← **the one that unblocks everything**

```bash
cd /nfs_home/users/yashsinha/H202500058_Suraj && bash scripts/cluster/probe_cluster.sh
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
cd /nfs_home/users/yashsinha/H202500058_Suraj && make check
```
`R` + `W` (caches only) · no Slurm · no download. Runs config validation, lint
and 205 unit tests. **Must pass before anything is submitted.**

---

## Step 4 — cache the one model's weights

```bash
cd /nfs_home/users/yashsinha/H202500058_Suraj && \
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
df -h /nfs_home/users/yashsinha/H202500058_Suraj
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
