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


# ---------------------------------------------------------------------------
# D0AUDIT-A — analytic audit cases (ADR-0023 D3)
# ---------------------------------------------------------------------------
#
# The §4.12 `D0AUDIT` criterion required three HAND-CHECKED instances per
# predicate, with `expected_verdict` supplied by a named human. That criterion
# is superseded by `D0AUDIT-A`, which replaces the human verdict with one that
# follows DEDUCTIVELY from the predicate's own declared `formal_statement`
# against a constructed fixture.
#
# WHAT THIS IS: a software-correctness check. It establishes that a predicate
# implements the formalisation it declares.
#
# WHAT IT IS NOT, and both matter:
#   * NOT detector validity. It cannot establish that the formalisation
#     captures the constraint the benchmark intends. A predicate whose
#     `formal_statement` is wrong passes its own analytic audit perfectly.
#   * NOT human validation. No person judged any instance. The original
#     criterion is retained above, unchanged and unused, for traceability.
#
# The non-circularity guarantee is structural: `expected_verdict` is a LITERAL
# written by the case author, never a value obtained by running the predicate.
# `derived_from` stores the `formal_statement` the case was derived against, so
# if that statement changes the case is automatically invalidated rather than
# silently continuing to pass against new semantics.


@dataclass(slots=True)
class AnalyticAuditCase:
    """One case whose expected verdict follows from the predicate's own text.

    ``derivation`` is the argument from ``derived_from`` to ``expected_verdict``.
    It is required and is not decoration: a case nobody can justify from the
    formal statement is not an analytic case, it is a guess with a literal.
    """

    case_id: str
    constraint: Constraint
    responses: Sequence[CanonicalResponse]
    expected_verdict: Verdict
    derivation: str
    derived_from: str

    def __post_init__(self) -> None:
        if not isinstance(self.expected_verdict, Verdict):
            raise TypeError(
                f"analytic case {self.case_id}: expected_verdict must be a Verdict"
            )
        if not self.derivation.strip():
            raise ValueError(
                f"analytic case {self.case_id}: `derivation` is required — a case "
                "with no argument from the formal statement is not analytic"
            )
        if not self.derived_from.strip():
            raise ValueError(
                f"analytic case {self.case_id}: `derived_from` must hold the "
                "predicate's formal_statement, so a change to it invalidates "
                "this case instead of silently passing"
            )


def run_analytic_audit(
    predicate: D0Predicate,
    cases: Sequence[AnalyticAuditCase],
    kb: KnowledgeBase,
) -> AuditResult:
    """Run analytic cases against one predicate.

    Refuses a case derived from a different `formal_statement` than the
    predicate currently declares — that is the drift guard, and it fires as an
    error rather than a failed case because a stale derivation is not evidence
    either way.
    """
    result = AuditResult(
        predicate_name=predicate.predicate_name,
        schema_id=predicate.schema_id,
        version=predicate.version,
        source_sha256=predicate.source_hash(),
    )
    for case in cases:
        if case.derived_from.strip() != predicate.formal_statement.strip():
            raise ValueError(
                f"analytic case {case.case_id} was derived from a formal_statement "
                f"that {predicate.predicate_name} no longer declares. Re-derive the "
                "case against the current statement; a stale derivation is not "
                "evidence.\n"
                f"  case:      {case.derived_from.strip()[:120]!r}\n"
                f"  predicate: {predicate.formal_statement.strip()[:120]!r}"
            )
        if len(case.responses) != 2:
            raise ValueError(
                f"analytic case {case.case_id}: a pairwise case needs exactly 2 "
                f"responses, got {len(case.responses)}"
            )
        a, b = case.responses
        actual = predicate.check_pair(case.constraint, a, b, kb)
        result.outcomes.append(CaseOutcome(
            case_id=case.case_id,
            expected=case.expected_verdict,
            actual=actual.verdict,
            passed=actual.verdict is case.expected_verdict,
            reason=actual.reason,
        ))
    return result


def mechanism_coverage(registry: object) -> dict[str, object]:
    """How many DISTINCT pairwise mechanisms the registered predicates have.

    Auditing 28 names is not auditing 28 mechanisms. All 24 `s_c*_0*`
    predicates — the only ones any test constraint selects — delegate their
    pairwise verdict to `_SchemaExclusion.check_pair` or
    `_SchemaAnchor.check_pair`, both of which route through
    `C1MutualExclusion.check_pair`. Grouping by the bound implementation makes
    that visible instead of leaving a reader to count names.

    This is the honest denominator for D0AUDIT-A's coverage claim.
    """
    names = sorted(registry.names())            # type: ignore[attr-defined]
    by_impl: dict[str, list[str]] = {}
    placeholders: list[str] = []
    for name in names:
        pred = registry.get(name)               # type: ignore[attr-defined]
        qual = type(pred).check_pair.__qualname__
        by_impl.setdefault(qual, []).append(name)
        if "placeholder" in pred.version.lower() or pred.formal_statement.strip().upper().startswith("PLACEHOLDER"):
            placeholders.append(name)
    return {
        "n_registered_predicates": len(names),
        "n_distinct_pairwise_implementations": len(by_impl),
        "predicates_by_implementation": {k: sorted(v) for k, v in sorted(by_impl.items())},
        "placeholder_predicates": sorted(placeholders),
        "coverage_caveat": (
            f"{len(names)} registered predicate(s) share "
            f"{len(by_impl)} distinct pairwise implementation(s). An audit that "
            "passes for every NAME audits those implementations, not that many "
            "independent formalisations."
        ),
    }
