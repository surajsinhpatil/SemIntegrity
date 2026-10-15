"""Why did Stage 0 return INVALID? A syntactic decomposition (§7.6 failure analysis).

Mistral-7B-Instruct-v0.3 canonicalises at 63.02% against a FROZEN >=95% CANON
gate, while the other four models sit at 97.29-99.17%. "Mistral fails CANON" is
one number covering at least two different events, and the difference decides
whether the gate is measuring the model or the instrument:

* the model answered **outside the constraint's closed answer space** — a
  finding about the model (or the probe), and INVALID is the correct label; or
* the model answered a **polar** probe by naming an answer-space member instead
  of YES/NO — the Q31 entity/date fall-through, where a reader can often see a
  determinate answer that Stage 0's rule deliberately declines to infer.

THIS MODULE CLASSIFIES SURFACE FORM ONLY. IT DOES NOT ADJUDICATE.
----------------------------------------------------------------
Every category here is decided by **machine-checkable syntax**: is the probe
polar, does `parse_yes_no` find a leading yes/no token, does `_find_candidates`
locate an answer-space member, does a negation token co-occur. None of them is a
judgement about what the model meant, and
:data:`POLAR_NEGATED_SPACE_MEMBER_NO_YESNO` in particular is **not** a claim
that the reply was a determinate answer. It is the count of replies in which a
negation marker and an answer-space member co-occur without a leading yes/no —
the subset that a different, non-frozen rule *could* reach. Reporting it bounds
what the frozen first-token rule forgoes. It does not argue for changing it.

NOTHING HERE PROPOSES A CANONICALISER CHANGE
--------------------------------------------
Stage 0 and the >=95% threshold are FROZEN (2026-10-07). The first-token rule is
deliberate: `parse_yes_no` "returns None rather than True — inferring a polar
answer from a word buried [in the reply]" would reintroduce on negated probes
the exact artifact the Q21 polarity mapping removed. This module measures the
cost of that choice so the cost can be reported, which is the alternative to
changing a frozen instrument to accommodate one model of five.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..canonicalization.canonicaliser import (
    _find_candidates,
    classify,
    is_polar,
    normalise,
    parse_yes_no,
)
from ..schemas.enums import AnswerType, ResponseLabel

#: Reply is blank once normalised.
EMPTY = "EMPTY"
#: Non-polar probe, no answer-space member recognised. The model answered
#: something outside the closed space: INVALID is the CORRECT label, and this is
#: a finding about the model or the probe, not about Stage 0.
NON_POLAR_NO_SPACE_MEMBER = "NON_POLAR_NO_SPACE_MEMBER"
#: Polar probe on an **entity or date** constraint, no leading yes/no, but a
#: member of the closed answer space is present. **THIS, AND ONLY THIS, IS THE
#: Q31 ENTITY/DATE FALL-THROUGH** — the open question of whether a polar probe
#: answered by naming an answer-space member should be read as an answer.
POLAR_ENTITY_DATE_MEMBER = "POLAR_ENTITY_DATE_MEMBER"
#: Polar probe on a **boolean** constraint, whose answer space IS ``['YES','NO']``,
#: where a yes/no token appears but NOT in leading position.
#:
#: This is a DIFFERENT designed behaviour and must never be pooled with the
#: category above. The canonicaliser refuses answer-space matching here on
#: purpose: "'The answer is yes' would match YES literally and BYPASS the
#: polarity inversion, reintroducing on negated probes the exact artifact this
#: mapping removes." Counting these as Q31 cases would misread a deliberate
#: anti-bypass guard as an unresolved question.
POLAR_BOOLEAN_YESNO_BURIED = "POLAR_BOOLEAN_YESNO_BURIED"
#: Polar probe, neither a leading yes/no nor any answer-space member. The model
#: answered something else entirely.
POLAR_NO_YESNO_NO_SPACE_MEMBER = "POLAR_NO_YESNO_NO_SPACE_MEMBER"
#: INVALID for a reason none of the above describes. A non-empty count here
#: means this taxonomy is incomplete and must be extended, not ignored.
OTHER = "OTHER"

CATEGORIES: tuple[str, ...] = (
    EMPTY,
    NON_POLAR_NO_SPACE_MEMBER,
    POLAR_ENTITY_DATE_MEMBER,
    POLAR_BOOLEAN_YESNO_BURIED,
    POLAR_NO_YESNO_NO_SPACE_MEMBER,
    OTHER,
)

#: Explicit negation markers, matched on word boundaries over the NORMALISED
#: reply. Deliberately short and syntactic: "no" is excluded because a leading
#: "no" is already a yes/no token and a buried one is not evidence of anything.
_NEGATION = re.compile(r"\b(?:not|never|cannot)\b|n't")


@dataclass(frozen=True, slots=True)
class InvalidCase:
    """One INVALID response, with the surface facts behind its category."""

    probe_id: str
    constraint_id: str
    category: str
    polar: bool
    candidates: tuple[str, ...]
    has_negation: bool
    note: str


def categorise(raw: Any, constraint: Any, probe: Any) -> InvalidCase | None:
    """Classify one response, or ``None`` if Stage 0 did not call it INVALID.

    Stage 0 is **recomputed**, never read from a stored label, so this cannot
    drift from the canonicaliser it is describing.
    """
    result = classify(raw, constraint, probe)
    if result.label is not ResponseLabel.INVALID:
        return None

    text = normalise(raw.raw_text)
    polar = is_polar(probe)
    # `candidates_found` is empty on the polar-INVALID path, so candidates are
    # recomputed here with the canonicaliser's own matcher rather than a second
    # implementation that would drift from it.
    candidates = tuple(c for c, _ in _find_candidates(text, constraint))
    has_negation = bool(_NEGATION.search(text))

    if not text:
        category = EMPTY
    elif not polar:
        category = NON_POLAR_NO_SPACE_MEMBER if not candidates else OTHER
    elif parse_yes_no(text) is not None:
        category = OTHER  # a leading yes/no was found, so INVALID came elsewhere
    elif candidates:
        # The split that matters: a YES/NO candidate on a boolean constraint is
        # the deliberate anti-bypass guard, not the Q31 question.
        category = (
            POLAR_BOOLEAN_YESNO_BURIED
            if constraint.answer_type is AnswerType.BOOLEAN
            else POLAR_ENTITY_DATE_MEMBER
        )
    else:
        category = POLAR_NO_YESNO_NO_SPACE_MEMBER

    return InvalidCase(
        probe_id=probe.probe_id, constraint_id=constraint.constraint_id,
        category=category, polar=polar, candidates=candidates,
        has_negation=has_negation, note=result.note,
    )


def decompose(
    raws: Sequence[Any],
    constraints: Mapping[str, Any],
    probes: Mapping[str, Any],
) -> tuple[list[InvalidCase], dict[str, Any]]:
    """Every INVALID response in a run, categorised, plus a summary.

    The summary reports the **recoverable fraction** of INVALIDs separately from
    the total, where "recoverable" means only "a rule other than the frozen
    first-token rule could in principle reach a verdict here". It is an upper
    bound on what the frozen choice costs, not a correction to apply.
    """
    cases = [
        case
        for r in raws
        if (case := categorise(r, constraints[r.constraint_id], probes[r.probe_id]))
    ]
    counts = Counter(c.category for c in cases)
    n_invalid = len(cases)
    #: Q31 is ONLY the entity/date category. The boolean-buried count is
    #: reported alongside it, never added to it.
    fallthrough = counts[POLAR_ENTITY_DATE_MEMBER]
    summary = {
        "n_responses": len(raws),
        "n_invalid": n_invalid,
        "invalid_rate": (n_invalid / len(raws)) if raws else None,
        "counts": {k: counts[k] for k in CATEGORIES},
        "n_q31_entity_date_fallthrough": fallthrough,
        "q31_share_of_invalid": (fallthrough / n_invalid if n_invalid else None),
        "n_boolean_yesno_buried": counts[POLAR_BOOLEAN_YESNO_BURIED],
        "n_correctly_invalid_model_error": counts[NON_POLAR_NO_SPACE_MEMBER],
        "n_negation_marker_present": sum(1 for c in cases if c.has_negation),
        "n_unclassified": counts[OTHER],
        # The arithmetic that decides whether any rule change could rescue this
        # run: recovering EVERY Q31 case and still failing the gate settles the
        # question without touching the canonicaliser.
        "canonicalisation_rate": (
            1 - n_invalid / len(raws) if raws else None
        ),
        "ceiling_if_every_q31_case_were_recovered": (
            (len(raws) - n_invalid + fallthrough) / len(raws) if raws else None
        ),
        "interpretation": (
            "NON_POLAR_NO_SPACE_MEMBER is a finding about the model: it answered "
            "outside the closed space and INVALID is correct. "
            "POLAR_ENTITY_DATE_MEMBER is the Q31 question and nothing else is. "
            "POLAR_BOOLEAN_YESNO_BURIED is a DIFFERENT, deliberate anti-bypass "
            "guard and must not be pooled with it. "
            "POLAR_NO_YESNO_NO_SPACE_MEMBER is a reply that answered neither way. "
            "`ceiling_if_every_q31_case_were_recovered` is an UPPER BOUND, not a "
            "correction: Stage 0 and the >=95% threshold remain FROZEN."
        ),
    }
    return cases, summary
