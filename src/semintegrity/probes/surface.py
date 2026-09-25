"""Surface realisation of probes from factor cells (proposal §4.4.2).

:mod:`semintegrity.probes.factor_design` decides *which* factor cell each probe
slot occupies. This module turns a cell plus a constraint's surface slots into
the actual string the model sees.

How the four factors are realised
---------------------------------
**syntax** changes the frame:

===============  =====================================  ==============================
syntax           entity form                            boolean / date form
===============  =====================================  ==============================
declarative      ``The capital city of Australia is``    ``<claim> — YES or NO?``
interrogative    ``What is the capital city of ...?``    ``Is <claim>?``
cloze            ``The capital city of ... is ___.``      ``<claim>: ___``
===============  =====================================  ==============================

**directionality** decides which side of the relation is queried. §4.7 states
plainly that this factor "mixes 'Is A the X of B?' (yes/no) with 'What is the X
of B?' (an entity)", so a *reverse* probe of an entity constraint is a boolean
verification probe. Stage 0 reconciles the two answer spaces.

**polarity** negates the framing. A negated probe of a true proposition expects
the opposite surface answer, and that flip is recorded on the probe rather than
inferred later.

Q21 — UNRESOLVED, and visible here
----------------------------------
Whether an affirmative and a negated probe count as *the same* probe depends on
``EQUIVALENCE_KEY_FIELDS`` in :mod:`semintegrity.schemas.probe`, which currently
excludes ``polarity``. Under that setting the 8 probes of a constraint form one
paraphrase set and yield 28 comparable pairs. If the researcher decides polarity
belongs *inside* the key, each constraint instead yields two sets of 4 and only
12 pairs. **This module does not decide that**: it generates both polarities and
records the expected answer for each, so either reading works on the same data.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas.enums import AnswerType, Directionality, Polarity, Register, Syntax
from .factor_design import FactorCell


class SurfaceError(ValueError):
    """Raised when a constraint's surface slots cannot realise a factor cell."""


@dataclass(frozen=True, slots=True)
class Realisation:
    """One rendered probe."""

    text: str
    answer_type: AnswerType
    expected_answer: str
    form: str  # "entity" | "verify"


def _pick(slots: dict, base: str, register: Register) -> str:
    """Register-specific slot with a formal fallback."""
    if register is Register.COLLOQUIAL and f"{base}_colloquial" in slots:
        return str(slots[f"{base}_colloquial"])
    for key in (f"{base}_formal", base):
        if key in slots:
            return str(slots[key])
    raise SurfaceError(f"surface slots are missing {base!r} (have {sorted(slots)})")


def _flip(answer: str) -> str:
    return {"YES": "NO", "NO": "YES"}[answer]


def realise(
    cell: FactorCell,
    *,
    slots: dict,
    answer_type: AnswerType,
    gold_answer: str,
) -> Realisation:
    """Render one probe for one factor cell.

    ``form`` is "entity" only for a direct, affirmative probe of an entity- or
    date-typed constraint; every other cell is a boolean verification probe,
    which is what keeps a reverse or negated probe answerable at all.
    """
    direct = cell.directionality is Directionality.DIRECT
    affirmative = cell.polarity is Polarity.AFFIRMATIVE
    open_answer = answer_type in (AnswerType.ENTITY, AnswerType.DATE)

    if open_answer and direct and affirmative:
        return _realise_open(cell, slots, answer_type, gold_answer)
    return _realise_verify(cell, slots, gold_answer, answer_type)


def _realise_open(cell, slots, answer_type, gold_answer) -> Realisation:
    subject = _pick(slots, "subject", cell.register)
    relation = _pick(slots, "relation", cell.register)
    # "What is the first President of the United States?" is wrong for a person;
    # the author declares the interrogative pronoun rather than the generator
    # guessing at animacy.
    qword = str(slots.get("question_word", "What"))
    if cell.syntax is Syntax.INTERROGATIVE:
        text = f"{qword} is the {relation} of {subject}?"
    elif cell.syntax is Syntax.CLOZE:
        text = f"The {relation} of {subject} is ___."
    else:
        text = f"The {relation} of {subject} is"
    return Realisation(text, answer_type, gold_answer, "entity")


