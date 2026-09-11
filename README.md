# SemIntegrity

**Measuring Semantic Self-Inconsistency in Large Language Models Across
Structured Integrity Constraints**

A multi-model study of constraint structure, detection budget, and contradiction
detection. M.E. Computer Science research project, BITS Pilani.

> **Authoritative specification:** `proposal/semintegrity_proposal.docx` (v2).
> The proposal governs. Where this repository resolves something the proposal
> underdetermines, the resolution is recorded in `docs/decisions/` and the
> underlying ambiguity in `docs/OPEN_QUESTIONS.md`.

---

## What the study measures

Three quantities, jointly, because none is interpretable alone:

1. how semantic self-inconsistency under meaning-preserving probes varies across
   four structured integrity-constraint classes;
2. how reliable automated contradiction detectors remain across those classes,
   measured against blinded human judgement;
3. how many meaning-preserving probes are needed before an existing
   inconsistency surfaces.

Factual accuracy, consistency and abstention are held apart throughout: a model
that is reliably wrong and a model that is unreliable are different failure
modes.

**Scope of the claim.** This is an *output-level behavioural* study. It does not
claim that observed contradictions originate in parametric memory.

---

## Design at a glance

| | |
|---|---|
| Constraint classes | C1 atomic · C2 conjunctive/relational · C3 quantified · C4 temporal — **categorical conditions, not an ordered scale** |
| Benchmark | 120 constraints = 30 families × 4 classes, 5 domains, 6 per (domain, class) |
| Probes | K = 8 → 960 probes, 28 pairs per constraint; factors balanced exactly at class level |
| Saturation tier | 24 constraints at K = 50, evaluated at k ∈ {2,4,8,16,32,50} |
| Models | Llama-3.1-8B · Mistral-7B-v0.3 · Qwen2.5-7B · Gemma-2-9B · Qwen2.5-3B · Qwen2.5-14B · Llama-3.3-70B, all bf16, pinned revisions |
| Detection | Stage 0 canonicalisation → D0 symbolic · D1 exact match · D2 NLI · D3 pairwise LLM judge · D4 distributional (exploratory, **never** a detector) |
| Gold standard | blinded human annotation, two annotators, adjudicated |
| Primary endpoint | **PSCR**; independent unit is the **constraint**, tested by cluster bootstrap |

---

## Repository layout

```
configs/       frozen specification: project, models, inference, detectors, analysis, annotation, cluster
data/          raw · interim · processed · benchmark (dev/test/pilot/saturation) · annotations
src/semintegrity/
               schemas · benchmark · probes · kb · inference · canonicalization
               detectors/{d0,d1,d2,d3,d4} · knowledge_screen · annotation · analysis · utils
scripts/       cluster probing, env, model pinning, benchmark authoring, detectors, analysis
slurm/         job templates (rendered with real partitions after the cluster probe)
tests/         unit · integration · fixtures
results/       raw (immutable) · canonicalized · detectors · analysis · figures · manifests
docs/          BLUEPRINT · IMPLEMENTATION_PLAN · OPEN_QUESTIONS · decisions/ · prereg/ · phase0/
```

---

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Everything above runs on a laptop or a login node. It installs **no** torch and
starts **no** model.

### On the cluster

```bash
bash scripts/cluster/probe_cluster.sh
```

Read-only reconnaissance: partitions, GPUs, quota, modules, CUDA, network
reachability. It submits nothing and downloads nothing. Its report fills in
`configs/cluster/cluster.yaml`, after which the Slurm job scripts can be
rendered with real partition names.

**Login-node rule.** The login node is for editing, git, lightweight commands,
job status and `sbatch`. All CPU- and GPU-heavy work goes through Slurm;
`scripts/_guard_login_node.sh` enforces this.

---

## Reproducibility guarantees

* **Content-addressed identifiers** — every constraint, probe, pair, response
  and run id is a pure function of its inputs.
* **Full provenance** — 24 required fields per response, including the fully
  rendered prompt, model revision, chat-template hash and the whole software
  version matrix.
* **Immutable raw results** — append-only JSONL with `fsync`; manifests written
  create-exclusive; resume by key so a killed job never duplicates work.
* **Frozen artefacts** — benchmark, D0 predicates, D2 thresholds, D3 prompt and
  extraction rules are hashed and frozen before test evaluation.
* **Nothing fabricated** — model revisions, cluster facts, literature
  verification, annotations and results are recorded only from real artefacts.
  `PROJECT_STATUS.md` carries an integrity ledger of what is *not* yet backed by
  one.

---

## Status

See [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for the live phase board, blockers
and decisions, and [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md) for the
open methodological questions.

## Licence

Code: Apache-2.0 (`LICENSE`). Dataset, on release: CC-BY-4.0 — Wikidata is CC0,
so derived constraints can be released permissively.
