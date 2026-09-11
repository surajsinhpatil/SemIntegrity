"""Reference predicate: temporal interval precedence (C4, proposal §4.8.2).

Formalises the proposal's own worked example:

    # C4 schema: office cannot be held before it existed
    def check(responses, kb):
      for r in responses:
        if r.label in (ABSTAIN, INVALID): continue
        if r.start_date < kb.office_creation_date(r.office): return VIOLATION
      return SATISFIED

Two differences from the sketch, both required by the surrounding design:

* the pairwise form is provided as well, because PSCR counts contradictory
  **pairs** (§4.10) while the sketch is set-level (see Q22);
* the knowledge-base lookup goes through the :class:`KnowledgeBase` protocol so
  it resolves from the frozen snapshot, never the live network.

Like the C1 reference predicate this carries no facts of its own: the entity,
the property and the anchor date all come from the constraint and the KB.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from ....schemas.enums import Verdict
from ..base import D0Predicate, D0Result, KnowledgeBase
from ..registry import register

if TYPE_CHECKING:  # pragma: no cover
    from ....schemas.constraint import Constraint
    from ....schemas.response import CanonicalResponse


def _parse_iso(value: str) -> dt.date | None:
    """Parse a canonicalised date answer. Year-only answers clamp to 1 January."""
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


@register
class C4IntervalPrecedence(D0Predicate):
    predicate_name = "c4_interval_precedence"
    schema_id = "S-C4-00"  # reference schema
    version = "1.0"
    formal_statement = (
        "For a constraint with an establishment anchor T0 (from temporal_validity.start): "
        "a date response d violates the constraint iff d < T0. Two date responses "
        "contradict iff they differ, or iff either precedes T0."
    )

    def _anchor(self, constraint: Constraint) -> dt.date | None:
        tv = constraint.temporal_validity
        return tv.start if tv else None

    def check_pair(
        self,
        constraint: Constraint,
        a: CanonicalResponse,
        b: CanonicalResponse,
        kb: KnowledgeBase,
    ) -> D0Result:
        if a.canonical_answer is None or b.canonical_answer is None:
            return D0Result(
                Verdict.NOT_APPLICABLE, self.predicate_name, self.schema_id,
                reason="a non-answer response cannot participate in a pairwise check",
            )

        da, db = _parse_iso(a.canonical_answer), _parse_iso(b.canonical_answer)
        if da is None or db is None:
            return D0Result(
                Verdict.NOT_APPLICABLE, self.predicate_name, self.schema_id,
                reason=(
                    f"unparseable date answer(s): "
                    f"{[r.canonical_answer for r, d in ((a, da), (b, db)) if d is None]}"
                ),
            )

        anchor = self._anchor(constraint)
        if anchor is None:
            return D0Result(
                Verdict.NOT_APPLICABLE, self.predicate_name, self.schema_id,
                reason="constraint has no temporal anchor; D0 cannot verify precedence",
            )

        too_early = [
            (r.probe_id, d) for r, d in ((a, da), (b, db)) if d < anchor
        ]
        if too_early:
            return D0Result(
                Verdict.VIOLATION, self.predicate_name, self.schema_id,
                reason=(
                    f"date(s) precede the establishment anchor {anchor.isoformat()}: "
                    + ", ".join(f"{pid}={d.isoformat()}" for pid, d in too_early)
                ),
                conflicting_pairs=((a.probe_id, b.probe_id),),
                kb_facts_used=(f"anchor({constraint.constraint_id})={anchor.isoformat()}",),
            )

        if da != db:
            return D0Result(
                Verdict.VIOLATION, self.predicate_name, self.schema_id,
                reason=f"incompatible dates: {a.probe_id}={da.isoformat()} vs {b.probe_id}={db.isoformat()}",
                conflicting_pairs=((a.probe_id, b.probe_id),),
            )
        return D0Result(
            Verdict.SATISFIED, self.predicate_name, self.schema_id,
            reason=f"both responses give {da.isoformat()}, which is on or after {anchor.isoformat()}",
        )
