"""D2 rendering: a canonicalised response as a declarative claim (§4.8.4).

`configs/detectors/d2_nli.yaml` requires that D2 operate on *declarative
propositions only* -- "question and cloze forms are converted to statements by
Stage 0 before classification" -- at claim level. An NLI model fed a bare
`"Canberra"` against `"Sydney"` has no proposition to contradict; fed
`"The capital city of Australia is Canberra."` against
`"The capital city of Australia is Sydney."` it has exactly one.

The template is not invented here. Every constraint already carries
`gold_proposition`, the declarative form of the constraint, and the claim a
response makes is that proposition with the response's own answer in it:

    gold_proposition : "The capital city of Australia is Canberra."
    response         : Sydney
    claim            : "The capital city of Australia is Sydney."

Three cases, keyed on the constraint's `answer_type` and the Stage 0 label:

* **entity / date, ANSWER** -- substitute the canonical answer for the gold
  answer inside `gold_proposition`.
* **entity / date, NEGATED** -- the response denied the asserted candidate, so
  the claim is the negation of the gold proposition.
* **boolean** -- `gold_proposition` already states the proposition; canonical
  `YES` asserts it and `NO` negates it. Boolean is branched on `answer_type`,
  NEVER on whether "NO" appears in the text: `K-C3-GEO-01` reads "...and of no
  other sovereign state", which a substring test would mangle.

Substitution fails LOUDLY. A claim silently rendered with the wrong answer in it
would feed the NLI model a proposition the model never made, which is worse than
no D2 verdict at all.
"""

from __future__ import annotations

import re

from ...schemas.constraint import Constraint
from ...schemas.enums import AnswerType, ResponseLabel
from ...schemas.response import CanonicalResponse

#: Prefix used to negate a proposition. Kept as a single constant because the
#: NLI model's behaviour depends on it, so it is part of the frozen detector
#: configuration rather than an incidental string.
NEGATION_PREFIX = "It is not the case that "


class ClaimRenderingError(RuntimeError):
    """The response could not be turned into a declarative claim."""


def negate(proposition: str) -> str:
    """Negate a declarative proposition, preserving sentence case."""
    body = proposition.rstrip()
    trailing = "." if body.endswith(".") else ""
    body = body[:-1] if trailing else body
    if body:
        body = body[0].lower() + body[1:]
    return f"{NEGATION_PREFIX}{body}{trailing}"


def _substitute(proposition: str, gold: str, replacement: str) -> str:
    """Replace the gold answer inside the proposition, case-insensitively."""
    pattern = re.compile(re.escape(gold), re.IGNORECASE)
    if not pattern.search(proposition):
        raise ClaimRenderingError(
            f"gold answer {gold!r} does not occur in gold_proposition "
            f"{proposition!r}; cannot render a claim without inventing one"
        )
    return pattern.sub(replacement, proposition, count=1)


def render_claim(constraint: Constraint, response: CanonicalResponse) -> str | None:
    """The declarative claim this response makes, or None if it makes none.

    Returns None for ABSTAIN/INVALID/AMBIGUOUS/FAILED: those responses assert
    nothing, and manufacturing a proposition for them would put words in the
    model's mouth. D2 skips them, which shows up as reduced coverage.
    """
    if response.label not in (ResponseLabel.ANSWER, ResponseLabel.NEGATED):
        return None

    proposition = constraint.gold_proposition
    answer = response.canonical_answer
    if not answer:  # pragma: no cover - schema forbids it
        raise ClaimRenderingError(f"{response.probe_id}: {response.label.value} without an answer")

    if constraint.answer_type is AnswerType.BOOLEAN:
        # The proposition itself is the claim; YES asserts it, NO denies it.
        if response.label is ResponseLabel.NEGATED:  # pragma: no cover - not produced for boolean
            raise ClaimRenderingError(
                f"{response.probe_id}: NEGATED is not produced for boolean constraints"
            )
        if answer.upper() == "YES":
            return proposition
        if answer.upper() == "NO":
            return negate(proposition)
        raise ClaimRenderingError(
            f"{response.probe_id}: boolean answer {answer!r} is neither YES nor NO"
        )

    claim = _substitute(proposition, constraint.gold_answer, answer)
    return negate(claim) if response.label is ResponseLabel.NEGATED else claim
