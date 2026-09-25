"""Benchmark design validator (proposal §4.3, ADR-0002, ADR-0007).

Checks the whole constraint set against the design lattice and reports **every**
violation at once, because during authoring you want the full list, not the
first failure.

Rules enforced
--------------
=========================  ===========================================================
``unique_ids``             constraint/family/schema ids are well-formed and unique
``total_count``            exactly 120 test constraints
``class_balance``          exactly 30 per class
``domain_class_balance``   exactly 6 per (domain, class)
``family_completeness``    every family has exactly one constraint per class
``family_domain_fixed``    all constraints in a family share one domain
``schema_class_fixed``     a schema belongs to exactly one class
``schema_balance``         every schema has exactly 5 instances
``schema_domain_crossing`` schema x domain coverage (relaxable — see Q12)
``sitelink_matching``      entity familiarity distribution matched across classes
``dev_test_disjoint``      no entity set / gold proposition shared across the split
``predicate_registered``   every ``formal_predicate`` resolves to a D0 predicate
=========================  ===========================================================

Every rule is reported with the offending ids, so an authoring session can be
driven directly from the report.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ..schemas.constraint import Constraint
from ..schemas.enums import ConstraintClass, Domain, Split
from ..utils.config import load_config


@dataclass(slots=True)
class RuleResult:
    rule: str
    passed: bool
    message: str
    offenders: list[str] = field(default_factory=list)
    severity: str = "error"  # error | warning | info

    def __str__(self) -> str:
        mark = "PASS" if self.passed else ("WARN" if self.severity == "warning" else "FAIL")
        line = f"[{mark}] {self.rule}: {self.message}"
        if self.offenders:
            shown = ", ".join(self.offenders[:10])
            more = f" (+{len(self.offenders) - 10} more)" if len(self.offenders) > 10 else ""
            line += f"\n         offenders: {shown}{more}"
        return line


@dataclass(slots=True)
class ValidationReport:
    results: list[RuleResult] = field(default_factory=list)

    @property
    def errors(self) -> list[RuleResult]:
        return [r for r in self.results if not r.passed and r.severity == "error"]

    @property
    def warnings(self) -> list[RuleResult]:
        return [r for r in self.results if not r.passed and r.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise DesignViolation(
                f"{len(self.errors)} design rule(s) violated:\n"
                + "\n".join(str(r) for r in self.errors)
            )

    def __str__(self) -> str:
        header = (
            f"{sum(r.passed for r in self.results)}/{len(self.results)} rules passed"
            f" — {len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )
        return header + "\n" + "\n".join(str(r) for r in self.results)


class DesignViolation(ValueError):
    """Raised when the benchmark violates its own design lattice."""


class BenchmarkDesignValidator:
    """Validates a constraint set against ``configs/benchmark/design.yaml``."""

    def __init__(self, design_config: dict | None = None) -> None:
        self.cfg = design_config or load_config("configs/benchmark/design.yaml").data
        lattice = self.cfg["lattice"]
        self.n_total = 120
        self.n_per_class = 30
        self.n_per_domain_class = lattice["domain"]["constraints_per_domain_per_class"]
        self.n_families = lattice["family"]["count"]
        self.n_schemas_per_class = lattice["schema"]["count_per_class"]
        self.n_instances_per_schema = lattice["schema"]["instances_per_schema"]
        self.sitelink_alpha = 0.10

    # -- public API ---------------------------------------------------------
    def validate(
        self,
        constraints: Sequence[Constraint],
        *,
        split: Split = Split.TEST,
        known_predicates: Iterable[str] | None = None,
        strict_schema_crossing: bool = False,
    ) -> ValidationReport:
        """Validate the constraint set for one split."""
        subset = [c for c in constraints if c.split is split]
        report = ValidationReport()
        report.results.append(self._unique_ids(subset))

        if split is Split.TEST:
            report.results.append(self._total_count(subset))
            report.results.append(self._class_balance(subset))
            report.results.append(self._domain_class_balance(subset))
            report.results.append(self._family_completeness(subset))
            report.results.append(self._schema_balance(subset))
            report.results.append(
                self._schema_domain_crossing(subset, strict=strict_schema_crossing)
            )

        report.results.append(self._family_domain_fixed(subset))
        report.results.append(self._schema_class_fixed(subset))
        report.results.append(self._sitelink_matching(subset))
        if known_predicates is not None:
            report.results.append(self._predicates_registered(subset, set(known_predicates)))
        return report

    def validate_split_disjointness(self, constraints: Sequence[Constraint]) -> RuleResult:
        """ADR-0007: dev must share no entity set or gold proposition with test."""
        dev = [c for c in constraints if c.split in (Split.DEV, Split.PILOT)]
        test = [c for c in constraints if c.split is Split.TEST]
        test_entity_sets = {frozenset(c.entity_qids): c.constraint_id for c in test}
        test_props = {c.gold_proposition.strip().lower(): c.constraint_id for c in test}

        offenders: list[str] = []
        for c in dev:
            if (hit := test_entity_sets.get(frozenset(c.entity_qids))) is not None:
                offenders.append(f"{c.constraint_id} shares its entity set with {hit}")
            if (hit := test_props.get(c.gold_proposition.strip().lower())) is not None:
                offenders.append(f"{c.constraint_id} shares its gold proposition with {hit}")
        return RuleResult(
            "dev_test_disjoint",
            not offenders,
            "development and test sets are disjoint"
            if not offenders
            else f"{len(offenders)} dev/test overlap(s); tuning would leak into the test set",
            offenders,
        )

    # -- rules --------------------------------------------------------------
    def _unique_ids(self, cs: Sequence[Constraint]) -> RuleResult:
        dupes = [cid for cid, n in Counter(c.constraint_id for c in cs).items() if n > 1]
        return RuleResult(
            "unique_ids",
            not dupes,
            "all constraint ids unique" if not dupes else f"{len(dupes)} duplicate id(s)",
            dupes,
        )

    def _total_count(self, cs: Sequence[Constraint]) -> RuleResult:
        n = len(cs)
        return RuleResult(
            "total_count",
            n == self.n_total,
            f"{n} constraints (expected {self.n_total})",
        )

    def _class_balance(self, cs: Sequence[Constraint]) -> RuleResult:
        counts = Counter(c.constraint_class for c in cs)
        bad = {k.value: v for k, v in counts.items() if v != self.n_per_class}
        missing = [k.value for k in ConstraintClass if k not in counts]
        return RuleResult(
            "class_balance",
            not bad and not missing,
            f"expected {self.n_per_class} per class; "
            + ("balanced" if not bad and not missing else f"off: {bad}, missing: {missing}"),
        )

    def _domain_class_balance(self, cs: Sequence[Constraint]) -> RuleResult:
        counts = Counter((c.domain, c.constraint_class) for c in cs)
        offenders = []
        for dom in Domain:
            for cls in ConstraintClass:
                n = counts.get((dom, cls), 0)
                if n != self.n_per_domain_class:
                    offenders.append(f"({dom.value}, {cls.value})={n}")
        return RuleResult(
            "domain_class_balance",
            not offenders,
            f"expected {self.n_per_domain_class} per (domain, class) cell"
            + ("; balanced" if not offenders else f"; {len(offenders)} cell(s) off"),
            offenders,
        )

    def _family_completeness(self, cs: Sequence[Constraint]) -> RuleResult:
        by_family: dict[str, list[ConstraintClass]] = defaultdict(list)
        for c in cs:
            by_family[c.family_id].append(c.constraint_class)
        offenders = []
        expected = ["C1", "C2", "C3", "C4"]
        for fam, classes in sorted(by_family.items()):
            seen = sorted({c.value for c in classes})
            if seen != expected or len(classes) != 4:
                offenders.append(f"{fam}={seen}")
        n_fam_ok = len(by_family) == self.n_families
        return RuleResult(
            "family_completeness",
            not offenders and n_fam_ok,
            f"{len(by_family)} families (expected {self.n_families}); "
            + ("each spans all 4 classes exactly once" if not offenders else f"{len(offenders)} incomplete"),
            offenders,
        )

    def _family_domain_fixed(self, cs: Sequence[Constraint]) -> RuleResult:
        by_family: dict[str, set[Domain]] = defaultdict(set)
        for c in cs:
            by_family[c.family_id].add(c.domain)
        offenders = [f"{fam}={sorted(d.value for d in doms)}" for fam, doms in by_family.items() if len(doms) > 1]
        return RuleResult(
            "family_domain_fixed",
            not offenders,
            "every family sits in one domain" if not offenders else f"{len(offenders)} family/families span domains",
            offenders,
        )

    def _schema_class_fixed(self, cs: Sequence[Constraint]) -> RuleResult:
        by_schema: dict[str, set[ConstraintClass]] = defaultdict(set)
        for c in cs:
            by_schema[c.schema_id].add(c.constraint_class)
        offenders = [f"{s}={sorted(k.value for k in v)}" for s, v in by_schema.items() if len(v) > 1]
        return RuleResult(
            "schema_class_fixed",
            not offenders,
            "every schema belongs to one class" if not offenders else f"{len(offenders)} schema(s) span classes",
            offenders,
        )

    def _schema_balance(self, cs: Sequence[Constraint]) -> RuleResult:
        counts = Counter(c.schema_id for c in cs)
        offenders = [
            f"{s}={n}" for s, n in sorted(counts.items()) if n != self.n_instances_per_schema
        ]
        schemas_by_class: dict[ConstraintClass, set[str]] = defaultdict(set)
        for c in cs:
            schemas_by_class[c.constraint_class].add(c.schema_id)
        wrong_schema_count = [
            f"{k.value}={len(v)}"
            for k, v in sorted(schemas_by_class.items(), key=lambda kv: kv[0].value)
            if len(v) != self.n_schemas_per_class
        ]
        return RuleResult(
            "schema_balance",
            not offenders and not wrong_schema_count,
            f"expected {self.n_schemas_per_class} schemas x {self.n_instances_per_schema} instances per class"
            + ("; balanced" if not offenders and not wrong_schema_count else "; imbalanced"),
            offenders + wrong_schema_count,
        )

    def _schema_domain_crossing(self, cs: Sequence[Constraint], *, strict: bool) -> RuleResult:
        """Q12: full 6x5 crossing is attempted; a balanced incomplete design is allowed."""
        pairs = Counter((c.schema_id, c.domain) for c in cs)
        offenders = [
            f"{s}x{d.value}={n}"
            for (s, d), n in sorted(pairs.items(), key=lambda kv: str(kv[0]))
            if n > 1
        ]
        by_schema: dict[str, set[Domain]] = defaultdict(set)
        for c in cs:
            by_schema[c.schema_id].add(c.domain)
        not_fully_crossed = [s for s, doms in sorted(by_schema.items()) if len(doms) != len(Domain)]
        if offenders:
            return RuleResult(
                "schema_domain_crossing", False,
                "a (schema, domain) cell holds more than one constraint", offenders,
            )
        if not_fully_crossed:
            return RuleResult(
                "schema_domain_crossing",
                not strict,
                f"{len(not_fully_crossed)} schema(s) are not instantiated in every domain "
                "(permitted balanced-incomplete design; see Q12)",
                not_fully_crossed,
                severity="error" if strict else "warning",
            )
        return RuleResult("schema_domain_crossing", True, "schema x domain fully crossed")

    def _sitelink_matching(self, cs: Sequence[Constraint]) -> RuleResult:
        """§4.3: entity familiarity must not be confounded with class.

        Kruskal-Wallis over per-constraint median sitelinks. We want to FAIL TO
        REJECT equality, so a small p-value is the bad outcome — the inverse of
        the usual reading, and stated that way in the message.
        """
        groups = defaultdict(list)
        for c in cs:
            groups[c.constraint_class].append(c.median_sitelinks)
        present = [g for g in groups.values() if len(g) >= 2]
        if len(present) < 2:
            return RuleResult(
                "sitelink_matching", True,
                "not enough constraints to test familiarity matching yet", severity="info",
            )
        try:
            from scipy.stats import kruskal
        except ImportError:
            # FAIL CLOSED. A validity check that cannot run has NOT passed.
            # Reporting True here would let a benchmark whose classes are
            # confounded with entity familiarity sail through unnoticed — and
            # §4.3 calls that "the most damaging alternative explanation for any
            # observed class effect". Silence is not evidence of absence.
            return RuleResult(
                "sitelink_matching",
                False,
                "CHECK COULD NOT RUN: scipy is not installed, so entity-familiarity "
                "matching was never tested. Install it with: pip install -e '.[analysis]'",
                severity="error",
            )

        medians_only = {k.value: round(sorted(v)[len(v) // 2], 1) for k, v in sorted(groups.items(), key=lambda kv: kv[0].value)}
        try:
            stat, p = kruskal(*present)
        except ValueError as exc:
            # scipy raises when every value is tied. Perfectly identical
            # familiarity across classes is the IDEAL outcome of matching, not a
            # failure, so it passes with the degeneracy stated explicitly.
            if "identical" in str(exc):
                return RuleResult(
                    "sitelink_matching", True,
                    f"all per-constraint sitelink medians are identical across classes "
                    f"(perfectly matched; Kruskal-Wallis undefined); class medians {medians_only}",
                    severity="info",
                )
            raise
        passed = bool(p > self.sitelink_alpha)
        medians = {k.value: round(sorted(v)[len(v) // 2], 1) for k, v in sorted(groups.items(), key=lambda kv: kv[0].value)}
        return RuleResult(
            "sitelink_matching",
            passed,
            f"Kruskal-Wallis H={stat:.2f}, p={p:.3f} (need p > {self.sitelink_alpha} "
            f"= fail to reject equality); class medians {medians}",
            severity="error" if not passed else "info",
        )

    def _predicates_registered(self, cs: Sequence[Constraint], known: set[str]) -> RuleResult:
        offenders = sorted({c.formal_predicate for c in cs} - known)
        return RuleResult(
            "predicate_registered",
            not offenders,
            "every formal_predicate resolves in the D0 registry"
            if not offenders
            else f"{len(offenders)} unregistered predicate(s)",
            offenders,
        )
