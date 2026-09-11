"""Three-instance schema audit harness (proposal §4.8.2, step 10).

    "Author the predicate; verify it manually against three hand-checked
    instances of its schema."

The harness makes that verification an artefact rather than a memory. For each
predicate the researcher supplies at least three hand-checked cases — inputs
plus the verdict a human determined — and the harness records pass/fail per
case, writing the result to JSONL.

The audit is a **gate**: `configs/detectors/d0_symbolic.yaml` requires every
predicate to pass before the freeze, and it is a Phase 3 go/no-go criterion.

**The expected verdicts are human judgements and are never generated here.** An
audit case with no human-supplied verdict is rejected, not defaulted.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ...schemas.enums import Verdict
from ...utils.io import append_jsonl
from ...utils.logging import get_logger
from .base import D0Predicate, KnowledgeBase

if TYPE_CHECKING:  # pragma: no cover
    from ...schemas.constraint import Constraint
    from ...schemas.response import CanonicalResponse

log = get_logger(__name__)

MIN_AUDIT_INSTANCES = 3


@dataclass(slots=True)
class AuditCase:
    """One hand-checked instance of a schema.

    ``expected_verdict`` is a HUMAN judgement supplied by the researcher. There
    is no default and no inference from the predicate itself, which would make
    the audit circular.
    """

    case_id: str
    constraint: Constraint
    responses: Sequence[CanonicalResponse]
    expected_verdict: Verdict
    checked_by: str
    checked_at: dt.date
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.checked_by.strip():
            raise ValueError(
                f"audit case {self.case_id}: checked_by is required — an audit case "
                "without a named human checker is not an audit"
            )
        if not isinstance(self.expected_verdict, Verdict):
            raise TypeError(f"audit case {self.case_id}: expected_verdict must be a Verdict")


@dataclass(slots=True)
class CaseOutcome:
    case_id: str
    expected: Verdict
    actual: Verdict
    passed: bool
    reason: str = ""


@dataclass(slots=True)
class AuditResult:
    predicate_name: str
    schema_id: str
    version: str
    source_sha256: str
    outcomes: list[CaseOutcome] = field(default_factory=list)
    audited_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    @property
    def passed(self) -> bool:
        return (
            len(self.outcomes) >= MIN_AUDIT_INSTANCES
            and all(o.passed for o in self.outcomes)
        )

    @property
    def summary(self) -> str:
        n_pass = sum(o.passed for o in self.outcomes)
        verdict = "PASS" if self.passed else "FAIL"
        note = "" if len(self.outcomes) >= MIN_AUDIT_INSTANCES else (
            f" — only {len(self.outcomes)} case(s); §4.8.2 requires {MIN_AUDIT_INSTANCES}"
        )
        return f"[{verdict}] {self.predicate_name} ({self.schema_id}): {n_pass}/{len(self.outcomes)} cases{note}"

    def to_record(self) -> dict:
        return {
            "predicate_name": self.predicate_name,
            "schema_id": self.schema_id,
            "version": self.version,
            "source_sha256": self.source_sha256,
            "audited_at": self.audited_at.isoformat(),
            "passed": self.passed,
            "n_cases": len(self.outcomes),
            "cases": [
                {
                    "case_id": o.case_id,
                    "expected": o.expected.value,
                    "actual": o.actual.value,
                    "passed": o.passed,
                    "reason": o.reason,
                }
                for o in self.outcomes
            ],
        }


class SchemaAuditFailure(AssertionError):
    """Raised when a predicate fails its three-instance audit."""


def audit_predicate(
    predicate: D0Predicate, cases: Sequence[AuditCase], kb: KnowledgeBase
) -> AuditResult:
    """Run one predicate against its hand-checked cases."""
    result = AuditResult(
        predicate_name=predicate.predicate_name,
        schema_id=predicate.schema_id,
        version=predicate.version,
        source_sha256=predicate.source_hash(),
    )
    for case in cases:
        if case.constraint.formal_predicate != predicate.predicate_name:
            raise ValueError(
                f"audit case {case.case_id} references predicate "
                f"{case.constraint.formal_predicate!r}, not {predicate.predicate_name!r}"
            )
        actual = predicate.check_set(case.constraint, case.responses, kb)
        result.outcomes.append(
            CaseOutcome(
                case_id=case.case_id,
                expected=case.expected_verdict,
                actual=actual.verdict,
                passed=actual.verdict is case.expected_verdict,
                reason=actual.reason,
            )
        )
    return result


def audit_all(
    predicates: Sequence[D0Predicate],
    cases_by_predicate: dict[str, Sequence[AuditCase]],
    kb: KnowledgeBase,
    *,
    out_path: str | Path | None = None,
    strict: bool = True,
) -> list[AuditResult]:
    """Audit every predicate and optionally record the results.

    With ``strict`` (the default), a predicate with no cases, too few cases, or
    any failing case raises — the gate is meant to block, not to warn.
    """
    results: list[AuditResult] = []
    failures: list[str] = []

    for predicate in predicates:
        cases = cases_by_predicate.get(predicate.predicate_name, [])
        if not cases:
            failures.append(f"{predicate.predicate_name}: no audit cases supplied")
            continue
        result = audit_predicate(predicate, cases, kb)
        results.append(result)
        log.info("audited predicate", extra={"extra_fields": {"summary": result.summary}})
        if not result.passed:
            failures.append(result.summary)

    if out_path is not None:
        append_jsonl(out_path, [r.to_record() for r in results])

    if strict and failures:
        raise SchemaAuditFailure(
            "D0 three-instance schema audit failed (§4.8.2); predicates must not be "
            "frozen or used until every case passes:\n  - " + "\n  - ".join(failures)
        )
    return results
