# Reproducibility

What is guaranteed, how it is enforced, and what is explicitly *not* claimed.

## What is not claimed

**Determinism.** §4.6 of the proposal is deliberate on this point: batched GPU
inference is subject to kernel and batch-composition non-determinism. The
primary run is described as **fixed-decoding** (temperature 0, fixed seed), never
as deterministic. `configs/inference/determinism_check.yaml` specifies an
empirical check over 100 prompts in two modes — identical batch composition and
shuffled batch composition — and residual variance is reported if present.

**D0 oracularity.** D0's verdict is deterministic *conditional on* correct
formalisation, canonicalisation and knowledge base. Its errors are systematic
and schema-correlated, not random.

## Identifiers

Every id is a pure function of what it names, so the same inputs reproduce the
same ids on any machine (`src/semintegrity/utils/ids.py`).

| Id | Form |
|---|---|
| `family_id` | `F-<domain>-<nn>` |
| `schema_id` | `S-<class>-<nn>` |
| `constraint_id` | `K-<class>-<domain>-<nn>` |
| `probe_id` | `<constraint_id>-P<nn>` |
| `pair_id` | `<constraint_id>-P<a>xP<b>`, canonically ordered |
| `response_id` | `R-<hash of run, model, probe, sample>` — timestamp-free by design |
| `run_id` | `<experiment>-<utc>-<config hash>` |

## Provenance

22 provenance fields are required on every response
(`configs/inference/_provenance.yaml`), including `rendered_prompt`,
`hf_revision_hash`, `chat_template_hash` and the full software version matrix.
The schema rejects a response missing any of them at write time, so a gap is
caught when it happens rather than discovered during analysis.

## Immutability and resume

* raw results: append-only JSONL, `fsync`-ed per batch;
* manifests and config snapshots: create-exclusive (`O_EXCL`) — an existing file
  raises rather than being replaced;
* resume by key `(experiment_id, model_id, probe_id, sample_index)`;
* a truncated final line is tolerated on read; any other malformed line raises.

See `docs/decisions/ADR-0005-immutable-results.md`.

## Freeze points

| Artefact | Frozen before | Recorded as |
|---|---|---|
| Benchmark (constraints + probes) | any test inference | content hash in `results/manifests/` |
| D0 predicates | test-split evaluation | directory hash in `results/manifests/d0_freeze.json` |
| D2 checkpoint + per-class thresholds | test-split evaluation | `configs/detectors/d2_nli.yaml` + manifest |
| D3 judge prompt + judge version | test-split evaluation | `configs/detectors/d3_prompt.txt` + manifest |
| Canonicaliser + alias tables | test-split evaluation | content hash |
| Track B extraction rules | test-split evaluation | content hash |
| Saturation / stochastic / Track B subsets | any output inspection | `scripts/benchmark/select_subsets.py` output + seed |

A CI test compares each live hash against its freeze manifest and fails on drift.

## Environment

Declared constraints live in `requirements/*.in`; exact pins are captured **on
the target node** into `requirements/lock/*.txt`. torch and vLLM are deliberately
unpinned until the cluster CUDA version is known — a guessed pin is not a
reproducible pin.

## Secrets

No password, token or key is ever written to a script, config, notebook, log or
commit. Secrets are read from the environment; `.env` is gitignored and
`.env.example` documents the variables. SSH credentials are entered by the
researcher in their own terminal.

## Release

`scripts/release/build_release.py` assembles the benchmark, formal predicates,
raw outputs, canonicalised answers, detector outputs, human annotations and the
provenance manifest with checksums, for archiving with a DOI. Dataset CC-BY-4.0,
code Apache-2.0.
