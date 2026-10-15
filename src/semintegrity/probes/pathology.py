"""Machine-detectable probe pathologies (PROBE-C, ADR-0023 D2).

The preregistered `PROBE` criterion required ">= 90% of candidate probes survive
**human** semantic-equivalence validation". No human judged any probe — all
1,056 carry `validation_status: draft` — and under the redesign none will.
`PROBE-C` replaces it with checks a machine can make.

WHAT THIS IS AND IS NOT
-----------------------
It audits the **generator**, not the generated meaning. A systematically
mis-specified `logical_form` passes every check here. "Validated" is not
available as a word for the result; "constructed and machine-audited" is.

PROBE-C ADDS EXACTLY ONE CHECK. THE OTHER THREE ALREADY EXIST.
--------------------------------------------------------------
An earlier draft of this module implemented four pathologies. Three were
**already enforced upstream as HARD failures**, so reimplementing them would
have created two definitions of one rule — the thing this codebase repeatedly
warns against — and would have made PROBE-C appear to contribute four checks
when it contributes one:

* a cloze with no blank — `schemas.probe.Probe`'s own validator
  ("cloze probes must contain a '___' blank"). Refused at **construction**,
  which is stronger than refusing at audit;
* two probes of one constraint sharing a surface —
  `schemas.probe.assert_distinct_surfaces`, called by `benchmark.loader`;
* an `expected_answer` outside the answer space on a non-boolean probe —
  `benchmark.loader`, a hard load failure.

Those are reported by :func:`audit` as ``upstream_guarantees``: named,
attributed, and **not** re-derived here. The one genuinely new check is
:data:`STEM_EMBEDS_GOLD_ANSWER`.

THE ONE PATHOLOGY THIS WAS BUILT FOR, AND ITS EVIDENTIAL STATUS
---------------------------------------------------------------
:data:`STEM_EMBEDS_GOLD_ANSWER` detects a polar **CLOZE** probe whose own text
contains the gold answer — a blank to be completed with TRUE/FALSE placed after
a statement that already names the answer, as in
``The statement "1972 is the year it ended" is ___.`` The blank invites
completion from the nearest salient token, which is the embedded answer, and
Stage 0 then records INVALID.

**An alternative predicate was tested and found equivalent.** The echo risk
arguably applies to any embedded answer-space member, not only the gold one: a
cloze asserting a distractor could be echoed just as easily. Measured on the
frozen split, "contains the gold answer" and "contains ANY answer-space member"
flag **exactly the same 43 probes** — this benchmark has no distractor-embedding
polar cloze, and the other 17 entity/date polar clozes contain no answer-space
member at all. The narrower predicate is therefore not a restriction here, and
the question is closed by measurement rather than left as an assumption.

**`cloze` is load-bearing, and an earlier version of this check omitted it and
was useless.** "Contains the gold answer" alone flagged **362 of 960 probes
(37.7%) spread evenly across all eight factor cells** — because a polar question
*must* state the proposition it asks about. ``Is 1972 the year it ended?``
necessarily contains "1972". That version was detecting the normal structure of
polar probes, not a defect. An interrogative cues a yes/no answer by its form; a
cloze blank does not, and that difference is the whole pathology.

**It is a HYPOTHESIS about a probe-design weakness, not an explanation of any
model's behaviour.** The evidence: all 3 Qwen2.5-14B and all 4 OLMo-2-7B
`POLAR_ENTITY_DATE_MEMBER` cases are P04 probes, and `K-C1-HIS-16-P04` fails
identically in two different model families — which is a probe property, not a
model property. **But Mistral-7B's 71 cases span P02-P08**, so this pathology
does **not** explain Mistral's CANON failure. Nothing in this module may be
cited as doing so.

A flagged probe is **reported, never rewritten or discarded**. The benchmark is
frozen; changing probes to improve a result is exactly what ADR-0023 forbids.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

#: A polar **CLOZE** probe whose own text contains the gold answer: a blank to
#: be completed with TRUE/FALSE, placed after a statement that already names the
#: answer. See the module docstring for why `cloze` is load-bearing here and for
#: why this is a hypothesis rather than a conclusion.
STEM_EMBEDS_GOLD_ANSWER = "POLAR_CLOZE_STEM_EMBEDS_GOLD_ANSWER"
#: The only pathology this module implements. The three listed in the module
#: docstring are enforced upstream and are NOT re-derived here.
PATHOLOGIES: tuple[str, ...] = (STEM_EMBEDS_GOLD_ANSWER,)

#: Guarantees PROBE-C relies on but does not implement, each a HARD failure at
#: construction or load time. Reported so PROBE-C's total coverage is legible
#: without this module claiming credit for it.
UPSTREAM_GUARANTEES: tuple[dict[str, str], ...] = (
    {
        "guarantee": "a cloze probe contains a '___' blank",
        "enforced_by": "semintegrity.schemas.probe.Probe (model_validator)",
        "when": "construction",
        "severity": "hard failure — such a Probe cannot be instantiated",
    },
    {
        "guarantee": "no two probes of one constraint share a surface",
        "enforced_by": "semintegrity.schemas.probe.assert_distinct_surfaces",
        "when": "load (benchmark.loader)",
        "severity": "hard failure — identical surfaces inflate apparent agreement",
    },
    {
        "guarantee": "a non-boolean probe's expected_answer is in the answer space",
        "enforced_by": "semintegrity.benchmark.loader",
        "when": "load",
        "severity": "hard failure",
    },
)

_POLAR_EXPECTED = frozenset({"YES", "NO", "TRUE", "FALSE"})


@dataclass(frozen=True, slots=True)
class ProbeFinding:
    """One flagged probe. Reported; never a licence to rewrite it."""

    probe_id: str
    constraint_id: str
    pathology: str
    detail: str
    factor_cell: str


def _cell(probe_id: str) -> str:
    """The probe's factor-cell suffix, e.g. ``04`` from ``...-P04``."""
    return probe_id.rsplit("-P", 1)[-1] if "-P" in probe_id else "??"


