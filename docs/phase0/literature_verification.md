# Phase 0 — literature verification table

**Status: NOT STARTED.** No citation below has been verified. Nothing in this
table may be cited, and no novelty claim may be written, until its row reads
`VERIFIED` with a real source URL and retrieval date.

Verification is done against ACL Anthology or arXiv directly (§4.12). Raw API
responses are archived under `data/raw/literature/`.

| # | Work as cited in the proposal | Claimed venue/year | Verified venue/year | Identifier | URL | Retrieved | Status |
|---|---|---|---|---|---|---|---|
| 1 | Elazar et al. — ParaRel | TACL 2021 | — | — | — | — | NOT VERIFIED |
| 2 | Kassner et al. — BeliefBank | EMNLP 2021 | — | — | — | — | NOT VERIFIED |
| 3 | Mitchell et al. — ConCoRD | 2022 | — | — | — | — | NOT VERIFIED |
| 4 | Manakul et al. — SelfCheckGPT | EMNLP 2023 | — | — | — | — | NOT VERIFIED |
| 5 | Mündler et al. — self-contradiction | 2023 | — | — | — | — | NOT VERIFIED |
| 6 | Berglund et al. — Reversal Curse | 2023 | — | — | — | — | NOT VERIFIED |
| 7 | LogiConBench | ICLR 2026 | — | — | — | — | **HIGH RISK** |
| 8 | ChaosBench-Logic | (unstated) | — | — | — | — | **HIGH RISK** |
| 9 | REPAIR / "Aligning with Logic" | (unstated) | — | — | — | — | **HIGH RISK** |
| 10 | Tsujimura et al. — JSD belief consistency | ACL 2026 | — | — | — | — | **HIGH RISK** |
| 11 | Flip-Flop Consistency | ACL 2026 | — | — | — | — | **HIGH RISK** |
| 12 | "Logical Consistency as a Bridge" | ACL 2026 | — | — | — | — | **HIGH RISK** |

## Why rows 7–12 are flagged high risk

They are cited to very recent venues, they are the works that most directly
constrain the contribution claims (§2.2 "four consequences follow directly"),
and three of them are load-bearing for specific design choices:

* **Tsujimura et al.** is the stated precedent for D4 — if the citation does not
  hold, D4's positioning in §4.8.6 must be rewritten.
* **LogiConBench** is named "the principal positioning challenge" in §A.3.
* **ChaosBench-Logic** is what "rules out any claim to be first on that axis".

A mis-stated venue, a preprint-only status or a title drift in any of these
changes what the paper may claim. They are verified first.

## Outputs of this phase

* this table, completed;
* `positioning.md` — the final positioning statement, written only against
  VERIFIED rows;
* `novelty_risk.md` — for each claimed contribution in §5, the nearest prior
  work found and an assessment of how much of the claim survives.
