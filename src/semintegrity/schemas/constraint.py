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
import re
from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..utils.ids import CONSTRAINT_RE, DOMAIN_CODES, FAMILY_RE, SCHEMA_RE
from .enums import AnswerType, ConstraintClass, Domain, Split, VerificationStatus

NonEmptyStr = Annotated[str, Field(min_length=1)]

#: Providers that are the PRIMARY source and so can never be the second one.
#: Mirrors corroboration_policy.yaml's excluded_as_second_source.
_PRIMARY_PROVIDERS: frozenset[str] = frozenset({"wikidata", "wikidata.org", "wikibase"})

#: Hosts that are not real sources. A placeholder URL is not retrievable, and a
#: corroborating source that cannot be retrieved cannot be re-checked.
_PLACEHOLDER_HOSTS: tuple[str, ...] = (
    "example.com", "example.org", "example.net", "example.invalid",
    "invalid", "test.test", "placeholder",
)


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


class CorroboratingSource(GoldSource):
    """An INDEPENDENT second authoritative source (§4.3).

    §4.3 requires that "all historical and temporal facts are corroborated
    against a second authoritative source". This is that source. It extends
    :class:`GoldSource` rather than duplicating it: name, url, retrieved and
    note are inherited, and the four fields a *corroborator* additionally needs
    are added here, unconditionally required, so there is no model whose fields
    are required only sometimes.

    The five properties §4.3's requirement needs, and the field that carries
    each:

    ===============  ===========================================================
    identifiable     ``provider`` — and it must appear in the approved list
    retrievable      ``url`` — absolute, and not a placeholder
    frozen           ``snapshot`` + ``content_hash``
    separate         ``provider`` must not be the primary source
    tied to the fact ``fact_supported``
    ===============  ===========================================================

    **Being well-formed is not the same as counting.** Whether a provider is an
    independent authoritative source is a methodology decision recorded in
    ``configs/benchmark/corroboration_policy.yaml``, which is deliberately
    unconfigured. A perfectly well-formed instance of this class does not
    satisfy §4.3 until that policy names its provider.
    """

    model_config = ConfigDict(extra="forbid")

    provider: NonEmptyStr = Field(
        description=(
            "the source's provider id, checked against "
            "corroboration_policy.yaml's approved_independent_providers"
        )
    )
    snapshot: NonEmptyStr = Field(
        description="key in the corroboration store (KBCache kind='corroboration')"
    )
    content_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="sha256 of the retrieved artefact; makes the retrieval replayable",
    )
    fact_supported: NonEmptyStr = Field(
        description="the exact proposition this source corroborates, in words"
    )

    @model_validator(mode="after")
    def _is_a_second_source(self) -> CorroboratingSource:
        # NonEmptyStr is min_length=1, so "   " would otherwise pass. A
        # whitespace-only provider, snapshot or fact is as useless as an absent
        # one, and worse because it looks populated.
        blank = [
            field
            for field in ("name", "provider", "snapshot", "fact_supported")
            if not str(getattr(self, field)).strip()
        ]
        if blank:
            raise ValueError(
                f"{blank} must not be blank; whitespace is not a value. A "
                "corroborating source that looks populated but is not is worse than "
                "one that is absent."
            )
        if self.is_primary:
            raise ValueError(
                "a corroborating source cannot be is_primary: §4.3's second source is "
                "by definition not the primary one"
            )
        # The primary source cannot corroborate itself. A second Wikidata
        # statement, a reference URL or a P248 value is mediated by the primary
        # source and is not automatically independent; whether any of them may
        # count is an OPEN methodology question (corroboration_policy.yaml).
        if self.provider.strip().lower() in _PRIMARY_PROVIDERS:
            raise ValueError(
                f"provider {self.provider!r} is the primary source, so it cannot be the "
                "second one. A Wikidata reference, a P248 value or another statement on "
                "the same claim is NOT automatically an independent source"
            )
        host = urlparse(self.url).netloc.lower()
        if not host or not urlparse(self.url).scheme:
            raise ValueError(
                f"url {self.url!r} is not an absolute, retrievable URL"
            )
        if any(bad in host for bad in _PLACEHOLDER_HOSTS) or host.startswith("localhost"):
            raise ValueError(
                f"url {self.url!r} is a placeholder host ({host!r}); a corroborating "
                "source must be actually retrievable"
            )
        return self

    @property
    def url_host(self) -> str:
        return urlparse(self.url).netloc.lower()


