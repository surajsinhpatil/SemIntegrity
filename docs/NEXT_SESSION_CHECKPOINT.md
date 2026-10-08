# SemIntegrity — session checkpoint (2026-10-08)

> ## CONSTRUCTION COMPLETE — 2026-10-08 (supersedes the block below it too)
>
> **The benchmark is 132/132 and construction validation passes in full.**
> Q29 is RESOLVED by researcher option (a): coverage matrix **Revision 5**
> re-themed four (axis, domain) cells and **Revision 6** re-themed the fifth,
> axis 3 / biology. Every replacement was a WIDENING, so **no authored C1/C2/C3
> cell was re-authored or discarded**.
>
> | | |
> |---|---|
> | test | **120 / 120** · 960 probes · 48 EVIDENCE_VERIFIED · 72 DRAFT |
> | dev | **12 / 12** · 96 probes · 3 EVIDENCE_VERIFIED · 9 DRAFT |
> | pilot | 12 · 96 probes · byte-identical, untouched |
> | evidence | **313 / 313 checks passed, 0 failed** |
> | axis-5 universes | **20 / 20** frozen (12 enumerated · 8 ranked_source) |
> | lattice | **every rule PASS**, incl. schema x domain FULLY CROSSED |
> | readiness | **15 PASS · 1 FAIL · 2 BLOCKED** — the FAIL is GPU storage, not construction |
>
> **THE ONE REMAINING CONSTRUCTION-ADJACENT GAP:** 81 constraints are
> `corroboration_required` and **0** have a qualifying second source, so 81 sit
> at DRAFT. Mechanism built, policy configured (8 providers), 5 sources already
> frozen and verified. See Q28 for the multi-event axis-4 case, still OPEN.
>
> **NEXT PHASE IS HUMAN VALIDATION — not started, deliberately.** No annotators,
> no gold labels, no IAA, nothing HUMAN_VALIDATED, nothing FROZEN, no GPU run.
> **Still nothing committed.**
>
> Three ADRs from earlier on 2026-10-08 remain the governing ones: **ADR-0020**
> (C4 evidence routes), **ADR-0021** (computed ranked_source — never `NOW()`),
> **ADR-0022** (taxonomic-authority measure). Evidence readers added this day:
> `claim_point_in_time` (P585) and `claim_qualifier_time` (any time-valued
> qualifier, e.g. P574 on P225). Both have tests that they FIRE and that an
> unparseable or missing date reads as ABSENT, never as an invented year.
>
> ---
>
> ## EARLIER UPDATE — 2026-10-08 (now partly stale: it reports 126/132)
>
> **Everything below this block was written on 2026-10-07 and its authoring and
> corroboration numbers are STALE.** The 2026-10-07 text says "Authored so far: 4
> of 132" and calls the corroboration policy "the ONE BLOCKER / unconfigured".
> Both are out of date. The traps, tooling, working agreement and CANON sections
> below remain accurate and are still worth reading.
>
> ### Authoring — 126 of 132
>
> | | |
> |---|---|
> | test | **115 / 120** constraints · 920 probes · 48 EVIDENCE_VERIFIED · 67 DRAFT |
> | dev (new) | **11 / 12** constraints · 88 probes · 3 EVIDENCE_VERIFIED · 8 DRAFT |
> | pilot | 12 constraints · 96 probes · unchanged, byte-identical |
> | evidence | **287 / 287 checks passed, 0 failed** |
> | comparison universes | **19** frozen (11 enumerated · 8 ranked_source) |
> | corroborating sources | **5**, all verified against the frozen store |
>
> ### Corroboration policy is CONFIGURED, not blocking
>
> ADR-0019 was approved 2026-10-07 with **8 providers** (crossref, un-treaties,
> govinfo, nasa, standards-body, official-gazette, taxonomic-authority,
> national-archives) and a witness rule. The fetcher
> (`kb.fetchers.HttpDocumentFetcher`) and store (`kb.corroboration`) both work —
> 5 WoRMS artefacts were retrieved, frozen and verified on 2026-10-08. What
> remains is that **75 cells are DRAFT because no second source has been
> attached to them yet**, which is work, not a blocker. See Q28 (still OPEN) for
> the multi-event axis-4 case.
>
> ### Three ADRs approved 2026-10-08 — read before authoring
>
> * **ADR-0020** — a C4 temporal anchor may be any of the 8 check kinds, not only
>   P580/P582. `design.yaml`'s `temporal_qualifiers_required` is **read by zero
>   lines of code**, and the FROZEN pilot's C4 cells plus 5 authored test cells
>   already use `claim_time`/`claim_literal`. This unblocked 14 cells.
> * **ADR-0021** — a **computed** (duration) ranking is a valid ADR-0018
>   `ranked_source`. ADR-0018 is NOT amended; its `query` field already provides
>   for it. New registered query `office_holders_ranked_by_duration` v1.
>   **It must never contain `NOW()`** — an open-ended term is closed against a
>   frozen literal date in the query text, or the ranking is not reproducible.
>   This unblocked F-HIS-15 and F-POL-15 (8 cells).
> * **ADR-0022** — an axis-5 `measure_value` may come from an ADR-0019-approved
>   provider when Wikidata records the measure unusably. This unblocked F-BIO-15
>   (4 cells) via WoRMS body size. **Wikidata morphometry is not usable for this:**
>   P2067 gives a 581 kg emu, a 95 kg Asian elephant and an 800 kg jaguar.
>
> ### New code (both small, both tested)
>
> `claim_point_in_time` reads the **P585** qualifier, which no check could read
> before — an assessment (conservation status, measurement, census) is dated by
> P585 and has no validity interval. Added on the same terms as
> `claim_interval_end`. 5 tests, including one pinning that **deep time reads as
> ABSENT, never as a fabricated year**.
>
> ### THE REMAINING BLOCKER — Q29, and it needs a decision
>
> **Six C4 cells have no machine-checkable date in Wikidata, and ADR-0002's
> lattice is saturated — so it is valid only at exactly 120.** There is no
> defensible benchmark at 115. Five lattice rules fail until all six are filled:
>
> ```
> K-C4-BIO-11  K-C4-BIO-12  K-C4-BIO-13  K-C4-BIO-03 (dev)   taxonomy: deep time only (-10^6..-10^7)
> K-C4-GEO-15                                                 Kilimanjaro has NO dated statement at all
> K-C4-SCI-11                                                 SI redefinitions undated; IPK has P571, no P576
> ```
>
> **Do not fill these by anchoring on `on focus list of Wikimedia project` or
> other curation metadata** — that makes the gold a fact about Wikidata's
> editorial process. **Do not author `K-C4-SCI-11` from the IPK's 1889 inception**
> — the answer is then contained in its own question.
>
> Q29 in `docs/OPEN_QUESTIONS.md` has the full diagnosis and four options;
> recommendation is **(a) re-theme the five affected Revision-4 matrix cells**,
> scoped so the 15 already-verified C1/C2/C3 cells of those families survive.
> That is a **design change** and is not taken unilaterally.
>
> ### Validation as of 2026-10-08
>
> `1054 passed / 1 skipped` · ruff clean · mypy **19 errors (unchanged baseline)**
> · `make check` PASS · implementation verifier **33 PASS / 0 FAIL** · pilot
> **byte-identical** · readiness **14 PASS / 2 FAIL / 2 BLOCKED** · probe sets
> PASS (8 per constraint, all 8 factor cells once, no duplicate text) ·
> `dev_test_disjoint` PASS · `cross_split_ids` PASS · `corroboration_freeze` PASS
> · `sitelink_matching` PASS (p=0.756) · `answer_type_allocation` PASS (115/115).
>
> **Still nothing committed.** Still no human validation. Still no GPU run.


