"""Controlled vocabularies.

Every categorical value in the benchmark is an enum, so a typo is a load-time
error rather than a silently-dropped stratum in the analysis.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """Serialises as its value; compares equal to the plain string."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class ConstraintClass(StrEnum):
    """The four structural conditions (proposal §4.2).

    **CATEGORICAL, NOT ORDERED.** §4.2 is explicit: "temporal reasoning is not
    provably 'more complex' than universal quantification; it is a different
    structural requirement", and H1 is deliberately stated as a *difference*
    rather than a monotonic increase.

    Because this enum inherits from ``str``, Python would otherwise give it a
    free lexicographic ordering, and ``C1 < C4`` would quietly succeed — which
    is exactly how a categorical factor ends up modelled as an ordinal one. The
    comparison operators are therefore disabled.

    Ordering for *display* is still easy: sort on ``.value``, which is a plain
    string (``sorted(c.value for c in classes)``).
    """

    C1 = "C1"  # Atomic
    C2 = "C2"  # Conjunctive / relational
    C3 = "C3"  # Quantified / rule-based
    C4 = "C4"  # Temporal

    def _no_order(self, other: object) -> bool:
        raise TypeError(
            "ConstraintClass is a categorical experimental condition, not an "
            "ordered scale (proposal §4.2), so comparison is disabled. "
            "Sort or compare on `.value` if you need a display order, and never "
            "enter class as an ordinal or continuous model term."
        )

    __lt__ = _no_order
    __le__ = _no_order
    __gt__ = _no_order
    __ge__ = _no_order


class Domain(StrEnum):
    """Balancing/control variable (§4.3). Supports no inferential claim."""

    GEOGRAPHY = "geography"
    HISTORY = "history"
    BIOLOGY = "biology"
    PUBLIC_OFFICE = "public_office"
    SCIENCE_TECHNOLOGY = "science_technology"


class Split(StrEnum):
    """Frozen development/test split (ADR-0007)."""

    DEV = "dev"
    TEST = "test"
    PILOT = "pilot"  # Phase 3 pilot constraints; absorbed into DEV afterwards


class Tier(StrEnum):
    PRIMARY = "primary"
    SATURATION = "saturation"
    STOCHASTIC = "stochastic"
    TRACK_B = "track_b"
    KNOWLEDGE_SCREEN = "knowledge_screen"
    DETERMINISM = "determinism"
    PILOT = "pilot"


class Track(StrEnum):
    A = "A"  # constrained output
    B = "B"  # free-form


class AnswerType(StrEnum):
    """What Track A asks the model to return (§4.4.3)."""

    ENTITY = "entity"
    BOOLEAN = "boolean"
    DATE = "date"


# --- Probe surface factors (§4.4.2) ---------------------------------------
class Syntax(StrEnum):
    DECLARATIVE = "declarative"
    INTERROGATIVE = "interrogative"
    CLOZE = "cloze"


class Polarity(StrEnum):
    AFFIRMATIVE = "affirmative"
    NEGATED = "negated"


class Register(StrEnum):
    FORMAL = "formal"
    COLLOQUIAL = "colloquial"


class Directionality(StrEnum):
    DIRECT = "direct"
    REVERSE = "reverse"


class Quantifier(StrEnum):
    """Quantifier scope in the formal probe representation (§4.4.1)."""

    NONE = "none"
    UNIVERSAL = "universal"
    EXISTENTIAL = "existential"


# --- Stage 0 canonicalisation (§4.7) --------------------------------------
class ResponseLabel(StrEnum):
    ANSWER = "ANSWER"
    #: A polar probe whose answer asserts the COMPLEMENT of the named candidate:
    #: "Is Canberra the capital?" -> "no". The response is meaningful and
    #: evaluable, but it fixes only what the answer is NOT. Added 2026-09-25 as
    #: part of the Q21 polarity mapping.
    NEGATED = "NEGATED"
    ABSTAIN = "ABSTAIN"
    INVALID = "INVALID"
    AMBIGUOUS = "AMBIGUOUS"
    FAILED = "FAILED"


#: Labels that make a response unusable for pairwise contradiction detection.
#: A pair is evaluable iff BOTH responses carry a resolved answer, i.e. ANSWER
#: or NEGATED (Q6, pending confirmation at Phase 4 preregistration).
NON_EVALUABLE_LABELS = frozenset(
    {ResponseLabel.ABSTAIN, ResponseLabel.INVALID, ResponseLabel.AMBIGUOUS, ResponseLabel.FAILED}
)


# --- D0 (§4.8.2) -----------------------------------------------------------
class Verdict(StrEnum):
    VIOLATION = "VIOLATION"
    SATISFIED = "SATISFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DetectorId(StrEnum):
    D0 = "D0"
    D1 = "D1"
    D2 = "D2"
    D3 = "D3"
    D4 = "D4"
    HUMAN = "H"


# --- Human annotation (§4.9) ----------------------------------------------
class Relation(StrEnum):
    COMPATIBLE = "compatible"
    CONTRADICTORY = "contradictory"
    UNCLEAR = "unclear"


class Correctness(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNCLEAR = "unclear"


class ResponseStatus(StrEnum):
    ANSWER = "answer"
    ABSTAIN = "abstain"


class ValidationStatus(StrEnum):
    """Probe lifecycle through §4.4.5 validation."""

    DRAFT = "draft"
    AUTO_FILTERED = "auto_filtered"
    PENDING_HUMAN = "pending_human"
    VALIDATED = "validated"
    REWRITTEN = "rewritten"
    DISCARDED = "discarded"

class VerificationStatus(StrEnum):
    """Where a constraint sits on the evidence ladder.

    A strict, monotone ladder. Nothing may claim a rung it has not reached, and
    the :class:`~semintegrity.schemas.constraint.Constraint` validators refuse
    records that do:

    ``DRAFT``
        Authored by a human. The claim may be right, but nothing has checked it.
        **This is the only status a newly authored constraint may hold.**
    ``EVIDENCE_VERIFIED``
        At least one machine-checked piece of evidence from the knowledge base
        agrees with ``gold_answer``. Requires an :class:`Evidence` record with
        ``supports_gold=True``. Says nothing about whether the constraint is
        well-posed, unambiguous or correctly classified.
    ``HUMAN_VALIDATED``
        A **named** human confirmed the claim, its wording and its class
        assignment. Requires ``human_validated_by`` and ``human_validated_at``.
        This status is never set by any automated process.
    ``FROZEN``
        Human-validated and included in a frozen split (§4.1). No changes after.
    """

    DRAFT = "DRAFT"
    EVIDENCE_VERIFIED = "EVIDENCE_VERIFIED"
    HUMAN_VALIDATED = "HUMAN_VALIDATED"
    FROZEN = "FROZEN"


#: Ladder order. Used to test "has at least reached" without implying that these
#: are interchangeable with a numeric scale.
VERIFICATION_RANK: dict[str, int] = {
    VerificationStatus.DRAFT.value: 0,
    VerificationStatus.EVIDENCE_VERIFIED.value: 1,
    VerificationStatus.HUMAN_VALIDATED.value: 2,
    VerificationStatus.FROZEN.value: 3,
}


def at_least(status: VerificationStatus, floor: VerificationStatus) -> bool:
    """Whether ``status`` has reached ``floor`` on the ladder."""
    return VERIFICATION_RANK[status.value] >= VERIFICATION_RANK[floor.value]