class Evidence(BaseModel):
    """One machine-checked lookup supporting (or contradicting) the gold answer.

    Records what was asked, what came back, and whether it agrees — so an
    EVIDENCE_VERIFIED claim can be re-checked from the record alone rather than
    taken on trust.
    """

    model_config = ConfigDict(extra="forbid")

    source: NonEmptyStr = Field(description="e.g. 'wikidata'")
    query: NonEmptyStr = Field(description="what was asked, e.g. 'Q408 P36'")
    url: NonEmptyStr
    retrieved_at: dt.date
    observed_value: str = Field(description="verbatim value returned; empty if nothing was found")
    supports_gold: bool = Field(
        description="whether the observed value agrees with gold_answer, by an explicit comparison"
    )
    comparison: NonEmptyStr = Field(description="how the comparison was made, in words")
    note: str = ""


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


#: Schema indices whose semantics are extremal — a superlative over a comparison
#: set. Under ADR-0002's lattice the schema index IS the axis index, and axis 5
#: is "Extremal uniqueness" in `docs/BENCHMARK_COVERAGE_MATRIX.md`. A superlative
#: has no truth value until the set the maximum is taken over is fixed, which is
#: why these schemas — and only these — must carry a frozen comparison universe.
#: Pinned against the matrix by ``tests/unit/test_comparison_universe.py``.
EXTREMAL_SCHEMA_INDICES: frozenset[int] = frozenset({5})


class UniverseMember(BaseModel):
    """One member of an explicitly enumerated comparison set.

    ``measure_value`` is recorded **verbatim as retrieved**, not re-fetched: the
    whole point of the record is that the comparison can be re-checked without
    the live knowledge base agreeing with its past self.
    """

    model_config = ConfigDict(extra="forbid")

    label: NonEmptyStr
    qid: str = Field(pattern=r"^Q\d+$")
    measure_value: NonEmptyStr = Field(
        description="the measured quantity as retrieved, with its unit, e.g. '5895 metre'"
    )


class RankedSource(BaseModel):
    """An authoritative ranking, frozen, standing in for an enumerated set.

    Used where enumerating the universe is impractical — "the heaviest naturally
    occurring element" ranges over a set no one would list by hand. The ranking
    must be reproducible from the record: ``snapshot`` names its entry in the
    frozen cache (ADR-0011) so the job never depends on live external state, and
    ``rank_of_argmax`` states where the asserted extremal bearer sits, so "this
    source says so" is checkable rather than asserted.

    ``rank_of_argmax`` was called ``rank_of_gold`` and documented as the GOLD
    ANSWER's position. ADR-0017 Option B made axis 5 boolean, so the gold answer
    is YES or NO and has no position in a ranking of summits — the old name
    named the wrong object. It is **renamed, not reinterpreted**: the field now
    refers to :attr:`ComparisonUniverse.argmax_qid`, and nothing carries the old
    meaning. See the 2026-10-07 amendment in ADR-0018.
    """

    model_config = ConfigDict(extra="forbid")

    name: NonEmptyStr = Field(description="e.g. 'Wikidata SPARQL' or a named reference work")
    url: NonEmptyStr
    retrieved: dt.date
    snapshot: NonEmptyStr = Field(
        description="key or path in the FROZEN snapshot; never a live endpoint"
    )
    query: str = Field(default="", description="the ranked query, if the ranking was computed")
    rank_of_argmax: int = Field(
        ge=1,
        description=(
            "the ASSERTED EXTREMAL BEARER's position in this ranking. An extremal "
            "claim requires 1: the bearer heads the ordering. Renamed from "
            "rank_of_gold, which named the gold answer and so named the wrong "
            "object once axis 5 became boolean."
        ),
    )


