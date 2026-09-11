"""Reference predicate: atomic mutual exclusion (C1, proposal §4.2).

    "A single proposition with direct mutual exclusion."

This is the simplest formalisation in the taxonomy and is schema-general: given
a constraint whose answer space is a closed set of mutually exclusive canonical
answers, two responses contradict exactly when they name different members.

It is **infrastructure, not content** — it carries no facts of its own and
applies to any C1 schema whose answer space is mutually exclusive. Schema-specific
predicates are authored in Phase 5 alongside their constraints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....schemas.enums import Verdict
from ..base import D0Predicate, D0Result, KnowledgeBase
from ..registry import register

if TYPE_CHECKING:  # pragma: no cover
    from ....schemas.constraint import Constraint
    from ....schemas.response import CanonicalResponse


@register
class C1MutualExclusion(D0Predicate):
    predicate_name = "c1_mutual_exclusion"
    schema_id = "S-C1-00"  # reference schema; concrete schemas subclass or re-register
    version = "1.0"
    formal_statement = (
        "For a constraint with a closed, mutually exclusive answer space A: "
        "responses r1, r2 contradict iff canonical(r1) != canonical(r2)."
    )

    def check_pair(
        self,
        constraint: Constraint,
        a: CanonicalResponse,
        b: CanonicalResponse,
        kb: KnowledgeBase,
    ) -> D0Result:
        if a.canonical_answer is None or b.canonical_answer is None:
            return D0Result(
                Verdict.NOT_APPLICABLE,
                self.predicate_name,
                self.schema_id,
                reason="a non-answer response cannot participate in a pairwise check",
                skipped_probe_ids=tuple(
                    r.probe_id for r in (a, b) if r.canonical_answer is None
                ),
            )

        space = set(constraint.answer_space)
        unknown = {a.canonical_answer, b.canonical_answer} - space
        if unknown:
            # Stage 0 should never emit an answer outside the closed space; if it
            # does, that is a canonicalisation bug and D0 must not paper over it.
            return D0Result(
                Verdict.NOT_APPLICABLE,
                self.predicate_name,
                self.schema_id,
                reason=(
                    f"canonical answer(s) {sorted(unknown)} are outside the constraint's "
                    f"closed answer space — canonicalisation bug, not a contradiction"
                ),
            )

        if a.canonical_answer == b.canonical_answer:
            return D0Result(
                Verdict.SATISFIED,
                self.predicate_name,
                self.schema_id,
                reason=f"both responses give {a.canonical_answer!r}",
            )
        return D0Result(
            Verdict.VIOLATION,
            self.predicate_name,
            self.schema_id,
            reason=(
                f"mutually exclusive answers: {a.probe_id}={a.canonical_answer!r} vs "
                f"{b.probe_id}={b.canonical_answer!r}"
            ),
            conflicting_pairs=((a.probe_id, b.probe_id),),
        )