Read, in order: this file → `HANDOFF.md` → `docs/RESULTS_STATUS.md` →
`docs/AUTHORING_PLAN.md` → `docs/OPEN_QUESTIONS.md`.
`proposal/semintegrity_proposal.docx` is authoritative and overrides everything else.

## Project

**SemIntegrity** — measuring semantic self-inconsistency in LLMs across four
constraint classes (C1 entity, C2 Boolean, C3 relational/quantified, C4
temporal). M.E. dissertation, BITS Pilani. Classes are **categorical**, never
ordered by difficulty. Accuracy, consistency and abstention stay **separate
dimensions**.

I run every cluster command manually and paste output back (ADR-0010).
**Do not assume you can reach the cluster, and do not drive SSH from the agent.**

## Repo state

HEAD is still `09e15ac`. **61 files changed, NOTHING COMMITTED** — the whole of
2026-10-06/07 is uncommitted in the working tree.

`990 passed / 1 skipped` · ruff clean · `make check` PASS · mypy 19 errors (all
pre-existing) · 34 configs valid · readiness audit **12 PASS · 2 FAIL · 4
BLOCKED** · implementation verifier **33 PASS · 0 FAIL** · authoring plan
**8/8** · pilot **byte-identical**.

Cluster is behind. Sync + verify before any GPU:
`python scripts/cluster/verify_implementation.py` (expect 33 PASS · 0 FAIL) and
`python -m pytest -q` (expect **990 passed / 1 skipped** on the Mac; **989/2** on
the cluster, because the sync excludes `.git` and
`test_no_source_directory_is_hidden_by_gitignore` skips without a git checkout).

