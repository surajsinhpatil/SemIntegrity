"""Placeholder predicates for C2 and C3 pilot schemas.

**These formalise only the mutual-exclusion property of a closed answer space.**
They do *not* formalise the structure their names refer to: ``c2_conjunction``
does not check the two conjuncts separately, and ``c3_functional_uniqueness``
does not represent the quantifier or its variable binding. Over a closed answer
space both reduce to "two canonicalised answers contradict iff they differ",
which is exactly what :mod:`c1_mutual_exclusion` already does.

They exist so the pilot has D0 coverage that is *real* rather than absent, and
so the registry, freeze and audit machinery is exercised end to end. **Genuine
schema-specific predicates are Phase 5 work**, and until they are written, D0's
verdict on a C2 or C3 pilot constraint should be read as a mutual-exclusion
check and nothing more. The `formal_statement` on each class says so, and it is
copied into the freeze manifest and every audit record.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..base import D0Predicate, D0Result, KnowledgeBase
from ..registry import register
from .c1_mutual_exclusion import C1MutualExclusion

if TYPE_CHECKING:  # pragma: no cover
    from .....schemas.constraint import Constraint
    from .....schemas.response import CanonicalResponse


class _ClosedSpaceExclusion(D0Predicate):
    """Shared behaviour: differing canonical answers contradict."""

    def check_pair(
        self,
        constraint: Constraint,
        a: CanonicalResponse,
        b: CanonicalResponse,
        kb: KnowledgeBase,
    ) -> D0Result:
        delegate = C1MutualExclusion()
        result = delegate.check_pair(constraint, a, b, kb)
        return D0Result(
            verdict=result.verdict,
            predicate=self.predicate_name,
            schema_id=self.schema_id,
            reason=result.reason,
            conflicting_pairs=result.conflicting_pairs,
            skipped_probe_ids=result.skipped_probe_ids,
            kb_facts_used=result.kb_facts_used,
        )


@register
class C2Conjunction(_ClosedSpaceExclusion):
    predicate_name = "c2_conjunction"
    schema_id = "S-C2-01"
    version = "0.1-placeholder"
    formal_statement = (
        "PLACEHOLDER. Checks mutual exclusion over the closed answer space only; "
        "does NOT verify the conjuncts separately. A model that answers YES on the "
        "strength of one conjunct is indistinguishable from one that checked both."
    )


@register
class C3FunctionalUniqueness(_ClosedSpaceExclusion):
    predicate_name = "c3_functional_uniqueness"
    schema_id = "S-C3-01"
    version = "0.1-placeholder"
    formal_statement = (
        "PLACEHOLDER. Checks mutual exclusion over the closed answer space only; "
        "does NOT represent the universal quantifier or its variable binding."
    )
