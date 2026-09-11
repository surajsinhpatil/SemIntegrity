# Phase 0 — literature verification table

**Status: COMPLETE for all 12 works cited in Appendix A.3.**
Verified 2026-09-11 against ACL Anthology, OpenReview, PMLR, ICLR/ICML
proceedings and arXiv. Raw evidence in `data/raw/literature/`.

Status values: `VERIFIED` (as cited) · `CORRECTED` (real work, citation needs
fixing) · `PREPRINT` (real, but not a confirmed peer-reviewed venue) ·
`NOT_FOUND`.

| # | Work | Cited as | Verified as | Identifier | Status |
|---|---|---|---|---|---|
| 1 | Elazar et al. — ParaRel | TACL 2021 | TACL 2021, 9:1012–1031 | [2021.tacl-1.60](https://aclanthology.org/2021.tacl-1.60/) · arXiv 2102.01017 | **VERIFIED** |
| 2 | Kassner et al. — BeliefBank | EMNLP 2021 | EMNLP 2021, pp. 8849–8861 | [2021.emnlp-main.697](https://aclanthology.org/2021.emnlp-main.697/) · arXiv 2109.14723 | **VERIFIED** |
| 3 | Mitchell et al. — ConCoRD | "2022" | **EMNLP 2022** | [2022.emnlp-main.115](https://aclanthology.org/2022.emnlp-main.115/) · arXiv 2211.11875 | **CORRECTED** (venue now named) |
| 4 | Manakul et al. — SelfCheckGPT | EMNLP 2023 | EMNLP 2023, pp. 9004–9017 | [2023.emnlp-main.557](https://aclanthology.org/2023.emnlp-main.557/) | **VERIFIED** |
| 5 | Mündler et al. — self-contradiction | "2023" | **ICLR 2024** | arXiv [2305.15852](https://arxiv.org/abs/2305.15852) | **CORRECTED** — 2023 is the preprint year |
| 6 | Berglund et al. — Reversal Curse | "2023" | **ICLR 2024** | arXiv [2309.12288](https://arxiv.org/abs/2309.12288) · [ICLR proceedings](https://proceedings.iclr.cc/paper_files/paper/2024/hash/5178b2f2d7c44aa390c0777dc77b3f0c-Abstract-Conference.html) | **CORRECTED** — 2023 is the preprint year |
| 7 | LogiConBench | ICLR 2026 | ICLR 2026 (poster, 23 Apr 2026); Chen, Zhou, Cheng, Yip, Liu, Wang et al. | [OpenReview ULEHJkolxB](https://openreview.net/pdf?id=ULEHJkolxB) | **VERIFIED** |
| 8 | ChaosBench-Logic | (unstated) | **arXiv / OpenReview preprint — no confirmed peer-reviewed venue** | v1 arXiv 2601.01982 · v2 arXiv [2605.24305](https://arxiv.org/abs/2605.24305) · [OpenReview 3buGJj1xxA](https://openreview.net/forum?id=3buGJj1xxA) | **PREPRINT** |
| 9 | REPAIR / "Aligning with Logic" | (unstated) | **ICML 2025**; Liu et al. | arXiv [2410.02205](https://arxiv.org/abs/2410.02205) · [PMLR v267](https://proceedings.mlr.press/v267/liu25u.html) | **CORRECTED** (venue now named) |
| 10 | Tsujimura et al. | ACL 2026 | ACL 2026, pp. 40032–40055. Full title: *Assessing the Belief Consistency of Large Language Models on the Logical Conversation Process*. Tsujimura, Rikters, Asada, Egami, Ishigaki, Yano, Takamura | [2026.acl-long.1860](https://aclanthology.org/2026.acl-long.1860/) | **VERIFIED** |
| 11 | Flip-Flop Consistency | ACL 2026 | ACL 2026. Full title: *Flip-Flop Consistency: Unsupervised Training for Robustness to Prompt Perturbations in LLMs*. Hejabi, Rahmati, Salkhordeh Ziabari, Dehghani (USC) | [2026.acl-long.71](https://aclanthology.org/2026.acl-long.71.pdf) · arXiv 2510.14242 | **VERIFIED** |
| 12 | "Logical Consistency as a Bridge" | ACL 2026 | ACL 2026. Full title: *…via Label Constraint Modeling between Responses and Self-Judgments*. Mi, Sheng, Wang, Hu, Sun, Wang, Zeng, Li, Wang, Cao | [2026.acl-long.286](https://aclanthology.org/2026.acl-long.286/) · arXiv 2605.03971 | **VERIFIED** |

**Outcome: 12/12 resolved.** 7 verified as cited · 3 venue corrections · 1
downgraded to preprint status · 1 additional note (row 1 has a published
[erratum](https://aclanthology.org/2021.tacl-1.83/) that should be cited alongside the paper).

---

## Findings that affect the proposal's claims

### F1 — The D4 precedent claim holds, but the construction differs materially
**Affects §4.8.6. Verified directly from the paper's text, not from a summary.**

§4.8.6 states: *"Jensen–Shannon divergence over response distributions as a
consistency measure is established (Tsujimura et al., ACL 2026). The
contribution here is the application to meaning-preserving paraphrases over
knowledge-grounded constraints, not the measure."*

This is **correct**, and the precedent is real — the paper computes
`L_instance = 1 − JSD(p_prior ‖ p_posterior)`, citing Lin (1991). But what the
divergence is taken *between* is different in a way worth stating:

| | Tsujimura et al. (ACL 2026) | SemIntegrity D4 |
|---|---|---|
| Distributions compared | one **prior** vs one **posterior** scenario, after a logical-reasoning context is added | **K meaning-preserving paraphrases** of the same question |
| Distribution over | a 2-class normalised option tendency, built by **counting sampled selection frequencies** | teacher-forced **length-normalised log-probabilities over a closed candidate set** |
| Phenomenon measured | belief *update* under added context | phrasing-induced instability at fixed content |

The paper states explicitly that it measures tendencies *"rather than computing
log probabilities over a pre-defined answer set"* — which is precisely what D4
does. **This strengthens the differentiation and should be said plainly in
related work**, rather than leaving D4 looking like a re-run of the same measure.

### F2 — The scale claim is confirmed
§2.2 asserts the consistency/scale relationship "has already been studied".
Confirmed verbatim: *"belief consistency does not improve solely with model size
scaling, whereas continual pre-training on code and mathematics text improves
it."* §4.5's refusal to state a scaling-law hypothesis is well founded, and the
Qwen2.5 3B→7B→14B axis must stay descriptive.

### F3 — ChaosBench-Logic is a preprint, not a published benchmark
§A.3 says ChaosBench-Logic *"rules out any claim to be first on that axis"*.
It is real (v1 arXiv 2601.01982, v2 2605.24305, OpenReview 3buGJj1xxA) with
first-order-logic coverage and an explicit contradiction-rate metric, so it does
constrain the claim. But it has **no confirmed peer-reviewed venue**, and the
related-work text should describe it as a preprint rather than implying
otherwise.

### F4 — Flip-Flop Consistency is a mitigation method, not a measurement study
§2.2 describes it as studying "inconsistency across prompt perturbations". Its
actual contribution is **F²C, an unsupervised training method** (Consensus
Cross-Entropy + a representation alignment loss) that *improves* robustness —
reported as +11.62% observed agreement, +8.94% mean F₁. It is a **mitigation**
baseline, closer in kind to ConCoRD than to ParaRel. Describing it as a study of
inconsistency understates it and slightly misplaces it in the narrative.

### F5 — LogiConBench is the sharpest positioning challenge, and confirmed as such
Verified at ICLR 2026. It generates unlimited logical rule combinations with
precise labels and **controllable-depth graphs with explicit reasoning paths** —
exactly the "complexity axis in synthetic symbolic settings" §2.3 concedes
already exists. The distinguishing line in §2.3 (knowledge-grounded and
externally verifiable vs generated symbolic graphs) is the right one and
survives verification.

---

## What this does **not** establish

Verification confirms that these works exist, where they were published, and what
they claim. It does **not** constitute the systematic sweep §4.12 requires: no
search was run for *other* work that may already occupy SemIntegrity's
combination. The novelty statement therefore remains **unfinalised**, and
`novelty_risk.md` records the outstanding searches.

**No novelty or priority claim is made anywhere on the basis of this table.**
