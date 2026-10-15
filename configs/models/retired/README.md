# Retired model configs

Removed from the evaluated roster on **2026-10-15** by researcher decision.
Kept rather than deleted: each carries a pinned 40-hex revision, which is
provenance. A future run that wants one of these back should move it up a
directory, not re-derive the pin.

The loaders glob `configs/models/*.yaml` non-recursively, so nothing here is
picked up by `resolve_model_config`, the readiness audit or the tests.

| model | why retired |
|---|---|
| `llama33-70b` | 141 GB of weights against ~52 GB of usable quota on a shared 1 TB account. Could not be staged at all; see `configs/cluster/cluster.yaml:storage`. Dropping it narrows the scale axis from 3B-70B to 3B-14B, which must be stated in the write-up. |
| `gemma2-9b` | Dropped with the roster reduction. Also carried `hazard.preflight_status: NOT_RUN` (ADR-0006 soft-capping gate), which was never cleared. |
| `llama31-8b` | Replaced by `olmo2-7b` to keep an AI2 lineage in the evaluated set. |