def _realise_verify(cell, slots, gold_answer, answer_type) -> Realisation:
    """A yes/no verification probe.

    Two paths, because only one of them can be built grammatically:

    * **assembled** — for entity/date constraints the subject, relation and
      object are known, so a natural question is composed from the parts
      ("Is Canberra the capital city of Australia?");
    * **author-supplied** — a conjunction or a universal cannot be reassembled
      from parts, so the author writes the claim and it is embedded in a frame
      that is grammatical for any sentence ("Is the following statement true:
      <claim>?"). Composing a question by lower-casing an arbitrary English
      sentence and prefixing "Is" produces "Is gold has more than one atomic
      number?", so that approach is not used.
    """
    author_claim = "claim_formal" in slots or "claim" in slots
    negated = cell.polarity is Polarity.NEGATED

    if author_claim:
        # Directionality must be REALISED, not merely recorded. For an
        # author-written claim the reverse phrasing cannot be derived, so the
        # author supplies `claim_reverse_*`. Without it the factor would be
        # logged while the probe text stayed identical, which would silently
        # turn a manipulated factor into a constant.
        base = "claim"
        if cell.directionality is Directionality.REVERSE and (
            "claim_reverse_formal" in slots or "claim_reverse" in slots
        ):
            base = "claim_reverse"
        claim = _pick(slots, base, cell.register)
        base_answer = gold_answer if answer_type is AnswerType.BOOLEAN else "YES"
        expected = _flip(base_answer) if negated else base_answer
        text = _frame_author_claim(cell.syntax, claim, negated)
    else:
        subject = _pick(slots, "subject", cell.register)
        relation = _pick(slots, "relation", cell.register)
        obj = str(slots["object"])
        expected = _flip("YES") if negated else "YES"
        text = _frame_assembled(cell, subject, relation, obj, negated)

    return Realisation(text, AnswerType.BOOLEAN, expected, "verify")


def _sentence(text: str) -> str:
    return f"{text[0].upper()}{text[1:]}" if text else text


def _frame_author_claim(syntax: Syntax, claim: str, negated: bool) -> str:
    """Embed an arbitrary author-written sentence in a grammatical frame."""
    truth = "false" if negated else "true"
    if syntax is Syntax.INTERROGATIVE:
        return f"Is the following statement {truth}? {_sentence(claim)}"
    if syntax is Syntax.CLOZE:
        prefix = "It is not the case that " if negated else ""
        return f"{_sentence(prefix + claim) if prefix else _sentence(claim)}: ___"
    prefix = "It is not the case that " if negated else ""
    return f"{_sentence(prefix + claim) if prefix else _sentence(claim)} — YES or NO?"


def _frame_assembled(cell, subject: str, relation: str, obj: str, negated: bool) -> str:
    """Compose a natural question from known relation parts."""
    reverse = cell.directionality is Directionality.REVERSE
    # Reverse asks from the object's side; direct asks about the relation value.
    if reverse:
        positive = f"{obj} is the {relation} of {subject}"
        question = f"Is {obj} the {relation} of {subject}?"
    else:
        positive = f"the {relation} of {subject} is {obj}"
        question = f"Is the {relation} of {subject} {obj}?"

    if cell.syntax is Syntax.INTERROGATIVE:
        return f"Is it false that {positive}?" if negated else question
    if cell.syntax is Syntax.CLOZE:
        stem = f"It is not the case that {positive}" if negated else _sentence(positive)
        return f"{stem}: ___"
    stem = f"It is not the case that {positive}" if negated else _sentence(positive)
    return f"{stem} — YES or NO?"


def describe_cell(cell: FactorCell) -> str:
    """Compact human-readable label, for the preview tables."""
    return (
        f"{cell.syntax.value[:4]}/{cell.polarity.value[:3]}/"
        f"{cell.register.value[:4]}/{cell.directionality.value[:3]}"
    )


def realised_factors(
    *, slots: dict, answer_type: AnswerType, gold_answer: str
) -> dict[str, bool]:
    """Which factors actually change the probe text for this constraint.

    A factor that is recorded but never alters the surface is a constant wearing
    a factor's name; any effect later attributed to it would be meaningless.

    This probes the *renderer* over the full 24-cell space rather than the 8
    cells a constraint uses, because within one constraint each
    (polarity, register, directionality) triple occurs exactly once, so no two
    of its cells differ in a single factor and a cell-set comparison could never
    detect variation even where it exists.
    """
    from itertools import product

    factors = (list(Syntax), list(Polarity), list(Register), list(Directionality))
    rendered: dict[tuple, str] = {}
    for syn, pol, reg, direction in product(*factors):
        cell = FactorCell(
            cell_index=0, syntax=syn, polarity=pol, register=reg, directionality=direction
        )
        rendered[(syn, pol, reg, direction)] = realise(
            cell, slots=slots, answer_type=answer_type, gold_answer=gold_answer
        ).text

    out: dict[str, bool] = {}
    for position, name in enumerate(("syntax", "polarity", "register", "directionality")):
        varies = any(
            rendered[a] != rendered[b]
            for a in rendered
            for b in rendered
            if a[position] != b[position]
            and all(a[i] == b[i] for i in range(4) if i != position)
        )
        out[name] = varies
    return out
