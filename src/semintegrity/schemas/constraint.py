"""The constraint record (proposal §4.3).

The proposal specifies 17 fields. Those are reproduced verbatim and are all
required. A small number of *derived* fields are added because §4.7 depends on
them ("the answer space for each constraint is closed and known in advance") —
each is marked DERIVED and none changes what the study measures.

Validation is strict: unknown fields are rejected, so a typo in an authored
record fails at load time rather than becoming a silently-missing stratum.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..utils.ids import CONSTRAINT_RE, DOMAIN_CODES, FAMILY_RE, SCHEMA_RE
from .enums import AnswerType, ConstraintClass, Domain, Split

NonEmptyStr = Annotated[str, Field(min_length=1)]


class GoldSource(BaseModel):
    """One authoritative source for a constraint's ground truth (§4.3).

    Wikidata is primary but is explicitly *not* treated as absolute truth, so
    historical and temporal facts carry a second source.
    """

    model_config = ConfigDict(extra="forbid")

    name: NonEmptyStr = Field(description="e.g. 'Wikidata' or 'Encyclopaedia Britannica'")
    url: NonEmptyStr
    retrieved: dt.date = Field(description="retrieval date — provenance, not publication date")
    is_primary: bool = False
    note: str | None = None


class TemporalValidity(BaseModel):
    """Validity interval for the gold proposition (§4.3, §4.2 C4).

    ``start``/``end`` mirror Wikidata P580/P582. ``None`` for ``end`` means
    'still valid at retrieval time', which is distinct from 'unknown' —
    ``end_unknown`` records the difference rather than conflating them.
    """

    model_config = ConfigDict(extra="forbid")

    start: dt.date | None = None
    end: dt.date | None = None
    end_unknown: bool = False
    precision: str = Field(default="day", pattern="^(day|month|year|decade|century)$")

    @model_validator(mode="after")
    def _ordered(self) -> TemporalValidity:
        if self.start and self.end and self.end < self.start:
            raise ValueError(f"temporal_validity end {self.end} precedes start {self.start}")
        if self.end and self.end_unknown:
            raise ValueError("end_unknown cannot be true when an end date is given")
        return self


class PrerequisiteFact(BaseModel):
    """An atomic fact the model must know for the constraint to be meaningful.

    Asked directly of each model in the knowledge screen (§4.11). Conditioning on
    these is a *reporting view*, never an inclusion criterion.
    """

    model_config = ConfigDict(extra="forbid")

    fact_id: NonEmptyStr
    question: NonEmptyStr = Field(description="asked verbatim in the knowledge screen")
    answer_type: AnswerType
    gold_answer: NonEmptyStr
    gold_aliases: list[str] = Field(default_factory=list)


class Entity(BaseModel):
    """A named entity with its Wikidata grounding and familiarity metric."""

    model_config = ConfigDict(extra="forbid")

    label: NonEmptyStr
    qid: str = Field(pattern=r"^Q\d+$", description="Wikidata item id")
    sitelinks: int = Field(ge=0, description="deterministic familiarity proxy (§4.3)")
    aliases: list[str] = Field(default_factory=list)
    sitelinks_retrieved: dt.date | None = None


class Constraint(BaseModel):
    """One integrity constraint.

    Fields 1–17 are the proposal's per-constraint record, in its order.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=False, validate_assignment=True)

    # --- the proposal's 17 fields (§4.3) -----------------------------------
    constraint_id: str = Field(pattern=CONSTRAINT_RE.pattern)
    family_id: str = Field(pattern=FAMILY_RE.pattern)
    schema_id: str = Field(pattern=SCHEMA_RE.pattern)
    domain: Domain
    constraint_class: ConstraintClass = Field(alias="class")
    formal_predicate: NonEmptyStr = Field(
        description="the D0 predicate key; resolves via the predicate registry"
    )
    constraint_text: NonEmptyStr = Field(description="the constraint in natural language")
    entities: list[NonEmptyStr] = Field(min_length=1)
    entity_qids: list[str] = Field(min_length=1)
    entity_sitelinks: list[int] = Field(min_length=1)
    gold_proposition: NonEmptyStr
    gold_source: NonEmptyStr
    gold_source_url: NonEmptyStr
    gold_source_date: dt.date
    temporal_validity: TemporalValidity | None = None
    ambiguity_notes: str = ""
    prerequisite_atomic_facts: list[PrerequisiteFact] = Field(default_factory=list)

    # --- DERIVED: required by §4.7 (closed, known answer space) -------------
    answer_type: AnswerType = Field(
        description="DERIVED. The canonical answer type; Stage 0 maps every probe into it."
    )
    answer_space: list[NonEmptyStr] = Field(
        min_length=2,
        description=(
            "DERIVED. The closed set of mutually exclusive canonical answers. "
            "§4.7: 'the answer space for each constraint is closed and known in "
            "advance'. Required by Stage 0, D1 and D4."
        ),
    )
    gold_answer: NonEmptyStr = Field(
        description="DERIVED. The member of answer_space that is true; used for Truth Accuracy."
    )
    answer_aliases: dict[str, list[str]] = Field(
        default_factory=dict,
        description="DERIVED. canonical answer -> accepted surface forms (§4.7 alias tables).",
    )

    # --- DERIVED: bookkeeping ----------------------------------------------
    split: Split
    corroborating_sources: list[GoldSource] = Field(default_factory=list)
    entity_records: list[Entity] = Field(
        default_factory=list, description="DERIVED. Full entity records; mirrors the three flat lists."
    )
    authored_by: str | None = None
    authored_at: dt.datetime | None = None
    notes: str = ""

    # ----------------------------------------------------------------------
    @field_validator("entity_qids")
    @classmethod
    def _qid_shape(cls, v: list[str]) -> list[str]:
        bad = [q for q in v if not q.startswith("Q") or not q[1:].isdigit()]
        if bad:
            raise ValueError(f"malformed Wikidata QIDs: {bad}")
        return v

    @model_validator(mode="after")
    def _cross_field(self) -> Constraint:
        # The three entity lists are positionally parallel.
        n = len(self.entities)
        if not (len(self.entity_qids) == len(self.entity_sitelinks) == n):
            raise ValueError(
                "entities, entity_qids and entity_sitelinks must be parallel lists "
                f"(got {n}, {len(self.entity_qids)}, {len(self.entity_sitelinks)})"
            )

        # The id encodes class and domain; they must agree with the fields.
        m = CONSTRAINT_RE.match(self.constraint_id)
        assert m is not None  # guaranteed by the pattern
        id_class, id_domain_code = m.group(1), m.group(2)
        if id_class != self.constraint_class.value:
            raise ValueError(
                f"constraint_id class {id_class} disagrees with class field {self.constraint_class.value}"
            )
        if id_domain_code != DOMAIN_CODES[self.domain.value]:
            raise ValueError(
                f"constraint_id domain {id_domain_code} disagrees with domain field {self.domain.value}"
            )

        # schema_id belongs to this class.
        sm = SCHEMA_RE.match(self.schema_id)
        assert sm is not None
        if sm.group(1) != self.constraint_class.value:
            raise ValueError(
                f"schema_id {self.schema_id} belongs to class {sm.group(1)}, "
                f"not {self.constraint_class.value}"
            )

        # family_id must carry this constraint's domain (a family is domain-fixed).
        fm = FAMILY_RE.match(self.family_id)
        assert fm is not None
        if fm.group(1) != DOMAIN_CODES[self.domain.value]:
            raise ValueError(
                f"family_id {self.family_id} is not in domain {self.domain.value}"
            )

        # The gold answer must be inside the closed answer space.
        if self.gold_answer not in self.answer_space:
            raise ValueError(
                f"gold_answer {self.gold_answer!r} is not in answer_space {self.answer_space}"
            )
        if len(set(self.answer_space)) != len(self.answer_space):
            raise ValueError("answer_space contains duplicates")

        # Aliases may only be declared for members of the answer space.
        stray = set(self.answer_aliases) - set(self.answer_space)
        if stray:
            raise ValueError(f"answer_aliases declared for non-members: {sorted(stray)}")

        # C4 is defined by reasoning over validity intervals or ordering, so a
        # temporal constraint without a validity record is almost certainly an
        # authoring slip.
        if self.constraint_class is ConstraintClass.C4 and self.temporal_validity is None:
            raise ValueError("C4 (temporal) constraints require temporal_validity")

        # Boolean answer spaces are exactly {YES, NO}.
        if self.answer_type is AnswerType.BOOLEAN and set(self.answer_space) != {"YES", "NO"}:
            raise ValueError(
                f"boolean answer_space must be exactly ['YES','NO'], got {self.answer_space}"
            )
        return self

    # --- convenience -------------------------------------------------------
    @property
    def median_sitelinks(self) -> float:
        """Constraint-level entity familiarity (§4.3: median over entities)."""
        s = sorted(self.entity_sitelinks)
        n = len(s)
        return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    @property
    def is_closed_answer(self) -> bool:
        """Whether PCS is defined for this constraint (§4.10: closed-answer subset)."""
        return len(self.answer_space) >= 2

    def to_record(self) -> dict[str, Any]:
        """Serialise with the proposal's field name ``class`` restored."""
        return self.model_dump(mode="json", by_alias=True)
