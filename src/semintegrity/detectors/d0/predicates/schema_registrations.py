"""Per-schema D0 registrations for the 120-constraint test design.

Approved 2026-10-06 (decision A5). The scope is deliberately narrow, and the
narrowness is the decision rather than a shortfall.

Two behaviours are implemented in this codebase and only two are decidable from
a Track A response at all:

``EXCL``
    Closed-space mutual exclusion, from :class:`C1MutualExclusion`. That class
    documents itself as *schema-general*: it carries no facts and consults no
    knowledge base. Over a closed, mutually exclusive answer space -- which §4.7
    requires of every constraint -- pairwise contradiction simply *is* "the two
    canonical answers differ". Every one of the 24 schemas gets this.

``ANCHOR``
    Temporal anchor precedence, from :class:`C4IntervalPrecedence`. The only
    predicate that decides something ``EXCL`` cannot: a **single** response dated
    before ``temporal_validity.start`` is a VIOLATION even when both responses
    agree. It needs a parseable date answer, so it reaches only the two
    ``date``-typed axes (4 and 6), i.e. 8 of the 24 schemas.

What is **not** here, and why no amount of implementation effort would add it:
the C2 and C3 class structures are not recoverable from a Track A response. The
probe asks the conjunction, or the instantiated universal, as a whole and the
model returns one token. Conjunct-level information exists only in
``prerequisite_atomic_facts``, which the knowledge screen asks separately, and
§4.11 makes that "a reporting view, never an inclusion criterion". Admitting it
into D0 would change D0's role and is a methodology decision, not a coding task.
Every C2 and C3 ``formal_statement`` below therefore says in words what it does
not formalise, and that text is copied into the freeze manifest (§4.8.2) and into
every audit record.

§4.8.1 makes D0 coverage "a RESULT in its own right, not a diagnostic", so
stating the limit honestly is the requirement -- not a concession to it.

The classes are written out rather than generated in a loop on purpose:
:meth:`D0Predicate.source_hash` hashes ``inspect.getsource(type(self))``, and a
dynamically built class falls back to ``repr``, which would silently weaken the
freeze guarantee §4.8.2 depends on.

The pilot's four predicate names (``c1_mutual_exclusion``, ``c2_conjunction``,
``c3_functional_uniqueness``, ``c4_interval_precedence``) are untouched and keep
serving the 12 pilot/dev constraints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..base import D0Predicate, D0Result, KnowledgeBase
from ..registry import register
from .c1_mutual_exclusion import C1MutualExclusion
from .c4_interval_precedence import C4IntervalPrecedence

if TYPE_CHECKING:  # pragma: no cover
    from ....schemas.constraint import Constraint
    from ....schemas.response import CanonicalResponse


class _SchemaExclusion(D0Predicate):
    """``EXCL`` only: differing canonical answers contradict."""

    def check_pair(
        self,
        constraint: Constraint,
        a: CanonicalResponse,
        b: CanonicalResponse,
        kb: KnowledgeBase,
    ) -> D0Result:
        inner = C1MutualExclusion().check_pair(constraint, a, b, kb)
        return D0Result(
            verdict=inner.verdict,
            predicate=self.predicate_name,
            schema_id=self.schema_id,
            reason=inner.reason,
            conflicting_pairs=inner.conflicting_pairs,
            skipped_probe_ids=inner.skipped_probe_ids,
            kb_facts_used=inner.kb_facts_used,
        )


class _SchemaAnchor(D0Predicate):
    """``EXCL`` + ``ANCHOR``: mutual exclusion, then the temporal anchor.

    The anchor check runs first because it can fire on a pair whose answers
    AGREE, which mutual exclusion would call SATISFIED. Where the anchor check
    cannot apply -- an unparseable date, or no recorded anchor -- it returns
    NOT_APPLICABLE and the mutual-exclusion verdict stands rather than the pair
    being dropped.
    """

    def check_pair(
        self,
        constraint: Constraint,
        a: CanonicalResponse,
        b: CanonicalResponse,
        kb: KnowledgeBase,
    ) -> D0Result:
        anchored = C4IntervalPrecedence().check_pair(constraint, a, b, kb)
        inner = anchored if anchored.verdict.value != "NOT_APPLICABLE" else (
            C1MutualExclusion().check_pair(constraint, a, b, kb)
        )
        return D0Result(
            verdict=inner.verdict,
            predicate=self.predicate_name,
            schema_id=self.schema_id,
            reason=inner.reason,
            conflicting_pairs=inner.conflicting_pairs,
            skipped_probe_ids=inner.skipped_probe_ids,
            kb_facts_used=inner.kb_facts_used,
        )



# --- axis 1: Unique designated role-bearer ---------------
@register
class SchemaC101(_SchemaExclusion):
    predicate_name = "s_c1_01"
    schema_id = "S-C1-01"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C1-01's answer space (entity): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are entity, not dates, so interval "
        "precedence is NOT_APPLICABLE."
    )

@register
class SchemaC201(_SchemaExclusion):
    predicate_name = "s_c2_01"
    schema_id = "S-C2-01"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C2-01's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT verify the conjuncts separately: "
        "a model that answered on the strength of one conjunct is "
        "indistinguishable, in a single canonical answer, from one that checked "
        "both."
    )

@register
class SchemaC301(_SchemaExclusion):
    predicate_name = "s_c3_01"
    schema_id = "S-C3-01"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C3-01's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT represent the universal "
        "quantifier or its variable binding: the probe asks the instantiated "
        "claim and the response carries one token."
    )

@register
class SchemaC401(_SchemaExclusion):
    predicate_name = "s_c4_01"
    schema_id = "S-C4-01"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C4-01's answer space (entity): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are entity, not dates, so interval "
        "precedence is NOT_APPLICABLE."
    )


# --- axis 2: Disjoint category membership ----------------
@register
class SchemaC102(_SchemaExclusion):
    predicate_name = "s_c1_02"
    schema_id = "S-C1-02"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C1-02's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE."
    )

@register
class SchemaC202(_SchemaExclusion):
    predicate_name = "s_c2_02"
    schema_id = "S-C2-02"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C2-02's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT verify the conjuncts separately: "
        "a model that answered on the strength of one conjunct is "
        "indistinguishable, in a single canonical answer, from one that checked "
        "both."
    )

@register
class SchemaC302(_SchemaExclusion):
    predicate_name = "s_c3_02"
    schema_id = "S-C3-02"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C3-02's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT represent the universal "
        "quantifier or its variable binding: the probe asks the instantiated "
        "claim and the response carries one token."
    )

@register
class SchemaC402(_SchemaExclusion):
    predicate_name = "s_c4_02"
    schema_id = "S-C4-02"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C4-02's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE."
    )


# --- axis 3: Part-whole containment ----------------------
@register
class SchemaC103(_SchemaExclusion):
    predicate_name = "s_c1_03"
    schema_id = "S-C1-03"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C1-03's answer space (entity): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are entity, not dates, so interval "
        "precedence is NOT_APPLICABLE."
    )

@register
class SchemaC203(_SchemaExclusion):
    predicate_name = "s_c2_03"
    schema_id = "S-C2-03"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C2-03's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT verify the conjuncts separately: "
        "a model that answered on the strength of one conjunct is "
        "indistinguishable, in a single canonical answer, from one that checked "
        "both."
    )

@register
class SchemaC303(_SchemaExclusion):
    predicate_name = "s_c3_03"
    schema_id = "S-C3-03"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C3-03's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT represent the universal "
        "quantifier or its variable binding: the probe asks the instantiated "
        "claim and the response carries one token."
    )

@register
class SchemaC403(_SchemaExclusion):
    predicate_name = "s_c4_03"
    schema_id = "S-C4-03"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C4-03's answer space (entity): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are entity, not dates, so interval "
        "precedence is NOT_APPLICABLE."
    )


# --- axis 4: Event precedence ----------------------------
@register
class SchemaC104(_SchemaAnchor):
    predicate_name = "s_c1_04"
    schema_id = "S-C1-04"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C1-04's answer space (date): "
        "responses contradict iff their canonical answers differ. Plus temporal "
        "anchor precedence: a response dated before temporal_validity.start is a "
        "VIOLATION even when both responses agree."
    )

@register
class SchemaC204(_SchemaExclusion):
    predicate_name = "s_c2_04"
    schema_id = "S-C2-04"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C2-04's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT verify the conjuncts separately: "
        "a model that answered on the strength of one conjunct is "
        "indistinguishable, in a single canonical answer, from one that checked "
        "both."
    )

@register
class SchemaC304(_SchemaExclusion):
    predicate_name = "s_c3_04"
    schema_id = "S-C3-04"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C3-04's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT represent the universal "
        "quantifier or its variable binding: the probe asks the instantiated "
        "claim and the response carries one token."
    )

@register
class SchemaC404(_SchemaAnchor):
    predicate_name = "s_c4_04"
    schema_id = "S-C4-04"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C4-04's answer space (date): "
        "responses contradict iff their canonical answers differ. Plus temporal "
        "anchor precedence: a response dated before temporal_validity.start is a "
        "VIOLATION even when both responses agree."
    )


# --- axis 5: Extremal uniqueness -------------------------
@register
class SchemaC105(_SchemaExclusion):
    predicate_name = "s_c1_05"
    schema_id = "S-C1-05"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C1-05's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE."
    )

@register
class SchemaC205(_SchemaExclusion):
    predicate_name = "s_c2_05"
    schema_id = "S-C2-05"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C2-05's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT verify the conjuncts separately: "
        "a model that answered on the strength of one conjunct is "
        "indistinguishable, in a single canonical answer, from one that checked "
        "both."
    )

@register
class SchemaC305(_SchemaExclusion):
    predicate_name = "s_c3_05"
    schema_id = "S-C3-05"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C3-05's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT represent the universal "
        "quantifier or its variable binding: the probe asks the instantiated "
        "claim and the response carries one token."
    )

@register
class SchemaC405(_SchemaExclusion):
    predicate_name = "s_c4_05"
    schema_id = "S-C4-05"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C4-05's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE."
    )


# --- axis 6: Interval boundary ---------------------------
@register
class SchemaC106(_SchemaAnchor):
    predicate_name = "s_c1_06"
    schema_id = "S-C1-06"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C1-06's answer space (date): "
        "responses contradict iff their canonical answers differ. Plus temporal "
        "anchor precedence: a response dated before temporal_validity.start is a "
        "VIOLATION even when both responses agree."
    )

@register
class SchemaC206(_SchemaExclusion):
    predicate_name = "s_c2_06"
    schema_id = "S-C2-06"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C2-06's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT verify the conjuncts separately: "
        "a model that answered on the strength of one conjunct is "
        "indistinguishable, in a single canonical answer, from one that checked "
        "both."
    )

@register
class SchemaC306(_SchemaExclusion):
    predicate_name = "s_c3_06"
    schema_id = "S-C3-06"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C3-06's answer space (boolean): "
        "responses contradict iff their canonical answers differ. No anchor "
        "check: this schema's answers are boolean, not dates, so interval "
        "precedence is NOT_APPLICABLE. Does NOT represent the universal "
        "quantifier or its variable binding: the probe asks the instantiated "
        "claim and the response carries one token."
    )

@register
class SchemaC406(_SchemaAnchor):
    predicate_name = "s_c4_06"
    schema_id = "S-C4-06"
    version = "1.1"
    formal_statement = (
        "Closed-space mutual exclusion over S-C4-06's answer space (date): "
        "responses contradict iff their canonical answers differ. Plus temporal "
        "anchor precedence: a response dated before temporal_validity.start is a "
        "VIOLATION even when both responses agree."
    )