## THE ONE BLOCKER

**The corroboration policy is unconfigured, and 81 of 132 constraints cannot be
promoted past DRAFT until it is.**

§4.3 requires "all historical and temporal facts are corroborated against a
second authoritative source". The **mechanism is built and enforced**
(`src/semintegrity/kb/corroboration.py`,
`configs/benchmark/corroboration_policy.yaml`). What is missing is the
**methodology decision**:

1. Which external providers count as independent authoritative sources?
2. What is the `independence_criterion` — what makes a source independent of
   Wikidata?
3. May a Wikidata reference / P248 "stated in" value ever count? **Currently
   excluded, deliberately not assumed.**

Until `approved_independent_providers` is non-empty AND
`independence_criterion` is stated, every corroboration is rejected and the
system reports: *"corroboration mechanism implemented; approved independent
source policy not yet configured"*. That is the correct state, not a bug.
A fetcher adapter should not be written until providers are chosen, because the
adapter's shape follows from the choice.

## Decisions taken 2026-10-06/07 (all researcher-approved)

| | |
|---|---|
| ADR-0002 lattice | **APPROVED** — 30 families × 4 classes, 6 schemas × 5 instances |
| ADR-0003 probe factors | **APPROVED** — resolves Q2 |
| ADR-0007 dev set | **APPROVED** + amended: 12 new dev cells adopted (axis 2/history, axis 3/biology, axis 4/sci-tech) |
| ADR-0017 answer type | **APPROVED 2026-10-06, AMENDED 2026-10-07** |
| ADR-0018 comparison universe | **APPROVED + AMENDED 2026-10-07** |
| CANON | **FROZEN 2026-10-07 at 100.00% (0/96)** |

**ADR-0017 as amended — answer type is a function of (axis, class):**
C1 and C4 keep the axis-fixed allocation; **C2 and C3 are `boolean` on every
axis**. Why: `probes.surface.realise` routes a direct+affirmative probe of an
entity/date-answered constraint through `_realise_open`, which requires a single
binary subject-relation-object. A conjunction (C2) and a universal (C3) have
none. The original axis-only rule blocked 44 constraints and produced text like
*"The country it's the capital of of Brasília is ___."*
Cost, recorded: confirmatory contrast C1+C2 vs C3+C4 stays **balanced (0.556 vs
0.556)**; four-class descriptive profile carries a **0.111** spread; answer type
is a **covariate, never a factor**. D0's `ANCHOR` reach narrowed 8 → 4 schemas.

**ADR-0018 as amended** — `ComparisonUniverse` records the asserted extremal
bearer explicitly (`argmax_qid`, `argmax_label`, `direction` max|min), because
axis 5 is boolean so `gold_answer` is YES/NO and is not the bearer of anything.
`rank_of_gold` was **renamed to `rank_of_argmax`** (approved; do not rename
again). No member or bearer may be labelled YES/NO.

## CANON — frozen, do not touch

