# Probe rewrite log

§4.4.5 specifies probe validation in five steps and makes step 4 *"Rewrite or
discard failures; **record the discard rate**"*. This file is that record. Every
rewrite or discard of a probe gets an entry, with what failed, what replaced it,
and what was left unchanged.

A rewrite is **not** a change to the factor design. §4.4.1 defines probe
equivalence on the formal representation — `constraint_id, probe_id,
logical_form, subject, predicate, object, time_scope, quantifier, polarity,
answer_type` — and probe *text* is not part of it. Each entry below therefore
states, as a measured fact rather than an assurance, how many formal
representations changed.

---

## RW-001 — polar-cloze answer-type cue (2026-10-06)

**Decision:** researcher approval A6, Variant A. Recorded as Q24 in
`docs/OPEN_QUESTIONS.md`.

### What failed

| | |
|---|---|
| Split | pilot (→ dev under ADR-0007) |
| Probes in the split | 96 |
| Probes of the failing form (polar cloze) | 28 |
| Probes that failed canonicalisation | **6** |
| Failure rate, whole split | **6 / 96 = 6.25%** |
| Failure rate, within the form | **6 / 28 = 21.4%** |
| Evidence | pilot jobs 11969 and 12095, identical INVALID set in both |

The six, with the response each produced:

| probe | constraint answer type | expected | observed reply |
|---|---|---|---|
| `K-C2-SCI-01-P01` | boolean | YES | `Au` |
| `K-C2-SCI-01-P04` | boolean | YES | `Au` |
| `K-C2-GEO-01-P03` | boolean | YES | `Canberra` |
| `K-C2-GEO-01-P06` | boolean | NO | `CANBERRA` |
| `K-C1-GEO-01-P06` | entity | NO | `Melbourne` |
| `K-C4-SCI-01-P04` | date | YES | `Albert Einstein` |

**Cause.** The frame was `"<assertion>: ___"`. Colon-plus-blank reads as a
`label: value` gloss, so the model supplied what the sentence was *about*: the
echoed token is the assertion's **subject**, not the one adjacent to the blank
(`"...and its atomic number is 79: ___"` → `Au`, not `79`). The declarative
polar frame already carried an explicit `"— YES or NO?"` cue and the
interrogative frame cues a yes/no by its syntax; only cloze carried none, so the
Track A instruction (*"if the expected answer is yes or no, reply with exactly
YES or NO"*) could not fire.

### What replaced it

```
old:  {stem}: ___
new:  The statement "{stem}" is ___.
```

Two call sites, both in `src/semintegrity/probes/surface.py`:
`_frame_author_claim` and `_frame_assembled`, cloze branch, now both delegating
to `_polar_cloze`. Because probe surfaces are generated, the six could not be
fixed individually — the template change regenerates **all 28** probes of the
form. The four *open* cloze probes (`"The {relation} of {subject} is ___."`) are
not polar and are untouched.

### Counts

| | |
|---|---|
| Probes **rewritten** | **28** |
| Probes **discarded** | **0** |
| **Rewrite rate** | **28 / 96 = 29.17%** |
| **Discard rate** | **0 / 96 = 0.00%** |
| Probe ids changed | 0 |
| Constraints changed | 0 |
| Raw model outputs changed | 0 — not read, not written; immutable under ADR-0005 |

### What did not change, measured

Checked by `scripts/benchmark/rewrite_polar_cloze.py`, which refuses to write if
any field other than `probe_text` and `generated_at` differs:

```
probes on disk        : 96
probe_text rewritten  : 28
formal/factor changes : 0
§4.4.1 formal representation unchanged: YES
§4.4.2 surface factors unchanged: YES
```

So the rewrite changed **0 of 96** formal representations and **0 of 96** factor
cells. Every probe occupies the same (syntax, polarity, register,
directionality) cell it did before, and every equivalence class is intact.
Pinned by `tests/unit/test_polar_cloze_wording.py`, which holds all 28 texts as
literals.

### Offline validation

No inference was run. `tests/unit/test_polar_cloze_wording.py`:

* all 28 rewritten texts are pinned exactly;
* the four open-cloze texts are unchanged;
* no probe anywhere still ends in `": ___"`;
* the cued replies (`true`, `false`, `True.`, `FALSE`) **and** `YES`/`NO`
  canonicalise for all 28, with negated probes still inverting — `"true"` is
  already in `_YES_TOKENS` and `"false"` in `_NO_TOKENS`, so **no alias-table
  change was spent** on this (§5.6 keeps that budget for the dev split);
* all six observed failure strings are **still INVALID**, so the rewrite does not
  buy canonicalisation by making Stage 0 permissive.

Residual risks, measured and not hidden: a reply of `"The statement is true"`
canonicalises as INVALID, because `parse_yes_no` deliberately accepts only a
*leading* yes/no token; and `"accurate"` is not in `_YES_TOKENS`. Neither string
appears in the observed data. Widening the token set would be a §5.6 dev-tuning
change and has not been made.

### Outcome — measured 2026-10-07

Pilot run3 on the rewritten probes: **0/96 INVALID = 100.00%** canonicalisation,
against the unchanged ≥95% gate. All six previously-INVALID responses resolved;
no new INVALID appeared. Rewrite rate 29.17%, discard rate 0.00%, and the
rewrite's §4.4.1 guarantee held — 0 of 96 formal representations changed.

One prediction in the section below was wrong and is corrected here:
`K-C4-SCI-01-P04` was described as a "genuine off-target" with no reason to
resolve. It was itself one of the 28 polar-cloze probes, so its wording changed
too, and it resolved. The 95.8% / 99.0% projections below were both low.

### What remained unverified until run3

**Whether a model actually stops echoing the subject.** Canonicalisation is a
property of model responses, and no inference has been re-run — MPS was declined
under A8 and no GPU job was submitted. The observed CANON figure therefore stands
at **6/96 = 93.75%**, still failing the ≥95% gate.

Arithmetic *if* the rewrite works, stated as conditional and not as a result: the
five cue-related failures resolve and `K-C4-SCI-01-P04` (`Albert Einstein`,
genuinely off-target) does not, giving 95/96 = 99.0%. If only the four
subject-echo cases resolve, 92/96 = 95.8%. Both are conditional projections. The
only way to move the gate is to re-run inference on the rewritten probes.
