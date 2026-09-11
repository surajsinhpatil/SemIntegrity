"""D0 — symbolic constraint reference (proposal §4.8.2).

D0 performs **deterministic conditional verification, not oracular judgement**.
Its verdict is deterministic *conditional on* the correctness of the
formalisation, the canonicalisation and the knowledge base. A faulty predicate
is confidently wrong across every instance of its schema, so D0's errors are
systematic and schema-correlated rather than random — which is exactly why the
three-instance audit and the freeze policy exist.

Two levels of verdict
---------------------
§4.8.2's reference implementation checks each response against the knowledge
base and returns a **set-level** verdict. The primary metric PSCR, however,
counts **contradictory probe pairs** (§4.10). A predicate therefore implements:

``check_pair``  whether two canonicalised responses are jointly satisfiable —
                this is what feeds PSCR;
``check_set``   whether the whole response set satisfies the constraint — the
                §4.8.2 reading, reported as the integrity view.

The default ``check_set`` is "SATISFIED unless some pair contradicts", so a
predicate that only implements ``check_pair`` still yields both. **How these two
relate in the write-up is Q22 and awaits researcher approval**; both are computed
and stored so the decision does not need to be taken before the data exists.
"""

from __future__ import annotations

import datetime as dt
import inspect
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING, Any, Protocol

from ...schemas.enums import ResponseLabel, Verdict
from ...utils.hashing import sha256_text

if TYPE_CHECKING:  # pragma: no cover
    from ...schemas.constraint import Constraint
    from ...schemas.response import CanonicalResponse


class KnowledgeBase(Protocol):
    """What a predicate may ask of the knowledge base.

    Deliberately narrow: a predicate that needs something outside this protocol
    is doing work that belongs in constraint authoring, where it can be checked
    by a human, rather than in a predicate, where it cannot.
    """

    def entity_label(self, qid: str) -> str: ...
    def sitelinks(self, qid: str) -> int: ...
    def claim_values(self, qid: str, property_id: str) -> list[str]: ...
    def claim_interval(self, qid: str, property_id: str, value_qid: str) -> tuple[dt.date | None, dt.date | None]: ...


@dataclass(frozen=True, slots=True)
class D0Result:
    """One D0 verdict, with enough detail to audit it after the fact."""

    verdict: Verdict
    predicate: str
    schema_id: str
    reason: str = ""
    conflicting_pairs: tuple[tuple[str, str], ...] = ()
    skipped_probe_ids: tuple[str, ...] = ()
    kb_facts_used: tuple[str, ...] = ()

    @property
    def is_covered(self) -> bool:
        """Whether D0 reached a decision at all (feeds the D0 coverage metric)."""
        return self.verdict is not Verdict.NOT_APPLICABLE


class D0Predicate(ABC):
    """Base class for a machine-checkable constraint predicate.

    Subclasses declare the ``schema_id`` they formalise and implement
    ``check_pair``. They are registered by the ``predicate_name`` that
    constraints reference through their ``formal_predicate`` field.
    """

    #: The registry key; matches `Constraint.formal_predicate`.
    predicate_name: str = ""
    #: The schema this predicate formalises; matches `Constraint.schema_id`.
    schema_id: str = ""
    #: Bumped whenever the logic changes. Recorded on every verdict.
    version: str = "1.0"
    #: Human-readable statement of what the predicate asserts, for the audit.
    formal_statement: str = ""

    def __init_subclass__(cls, **kw: Any) -> None:
        super().__init_subclass__(**kw)
        if inspect.isabstract(cls):
            return
        for required in ("predicate_name", "schema_id", "formal_statement"):
            if not getattr(cls, required, ""):
                raise TypeError(f"{cls.__name__} must declare a non-empty {required!r}")

    # -- required -----------------------------------------------------------
    @abstractmethod
    def check_pair(
        self,
        constraint: Constraint,
        a: CanonicalResponse,
        b: CanonicalResponse,
        kb: KnowledgeBase,
    ) -> D0Result:
        """Are these two canonicalised responses jointly satisfiable?

        Only called when both responses are evaluable; non-answer labels are
        filtered upstream by :meth:`check_set` and by the detector runner, so a
        predicate never has to handle ABSTAIN.
        """

    # -- provided -----------------------------------------------------------
    def check_set(
        self,
        constraint: Constraint,
        responses: Sequence[CanonicalResponse],
        kb: KnowledgeBase,
    ) -> D0Result:
        """Set-level verdict over all probes of one constraint (§4.8.2).

        Mirrors the proposal's reference implementation: skip ABSTAIN and
        INVALID, then return VIOLATION if anything conflicts.
        """
        usable = [r for r in responses if r.label is ResponseLabel.ANSWER]
        skipped = tuple(r.probe_id for r in responses if r.label is not ResponseLabel.ANSWER)

        if len(usable) < 2:
            return D0Result(
                Verdict.NOT_APPLICABLE,
                self.predicate_name,
                self.schema_id,
                reason=f"only {len(usable)} evaluable response(s); no pair to check",
                skipped_probe_ids=skipped,
            )

        conflicts: list[tuple[str, str]] = []
        reasons: list[str] = []
        for a, b in combinations(usable, 2):
            result = self.check_pair(constraint, a, b, kb)
            if result.verdict is Verdict.VIOLATION:
                conflicts.append((a.probe_id, b.probe_id))
                if result.reason:
                    reasons.append(result.reason)

        if conflicts:
            return D0Result(
                Verdict.VIOLATION,
                self.predicate_name,
                self.schema_id,
                reason=reasons[0] if reasons else "at least one pair is jointly unsatisfiable",
                conflicting_pairs=tuple(conflicts),
                skipped_probe_ids=skipped,
            )
        return D0Result(
            Verdict.SATISFIED,
            self.predicate_name,
            self.schema_id,
            reason="all evaluable pairs are jointly satisfiable",
            skipped_probe_ids=skipped,
        )

    # -- identity -----------------------------------------------------------
    def source_hash(self) -> str:
        """Hash of this predicate's source, for the freeze manifest."""
        try:
            src = inspect.getsource(type(self))
        except OSError:  # pragma: no cover - interactive definitions
            src = repr(type(self))
        return sha256_text(src)

    def describe(self) -> dict[str, str]:
        return {
            "predicate_name": self.predicate_name,
            "schema_id": self.schema_id,
            "version": self.version,
            "formal_statement": self.formal_statement,
            "source_sha256": self.source_hash(),
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} {self.predicate_name} v{self.version}>"
