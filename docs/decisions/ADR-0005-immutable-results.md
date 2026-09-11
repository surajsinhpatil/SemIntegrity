# ADR-0005 — Immutable results and resume semantics

**Kind:** ENGINEERING

**Status:** ACCEPTED (implemented)
**Date:** 2026-09-11

## Context
"Raw model outputs should be immutable once generated" and "never overwrite
experimental results silently", against a cluster where jobs are killed by
walltime and must resume.

## Decision
* Raw results are **append-only JSONL**, `fsync`-ed per batch.
* Resume is by key `(experiment_id, model_id, probe_id, sample_index)`; completed
  keys are read from the existing file and skipped.
* Config snapshots and manifests use **create-exclusive** writes
  (`O_EXCL`): an existing file raises `ImmutabilityError` rather than being
  replaced.
* A truncated final line (job killed mid-write) is tolerated on read; any other
  malformed line raises, because silently skipping a corrupt record would
  quietly change a result.
* Response ids are content-addressed and deliberately exclude the timestamp, so
  a duplicate is detectable rather than silently doubled.

## Consequences
Re-submitting a killed job is always safe and never duplicates work.
Implemented in `src/semintegrity/utils/io.py`; tested in `tests/unit/test_io.py`.
