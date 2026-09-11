# ADR-0010 — Cluster interaction model

**Kind:** ENGINEERING

**Status:** ACCEPTED (researcher, 2026-09-11)
**Date:** 2026-09-11

## Decision
**The researcher runs all cluster commands.** I prepare exact, reviewable
commands and scripts; the researcher executes them in their own terminal and
returns the output. No SSH session is driven from this environment.

## Rationale
* Credentials are entered only into the researcher's own terminal, never into a
  chat, a script, a config or a log.
* Every command that touches the cluster is reviewed by a human before it runs —
  which matters most for the commands that cost GPU hours or disk quota.
* Keeps the "never modify other users' folders / shared environments / system
  packages" rule enforceable by inspection.

## Consequences
* Slower iteration on cluster-specific debugging; batched, self-contained
  scripts are preferred over interactive probing.
* Every cluster script must be **idempotent, read-only by default, and verbose**,
  so one run yields everything needed rather than requiring a round trip per fact.
* Results come back as pasted text or files; I never assert a cluster fact I have
  not seen in that output.