| | |
|---|---|
| Observed | **0/96 INVALID = 100.00%**, run3, post-rewrite |
| Gate (unchanged) | ≥95% → **PASS** |
| Variant A wording | `The statement "<stem>" is ___.` |

All six previous INVALIDs resolved, no new ones. Provenance: researcher-reported
from the cluster; the evaluator output was not pasted into the session.
**The 94.79% / 5-INVALID figure is a SIMULATION under an unadopted fall-through
rule** and is labelled as such in `docs/Q21_polarity_mapping_spec.md` §7.
Entity/date fall-through is **still OPEN and now unexercised** (0 INVALID means
no live instance).

## Authoring status

**Manifest:** `data/benchmark/authoring_manifest.json` — 132 rows, allocation
only (no facts). 120 test + 12 dev · C1/C2/C3/C4 = 33 each · 144 at freeze ·
1,056 new primary probes (960 test + 96 new dev) · the existing **96 pilot probes
stay separate** · 81 corroboration-required · 20 axis-5 (comparison universe) ·
24 schemas · 33 families. Test cell indices **11–16**, dev **02–04**, pilot
**01** — the id grammar has no split field, so this is the only thing keeping
them apart.

**Authored so far: 4 of 132.** Family `F-GEO-11` ("the capital city of Brazil"),
in `data/benchmark/test/candidates.yaml`, 8/8 evidence checks passing, replayable
from the FROZEN cache:

| | status |
|---|---|
| `K-C1-GEO-11` | EVIDENCE_VERIFIED |
| `K-C2-GEO-11` | EVIDENCE_VERIFIED |
| `K-C3-GEO-11` | EVIDENCE_VERIFIED |
| `K-C4-GEO-11` | **DRAFT** — corroboration required, none possible yet |

**Nothing written to `data/benchmark/test/constraints.jsonl` or `probes.jsonl`.**
A 4-of-120 split would fail every lattice gate; the records rebuild from
`candidates.yaml` + the frozen cache.

**LIVE Wikidata fetching is approved** (ADR-0011 LIVE mode, laptop/login node).
The client throttles to 1 request/second.

## Authoring workflow that works

```
candidate constraint + candidate QIDs → build(fetch_evidence=True,
promote_on_evidence=True, cache_mode=LIVE, split=TEST, tier=PRIMARY)
→ fetcher verifies → wrong candidates stay DRAFT → correct from fetched values
```

**My candidate-QID error rate was about 1 in 4.** Two real errors the fetcher
caught: I proposed `Q119251` for the Federal District (actual `Q119158`), and
wrote the Brasília handover as 1960-04-**21** (Wikidata: 1960-04-**22**). I had
also invented a start date of 1763; Wikidata records **no P580**, so the field is
`null`. **Fetch entity data BEFORE writing candidates** rather than guessing and
repairing — that is the main throughput lesson.

## Infrastructure built 2026-10-06/07

* **6 authoring gates, all running from the production path**
  (`python -m semintegrity.benchmark.validate`, the Slurm preflight):
  factor-cell completeness · duplicate probe text (hard failure) ·
  second-source corroboration · cross-split id uniqueness ·
  split disjointness (reports **VACUOUS**, explicitly not a pass) ·
  comparison universe. Each has a test that it **fires**, not just that the
  pilot passes.
* **24 per-schema D0 registrations** (`schema_registrations.py`) — no new
  detection logic. 2 behaviours: `EXCL` (all 24) and `ANCHOR` (4: `s_c1_04`,
  `s_c4_04`, `s_c1_06`, `s_c4_06`). All 12 C2/C3 schemas carry `N/A-struct`:
  their structure is **not decidable from a Track A response**, which is a design
  fact, not missing code.
* **`claim_interval_end`** — reads the P582 end qualifier. Nothing could before,
  which structurally blocked axis 6. Implements an existing §4.3 requirement.
* **SPARQL registry** moved to `configs/kb/sparql_queries.yaml` — 6 named,
  versioned, parameterised queries; values validated against `^Q\d+$`/`^P\d+$`
  so injection is refused. A test asserts no `SELECT…WHERE` with `wdt:` exists
  anywhere in `src/` or `scripts/`. The legacy `capitals_of_canberra` text is
  **byte-identical to the cached request** — DO NOT RE-INDENT, or a FROZEN replay
  becomes a live re-query.
