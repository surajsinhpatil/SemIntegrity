# Decision records

Two kinds of decision, kept strictly apart. Every ADR declares its kind on the
second line.

## `Kind: ENGINEERING`
How the software is built: layout, file formats, caching, I/O semantics,
tooling, process. **I take these myself** and record them here. They can be
revisited at any time without touching the study's validity.

## `Kind: METHODOLOGY`
Anything that could change what the study measures, what it may claim, or how a
number is computed: benchmark structure, probe semantics, detector definitions,
metric definitions, statistical procedure, model or judge selection, freeze
points, exclusion rules.

**I never take these.** I raise them in
[`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md) with options and a
recommendation, and write the ADR only after the researcher has explicitly
approved it. An unapproved methodology ADR carries `Status: PROPOSED — AWAITING
RESEARCHER APPROVAL` and **no code depending on it is written**.

Where a decision has an engineering surface and a methodological consequence, it
is classified as **METHODOLOGY**. The tie-break is deliberate.

## Index

| ADR | Kind | Decision | Status |
|---|---|---|---|
| 0001 | ENGINEERING | Package layout `src/semintegrity/<module>/` | ACCEPTED |
| 0002 | **METHODOLOGY** | 30 families × 4 classes design lattice | PROPOSED — awaiting approval |
| 0003 | **METHODOLOGY** | Probe-factor balancing at K=8 | PROPOSED — awaiting approval |
| 0004 | **METHODOLOGY** | Beta-binomial backend (PyMC / glmmTMB) | PROPOSED — awaiting approval |
| 0005 | ENGINEERING | Append-only JSONL, create-exclusive manifests, keyed resume | ACCEPTED |
| 0006 | **METHODOLOGY** | Gemma-2 soft-capping preflight gate | PROPOSED — awaiting approval |
| 0007 | **METHODOLOGY** | Separate 24-constraint development set | **APPROVED 2026-09-11** |
| 0008 | **METHODOLOGY** | Open-weight D3 judge (Phi-4 / OLMo-2) | **APPROVED 2026-09-11** |
| 0009 | **METHODOLOGY** | Disaggregated binomial cells | **APPROVED 2026-09-11** |
| 0010 | ENGINEERING | Researcher runs all cluster commands | ACCEPTED |
| 0011 | ENGINEERING | Frozen knowledge-base cache architecture | ACCEPTED |

Status values: `PROPOSED — AWAITING RESEARCHER APPROVAL` · `APPROVED` ·
`ACCEPTED` (engineering only) · `SUPERSEDED BY ADR-nnnn` · `REJECTED`
