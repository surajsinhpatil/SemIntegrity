# ADR-0001 — Repository layout

**Status:** PROPOSED (awaiting sign-off)
**Date:** 2026-09-11

## Context
The brief specifies directories including `src/benchmark/`, `src/probes/`, …
"at minimum". A flat `src/<module>/` layout is not importable as a package
without path hacks, which undermines reproducibility across the laptop, the
login node and Slurm compute nodes.

## Decision
Use a single installable package root: `src/semintegrity/<module>/`, keeping
every module the brief names (`benchmark`, `probes`, `inference`,
`canonicalization`, `detectors`, `knowledge_screen`, `analysis`, `utils`) plus
`schemas`, `kb` and `annotation`.

## Consequences
* `pip install -e .` gives `import semintegrity...` everywhere; Slurm jobs set
  `PYTHONPATH=$SEMINT_ROOT/src` as a fallback.
* One extra path segment versus the brief's listing. No functional difference.
* `detectors/` is further split into `d0/ d1/ d2/ d3/ d4/` so each detector's
  freeze boundary is a directory, which makes "frozen before test evaluation"
  checkable by hashing a directory.