* **`benchmark/ordering.py`** — pins `constraint_index` (which fixes every
  probe's syntax) to the records, not source-file order.
* **Builder and validator share one corroboration policy** so they cannot
  disagree about what a promotion requires.

## Tooling

| script | does |
|---|---|
| `scripts/propose_coverage_matrix.py` | regenerates the Revision 4 matrix |
| `scripts/propose_authoring_plan.py --manifest …` | regenerates the 132-row manifest; `--check` runs 8 plan checks |
| `scripts/cluster/verify_implementation.py` | 33 content-fingerprint checks; run on Mac **and** cluster, outputs must match |
| `scripts/models/verify_cache.py` | **offline** cache check. `cache_weights.sh --check` hits the network — do not use it on a compute node |
| `scripts/analysis/evaluate_cloze_rewrite.py` | evaluates a fresh pilot run; reads the CANON threshold from config |
| `scripts/benchmark/rewrite_polar_cloze.py --check` | proves the pilot is byte-identical |

## STILL OPEN — do not close without explicit approval

1. **Corroboration policy** (the blocker above).
2. **Q5 / ADR-0016** — D4 `distribution_construction`. `OPEN — AWAITING
   RESEARCHER DECISION`.
3. **Q22** — D0 pairwise vs set-level reporting. `AWAITING APPROVAL`.
4. **entity/date fall-through** on polar probes — open, now unexercised.
5. **Human validation** — NOT STARTED. No annotators, no gold, no IAA.

## Remaining audit FAIL / BLOCKED

* **FAIL** — 120-constraint benchmark unauthored (4 of 132 done).
* **FAIL** — storage: 244 GB of weights vs 286 GB **shared** headroom. Models
  must be staged one at a time and evicted.
* **BLOCKED** — GPU facts (only Qwen2.5-3B has ever loaded; six models never
  tried) · human validation · cross-split id check (vacuous until a second split
  exists) · corroboration policy.

## Traps that have cost real time

1. **JIT caches must stay node-local.** Triton/Inductor on NFS caused five
   SIGSEGVs. Only `HF_HOME` and `XDG_CACHE_HOME` belong in `work_dir`.
2. **A fresh pilot MUST set `OUT=`** or the runner resumes and generates nothing.
3. **rsync NEVER with `--delete`.** Also: `.ruff_cache` is gitignored but **not**
   rsync-excluded, so a macOS-built cache ships to the cluster. Add
   `--exclude .ruff_cache`.
4. **`ruff check .` on the login node** aborts — the conda env lives *inside* the
   repo and the cluster copy has no `.git`, so `.gitignore` cannot exclude it and
   ruff lints the stdlib. Lint explicit dirs: `ruff check src scripts tests`.
5. **`model_copy(update=…)` skips validation** and can leave a plain `str` where
   an enum belongs. Validators use `str(...)`, not `.value`.
6. **`NonEmptyStr` is `min_length=1`**, so `"   "` passes. Blank-strip explicitly.

## Working agreement

**Never fabricate** results, annotations, QIDs, sitelinks, observed values,
dates, quantities or source metadata — say NOT RUN, PARTIAL or BLOCKED.
**Engineering decisions:** take and record them. **Methodology:** goes to
`docs/OPEN_QUESTIONS.md` + an ADR, never decided unilaterally. A check that
cannot run has **not** passed; BLOCKED ≠ PASS. A test can encode a mistake as
confidently as a requirement. Commits end with
`Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Next moves

**A. Configure the corroboration policy** (the unblock). Decide providers +
independence criterion, record an ADR, then I write one adapter and resume
authoring. Unblocks 81 of 132 constraints.

**B. Author the 51 constraints that need no corroboration** while A is pending.
These can reach EVIDENCE_VERIFIED today. 132 − 81 = 51.

**C. Commit.** 61 files of approved, validated work is uncommitted. Worth
landing before anything else.

**D. Sync + re-verify on the cluster** (33 PASS · 0 FAIL, 989/2 tests there).