class ComparisonUniverse(BaseModel):
    """The set a superlative is taken over (§4.3 ground truth, axis 5).

    A superlative is not a proposition until its universe is fixed: "the highest
    summit" is true of Everest, Kilimanjaro or Ben Nevis depending on whether the
    universe is the world, Africa or Scotland. Recording only the answer space
    does not fix it — {Kilimanjaro, Mount Kenya, Ras Dashen} does not say
    "summits in Africa" — so the universe is represented here instead, and
    becomes part of the frozen ground-truth record.

    Exactly one of ``members`` or ``ranked_source`` is supplied. Prose in
    ``ambiguity_notes`` is explicitly **not** a substitute: nothing can validate
    it, and the requirement would be enforced in name only.

    The universe is **answer-type independent**. The entity the constraint
    asserts to be the extremum is recorded here as ``argmax_qid`` /
    ``argmax_label``, never inferred from ``gold_answer``: under ADR-0017 Option
    B axis 5 is boolean, so the gold answer is YES or NO and is not the bearer of
    anything. See the 2026-10-07 amendment in ADR-0018.
    """

    model_config = ConfigDict(extra="forbid")

    universe: NonEmptyStr = Field(
        description="what is being compared, e.g. 'summits wholly within Africa'"
    )
    membership_rule: NonEmptyStr = Field(
        description=(
            "how membership is decided, precisely enough to rebuild the set — "
            "e.g. 'Wikidata P31/P279* Q8502 (mountain) AND P30 Q15 (Africa)'"
        )
    )
    measure: NonEmptyStr = Field(
        description="the quantity ordered over, with its property — e.g. 'elevation (P2044)'"
    )
    direction: str = Field(
        pattern="^(max|min)$",
        description=(
            "which extremum the superlative names: 'max' for highest/largest/"
            "heaviest, 'min' for earliest/shortest/lightest. Required, because "
            "whether the bearer is the maximum or the minimum is load-bearing."
        ),
    )
    argmax_qid: str = Field(
        pattern=r"^Q\d+$",
        description=(
            "the entity the constraint ASSERTS is the extremum. Not the gold "
            "answer: axis 5 is boolean, so gold is YES/NO."
        ),
    )
    argmax_label: NonEmptyStr = Field(
        description="label of the asserted extremal bearer; must match its member"
    )
    frozen_at: dt.date = Field(description="when this universe was fixed; provenance, not publication")
    members: list[UniverseMember] = Field(
        default_factory=list,
        description="the enumerated set; at least 2 members, or use ranked_source",
    )
    ranked_source: RankedSource | None = None
    note: str = ""

    @staticmethod
    def _numeric(measure_value: str) -> float | None:
        """Leading numeric part of a recorded measure, e.g. '5895 metre' -> 5895.0.

        Returns None when the value is not numeric, in which case the extremum
        relationship is not machine-checkable and is not checked. Reporting a
        pass there would be a check that cannot fail.
        """
        m = re.match(r"\s*([+-]?\d+(?:\.\d+)?)", measure_value)
        return float(m.group(1)) if m else None

    @model_validator(mode="after")
    def _coherent(self) -> ComparisonUniverse:
        # A boolean truth value is never a member of a comparison universe. This
        # guard exists because a test once passed by enumerating a member
        # labelled "YES", which satisfied an earlier gold-answer check while
        # recording nonsense.
        booleans = {"yes", "no"}
        if self.argmax_label.strip().lower() in booleans:
            raise ValueError(
                f"argmax_label {self.argmax_label!r} is a boolean truth value, not an "
                "entity. The asserted extremal bearer is an entity; the YES/NO is the "
                "gold answer and belongs nowhere in the universe."
            )
        bad_members = [m.label for m in self.members if m.label.strip().lower() in booleans]
        if bad_members:
            raise ValueError(
                f"comparison-set members {bad_members} are boolean truth values, not "
                "entities; a universe cannot contain YES or NO"
            )

        has_members, has_source = bool(self.members), self.ranked_source is not None
        if has_members and has_source:
            raise ValueError(
                "supply EITHER an enumerated `members` set OR a `ranked_source`, not both: "
                "two bases for one comparison invite silent disagreement between them"
            )
        if not has_members and not has_source:
            raise ValueError(
                "a comparison universe needs a basis: either `members` (>= 2) or a "
                "`ranked_source`. Prose is not a basis"
            )
        if has_members:
            if len(self.members) < 2:
                raise ValueError(
                    f"an enumerated comparison set needs at least 2 members, got "
                    f"{len(self.members)}; a superlative over one thing is vacuous"
                )
            qids = [m.qid for m in self.members]
            if len(set(qids)) != len(qids):
                raise ValueError(f"duplicate QIDs in the comparison set: {sorted(qids)}")

            by_qid = {m.qid: m for m in self.members}
            bearer = by_qid.get(self.argmax_qid)
            if bearer is None:
                raise ValueError(
                    f"argmax_qid {self.argmax_qid!r} is not among the enumerated members "
                    f"{sorted(qids)}; the asserted extremum must lie inside the universe "
                    "it ranges over"
                )
            if bearer.label != self.argmax_label:
                raise ValueError(
                    f"argmax_label {self.argmax_label!r} does not match member "
                    f"{self.argmax_qid} whose label is {bearer.label!r}"
                )

            # The extremum relationship itself, where the recorded measures make
            # it checkable. If any value is non-numeric the comparison is left to
            # human review rather than silently passed.
            parsed = {m.qid: self._numeric(m.measure_value) for m in self.members}
            if all(v is not None for v in parsed.values()):
                values: dict[str, float] = {
                    q: v for q, v in parsed.items() if v is not None
                }
                chosen = values[self.argmax_qid]
                others = [v for q, v in values.items() if q != self.argmax_qid]
                worse = (
                    [v for v in others if v > chosen]
                    if self.direction == "max"
                    else [v for v in others if v < chosen]
                )
                if worse:
                    word = "greater" if self.direction == "max" else "smaller"
                    raise ValueError(
                        f"{self.argmax_label!r} is asserted as the {self.direction} of "
                        f"{self.measure} at {chosen}, but {len(worse)} member(s) record a "
                        f"{word} value ({sorted(worse)}); the asserted bearer is not the "
                        "extremum of the recorded measures"
                    )
        else:
            source = self.ranked_source
            assert source is not None
            if source.rank_of_argmax != 1:
                raise ValueError(
                    f"ranked_source puts the asserted extremal bearer at rank "
                    f"{source.rank_of_argmax}; an extremal claim requires rank 1, since "
                    "the bearer must head the ordering"
                )
        return self


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
    comparison_universe: ComparisonUniverse | None = Field(
        default=None,
        description=(
            "DERIVED. The set a superlative is taken over. REQUIRED for extremal "
            "schemas (see EXTREMAL_SCHEMA_INDICES) before they may leave DRAFT, and "
            "not used by the other schemas."
        ),
    )

    # --- DERIVED: verification ladder --------------------------------------
    # Integrity tracking (ADR-0012). Not part of the proposal's 17 fields; added
    # so that "verified" is a checkable state rather than a claim in prose.
    verification_status: VerificationStatus = VerificationStatus.DRAFT
    evidence: list[Evidence] = Field(default_factory=list)
    human_validated_by: str | None = Field(
        default=None, description="NAMED human. Never set by any automated process."
    )
    human_validated_at: dt.date | None = None
    review_notes: str = Field(
        default="", description="what a human reviewer still needs to check"
    )

    # --- DERIVED: bookkeeping ----------------------------------------------
    split: Split
    corroborating_sources: list[CorroboratingSource] = Field(
        default_factory=list,
        description=(
            "§4.3's independent second sources. Well-formed entries here still do "
            "not satisfy §4.3 until corroboration_policy.yaml names their provider."
        ),
    )
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

        # --- verification ladder: a rung may not be claimed without its basis ---
        if self.verification_status is VerificationStatus.EVIDENCE_VERIFIED and not any(
            e.supports_gold for e in self.evidence
        ):
            raise ValueError(
                f"{self.constraint_id}: EVIDENCE_VERIFIED requires at least one Evidence "
                "record with supports_gold=True; none is present"
            )
        if self.verification_status in (
            VerificationStatus.HUMAN_VALIDATED,
            VerificationStatus.FROZEN,
        ):
            if not (self.human_validated_by or "").strip():
                raise ValueError(
                    f"{self.constraint_id}: {self.verification_status.value} requires a NAMED "
                    "human validator in human_validated_by. This status is never set "
                    "automatically and must never be claimed on a human's behalf."
                )
            if self.human_validated_at is None:
                raise ValueError(
                    f"{self.constraint_id}: {self.verification_status.value} requires "
                    "human_validated_at"
                )

        # --- extremal schemas need their comparison universe -----------------
        # A superlative has no truth value until the universe is fixed, so for an
        # extremal schema the universe is part of the ground truth rather than
        # commentary on it. It is REQUIRED to leave DRAFT, and `ambiguity_notes`
        # is deliberately not consulted: prose cannot be validated, and a
        # requirement that is checked by looking for prose is not enforced.
        sm2 = SCHEMA_RE.match(self.schema_id)
        assert sm2 is not None
        is_extremal = int(sm2.group(2)) in EXTREMAL_SCHEMA_INDICES
        if (
            is_extremal
            and self.verification_status is not VerificationStatus.DRAFT
            and self.comparison_universe is None
        ):
            raise ValueError(
                f"{self.constraint_id}: schema {self.schema_id} is extremal, so "
                f"{self.verification_status.value} requires a `comparison_universe`. "
                "A superlative is not a proposition until the set it ranges over is "
                "fixed, and that set must be frozen in the record — prose in "
                "ambiguity_notes is not a substitute."
            )

        # The universe must belong to THIS constraint. The old check compared
        # `gold_answer` against the members, which was the wrong object: under
        # ADR-0017 Option B axis 5 is boolean, so gold is YES/NO and is not the
        # bearer of anything. What ties the two together is the asserted extremal
        # bearer, which must be one of the constraint's own entities.
        cu = self.comparison_universe
        if cu is not None and cu.argmax_qid not in self.entity_qids:
            raise ValueError(
                f"{self.constraint_id}: the comparison universe asserts {cu.argmax_qid} "
                f"({cu.argmax_label!r}) as the extremum, but that QID is not among the "
                f"constraint's entities {self.entity_qids}; a universe about a different "
                "entity is not this constraint's universe"
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
