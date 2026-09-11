"""The probe record (proposal §4.4.1 formal representation + §4.4.2 factors).

§4.4.1 lists ten fields and defines equivalence as identity of the
representation. §4.4.2 adds the surface transformation factors, which are
recorded on every probe so that a class effect cannot be an artefact of unequal
phrasing.

**Open methodological question (Q21).** §4.4.1 puts ``polarity`` *inside* the
formal representation while also making it a meaning-preserving transformation
factor in §4.4.2. Read literally, an affirmative and a negated probe would have
different representations and therefore not be equivalent — which would empty
the polarity factor of its purpose. The equivalence key below is therefore
*configurable* and defaults to excluding polarity, exactly as §4.7 already
handles directionality (a yes/no probe and an entity probe reach a common
canonical space through Stage 0). **This default is not a decision;
``EQUIVALENCE_KEY_FIELDS`` is the single place it lives and it awaits researcher
approval.**
"""

from __future__ import annotations

import datetime as dt
import warnings
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..utils.ids import CONSTRAINT_RE, PROBE_RE
from .enums import (
    AnswerType,
    Directionality,
    Polarity,
    Quantifier,
    Register,
    Syntax,
    Tier,
    Track,
    ValidationStatus,
)

# `register` is the proposal's own term for the formal/colloquial probe factor
# (§4.4.2), so the field keeps that name. It shadows `ABCMeta.register`, which is
# a *metaclass* method this project never calls — instances are unaffected.
# The warning is silenced precisely rather than renaming a spec field.
warnings.filterwarnings(
    "ignore",
    message=r'Field name "register" in "Probe" shadows an attribute in parent "BaseModel"',
    category=UserWarning,
)

NonEmptyStr = Annotated[str, Field(min_length=1)]

#: Fields whose identity defines semantic equivalence (§4.4.1).
#: Q21 — AWAITING RESEARCHER APPROVAL. Changing this tuple changes what the
#: study treats as "the same question asked differently".
EQUIVALENCE_KEY_FIELDS: tuple[str, ...] = (
    "logical_form",
    "subject",
    "predicate",
    "object",
    "time_scope",
    "quantifier",
)

#: Surface factors — deliberately NOT part of the equivalence key.
SURFACE_FACTOR_FIELDS: tuple[str, ...] = ("syntax", "polarity", "register", "directionality")


class Probe(BaseModel):
    """One meaning-preserving probe of one constraint."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # --- §4.4.1 formal representation (10 fields) --------------------------
    constraint_id: str = Field(pattern=CONSTRAINT_RE.pattern)
    probe_id: str = Field(pattern=PROBE_RE.pattern)
    logical_form: NonEmptyStr = Field(
        description=(
            "Polarity-normalised logical form. Two probes asking the same thing "
            "affirmatively and negatively share ONE logical_form."
        )
    )
    subject: NonEmptyStr
    predicate: NonEmptyStr
    object: str = Field(description="may be empty for open-ended probes")
    time_scope: str = Field(
        default="", description="temporal anchor, e.g. '1901-01-01' or 'at any time'; empty if atemporal"
    )
    quantifier: Quantifier = Quantifier.NONE
    polarity: Polarity
    answer_type: AnswerType = Field(
        description=(
            "This probe's answer type, which MAY differ from the constraint's "
            "(a reverse probe can be boolean where the constraint is entity). "
            "Stage 0 reconciles them (§4.7)."
        )
    )

    # --- §4.4.2 surface factors -------------------------------------------
    syntax: Syntax
    register: Register
    directionality: Directionality
    factor_cell_index: int = Field(
        ge=0, le=7, description="index into the 2x2x2 (polarity, register, direction) lattice (ADR-0003)"
    )

    # --- realisation and lifecycle ----------------------------------------
    probe_text: NonEmptyStr = Field(description="the surface string shown to the model")
    tier: Tier = Tier.PRIMARY
    track: Track = Track.A
    expected_answer: NonEmptyStr = Field(
        description=(
            "The canonical answer a correct, consistent model should give TO THIS "
            "PROBE, already accounting for polarity and directionality. Stage 0 "
            "maps a raw response onto the constraint's answer space using it."
        )
    )
    validation_status: ValidationStatus = ValidationStatus.DRAFT
    rewritten_from: str | None = Field(
        default=None, description="probe_id of the discarded probe this one replaces"
    )
    generated_at: dt.datetime | None = None
    notes: str = ""

    # ----------------------------------------------------------------------
    @model_validator(mode="after")
    def _consistent(self) -> Probe:
        if not self.probe_id.startswith(self.constraint_id + "-P"):
            raise ValueError(
                f"probe_id {self.probe_id} does not belong to constraint {self.constraint_id}"
            )
        if self.answer_type is AnswerType.BOOLEAN and self.expected_answer not in {"YES", "NO"}:
            raise ValueError(
                f"boolean probe expects YES or NO, got {self.expected_answer!r}"
            )
        if self.syntax is Syntax.CLOZE and "___" not in self.probe_text:
            raise ValueError("cloze probes must contain a '___' blank")
        if self.rewritten_from and self.validation_status is ValidationStatus.DRAFT:
            raise ValueError("a rewritten probe cannot still be DRAFT")
        return self

    # --- equivalence -------------------------------------------------------
    def equivalence_key(self) -> tuple[Any, ...]:
        """The operational definition of semantic equivalence (§4.4.1).

        Two probes of the same constraint are equivalent iff this key matches.
        """
        return (self.constraint_id, *(getattr(self, f) for f in EQUIVALENCE_KEY_FIELDS))

    def surface_key(self) -> tuple[Any, ...]:
        """The factor cell this probe occupies (§4.4.2)."""
        return tuple(getattr(self, f) for f in SURFACE_FACTOR_FIELDS)

    def is_equivalent_to(self, other: Probe) -> bool:
        return self.equivalence_key() == other.equivalence_key()

    @property
    def index(self) -> int:
        """1-based position within the constraint."""
        return int(self.probe_id.rsplit("-P", 1)[1])


def assert_mutually_equivalent(probes: list[Probe]) -> None:
    """Raise unless every probe shares one equivalence key.

    Run at freeze time: a probe set that fails this is not a paraphrase set, and
    every contradiction measured over it would be an artefact.
    """
    if not probes:
        raise ValueError("no probes given")
    keys = {p.equivalence_key() for p in probes}
    if len(keys) != 1:
        offenders = {p.probe_id: p.equivalence_key() for p in probes}
        raise ValueError(
            f"probes are not mutually equivalent — {len(keys)} distinct formal "
            f"representations: {offenders}"
        )


def assert_distinct_surfaces(probes: list[Probe]) -> None:
    """Raise if two probes occupy the same factor cell.

    Duplicate surface realisations would break the exact class-level balance the
    design depends on (ADR-0003).
    """
    seen: dict[tuple, str] = {}
    for p in probes:
        key = p.surface_key()
        if key in seen:
            raise ValueError(
                f"probes {seen[key]} and {p.probe_id} occupy the same factor cell {key}"
            )
        seen[key] = p.probe_id
