# ADR-0011 — Frozen, content-addressed knowledge-base cache

**Kind:** ENGINEERING

**Status:** ACCEPTED (engineering)
**Date:** 2026-09-11

## Context
Two facts constrain how ground truth is resolved.

* **Compute nodes have no network.** The cluster rules put all heavy work behind
  Slurm, and compute nodes may have no outbound access. A D0 predicate that
  needs a Wikidata lookup at evaluation time would fail there.
* **Wikidata changes.** A constraint verified in September and re-verified in
  December can silently differ. §4.3 already requires source, URL and retrieval
  date per constraint; the same discipline has to apply to every lookup the code
  makes, not just the ones a human wrote down.

## Decision
All knowledge-base access goes through a content-addressed disk cache with three
modes:

| Mode | Behaviour | Where |
|---|---|---|
| `LIVE` | fetch on miss, write to cache | login node / laptop |
| `FROZEN` | never fetch; a miss raises `CacheMiss` | Slurm jobs, reproduction |
| `REFRESH` | re-fetch, archiving the prior entry beside it | deliberate re-verification |

Entries are keyed by `sha256({kind, request})` and store the request, the raw
payload, the fetch timestamp and the source URL. `MANIFEST.json` records a hash
per entry, so tampering, loss and untracked additions are all detectable.

`REFRESH` **archives rather than overwrites** (`<hash>.superseded-<ts>.json`), so
the knowledge base the study used remains recoverable even after re-verification.

## Consequences
* Slurm jobs run with `HF_HUB_OFFLINE=1` and a `FROZEN` cache — no job can be
  slowed, rate-limited or silently changed by a live API.
* The snapshot is a releasable artefact and goes in the §5.6 DOI archive.
* Snapshotting is a deliberate login-node step (`scripts/benchmark/snapshot_kb.py`)
  rather than something that happens by accident during analysis.
* A frozen-mode miss is a loud error naming the missing key and the expected
  path, because the alternative — a silent fallback to the network — would make
  "which knowledge base produced this result" unanswerable.