def _contains_answer(text: str, answer: str) -> bool:
    """Whole-token containment, case-insensitive.

    Substring matching would fire on "1972" inside "11972" and on "Mir" inside
    "Mirror", so the comparison is anchored on non-word boundaries.
    """
    if not answer:
        return False
    return re.search(rf"(?<!\w){re.escape(answer.lower())}(?!\w)", text.lower()) is not None


def check_constraint_probes(
    constraint: Any, probes: Sequence[Any]
) -> list[ProbeFinding]:
    """Every pathology for one constraint's probe set."""
    findings: list[ProbeFinding] = []
    for p in probes:
        expected = str(p.expected_answer or "").strip()
        if expected.upper() not in _POLAR_EXPECTED:
            continue   # a non-polar probe is SUPPOSED to elicit the answer
        if str(p.syntax).split(".")[-1].lower() != "cloze":
            continue   # an interrogative cues yes/no by its form; a blank does not
        if _contains_answer(p.probe_text, constraint.gold_answer):
            findings.append(ProbeFinding(
                probe_id=p.probe_id, constraint_id=constraint.constraint_id,
                pathology=STEM_EMBEDS_GOLD_ANSWER,
                detail=(
                    f"polar CLOZE probe (expects {expected!r}) whose text "
                    f"contains the gold answer {constraint.gold_answer!r}: the "
                    "blank invites completion from the embedded answer rather "
                    "than a yes/no"
                ),
                factor_cell=_cell(p.probe_id),
            ))
    return findings


def audit(
    constraints: Sequence[Any], probes_by_constraint: dict[str, Sequence[Any]]
) -> tuple[list[ProbeFinding], dict[str, Any]]:
    """PROBE-C's pathology pass over a whole split.

    The summary cross-tabulates by factor cell, which is what makes a
    *structural* probe weakness distinguishable from scattered noise: a
    pathology concentrated in one cell is a template problem, one spread evenly
    is not.
    """
    findings: list[ProbeFinding] = []
    for c in constraints:
        findings.extend(
            check_constraint_probes(c, probes_by_constraint.get(c.constraint_id, []))
        )
    counts = Counter(f.pathology for f in findings)
    by_cell: dict[str, dict[str, int]] = {}
    for f in findings:
        by_cell.setdefault(f.pathology, {})
        by_cell[f.pathology][f.factor_cell] = (
            by_cell[f.pathology].get(f.factor_cell, 0) + 1
        )
    n_probes = sum(len(v) for v in probes_by_constraint.values())
    summary = {
        "n_constraints": len(constraints),
        "n_probes": n_probes,
        "n_flagged": len(findings),
        "flagged_rate": (len(findings) / n_probes) if n_probes else None,
        "counts": {k: counts[k] for k in PATHOLOGIES},
        "by_factor_cell": {k: dict(sorted(v.items())) for k, v in sorted(by_cell.items())},
        "passes_probe_c": not findings,
        "upstream_guarantees": [dict(g) for g in UPSTREAM_GUARANTEES],
        "checks_implemented_here": list(PATHOLOGIES),
        "scope": (
            "Audits the GENERATOR, not the generated meaning. A systematically "
            "mis-specified logical_form passes every check here. This is not "
            "semantic-equivalence validation and must not be called validated."
        ),
        "stem_embeds_gold_answer_status": (
            "HYPOTHESIS about probe design, NOT an explanation of any model's "
            "behaviour. Mistral-7B's 71 POLAR_ENTITY_DATE_MEMBER cases span "
            "P02-P08, so this pathology does not account for its CANON failure."
        ),
        "remedy": (
            "Findings are REPORTED. The benchmark is frozen and no probe is "
            "rewritten or discarded on the strength of a result (ADR-0023)."
        ),
    }
    return findings, summary
