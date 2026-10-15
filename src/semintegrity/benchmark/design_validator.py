"""Benchmark design validator (proposal §4.3, ADR-0002, ADR-0007).

Checks the whole constraint set against the design lattice and reports **every**
violation at once, because during authoring you want the full list, not the
first failure.

Rules enforced
--------------
=========================  ===========================================================
``unique_ids``             ``constraint_id`` is unique WITHIN the validated split
``cross_split_ids``        no ``constraint_id`` is reused ACROSS splits
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
``corroboration``          historical and temporal facts carry a VALID second source
``corroboration_freeze``   each second source's frozen artefact checks out
``comparison_universe``    extremal schemas carry a frozen comparison universe
``answer_type_allocation`` answer type follows ADR-0017's (axis, class) rule
=========================  ===========================================================

Every rule is reported with the offending ids, so an authoring session can be
driven directly from the report.

Two notes on what is *not* checked here, because the docstring used to promise
more than the code delivered:

* **Id grammar is enforced by the schema, not by a rule.** ``Constraint`` pins
  ``constraint_id``/``family_id``/``schema_id`` to the patterns in
  :mod:`semintegrity.utils.ids`, and its cross-field validator checks that the
  class and domain encoded in an id agree with the fields. A malformed id cannot
  reach a validator, so re-checking it here would be a rule that can never fire.
* **``family_id`` and ``schema_id`` are shared by design** -- a family holds four
  constraints and a schema five -- so "unique" is meaningful only for
  ``constraint_id``.

:meth:`BenchmarkDesignValidator.validate` deliberately validates ONE split at a
time, which means it cannot see an id reused across splits.
:meth:`validate_global_id_uniqueness` covers that, and must be called
separately; the id grammar carries no split field, so nothing else would catch
it.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from ..kb.corroboration import CorroborationPolicy, CorroborationStore, default_store
from ..schemas.constraint import EXTREMAL_SCHEMA_INDICES, Constraint
from ..schemas.enums import (
    AnswerType,
    ConstraintClass,
    Domain,
    Split,
    VerificationStatus,
)
from ..utils.config import load_config
from ..utils.ids import SCHEMA_RE
from ..utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..kb.witness import WitnessClassifier, WitnessVerdict
    from ..schemas.constraint import CorroboratingSource

log = get_logger(__name__)

#: Distinguishes "no classifier was requested" from "a classifier was requested
#: and there is none", which decide differently (ADR-0019).
_UNSET: object = object()


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


def corroboration_reason(constraint: Constraint, design_cfg: dict | None = None) -> str | None:
    """Why this constraint needs a second authoritative source, or None.

    §4.3: "all historical and temporal facts are corroborated against a second
    authoritative source". The policy is read from
    ``configs/benchmark/design.yaml``; the AXIS is a trigger as well as the
    answer type, so the 2026-10-07 answer-type amendment could not narrow it.

    Public so the builder and the validator cannot disagree about who needs one.
    """
    cfg = design_cfg or load_config("configs/benchmark/design.yaml").data
    gt = cfg.get("ground_truth", {})
    if not gt.get("second_source_required", False):
        return None
    required_for = set(gt.get("corroboration_required_for", ()))
    if "history" in required_for and constraint.domain is Domain.HISTORY:
        return "history domain"
    if "temporal_facts" in required_for:
        if constraint.constraint_class is ConstraintClass.C4:
            return "C4 temporal constraint"
        if str(constraint.answer_type) == AnswerType.DATE.value:
            return "date answer"
        if constraint.temporal_validity is not None:
            return "records a validity interval"
        m = SCHEMA_RE.match(constraint.schema_id)
        date_axes = cfg.get("lattice", {}).get("answer_type", {}).get("date_axes", [])
        if m and int(m.group(2)) in date_axes:
            return f"temporal axis {int(m.group(2))}"
    return None


def answer_type_for_cell(
    schema_id: str, cls: ConstraintClass, design_cfg: dict | None = None
) -> str | None:
    """ADR-0017 as amended 2026-10-07: answer type is a function of (axis, class).

    Read from ``configs/benchmark/design.yaml`` so there is one executable
    statement of the rule. Public because the test fixtures must model the
    approved design rather than restate it.
    """
    cfg = design_cfg or load_config("configs/benchmark/design.yaml").data
    rule = cfg.get("lattice", {}).get("answer_type")
    if not rule or "rule" not in rule:
        return None
    m = SCHEMA_RE.match(schema_id)
    if not m:
        return None
    per_class = rule["rule"].get(cls.value)
    if per_class is None:
        return None
    if per_class == "per_axis":
        return str(rule["per_axis"].get(int(m.group(2)), ""))
    return str(per_class)


class BenchmarkDesignValidator:
    """Validates a constraint set against ``configs/benchmark/design.yaml``."""

    def __init__(
        self, design_config: dict | None = None, *, witness_classifier: object = _UNSET
    ) -> None:
        self.cfg = design_config or load_config("configs/benchmark/design.yaml").data
        # ADR-0019 witness classification. Resolved lazily from the frozen cache
        # so that a records-only context costs nothing; injectable for tests.
        self._witness_cache = witness_classifier
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
        report.results.append(self._corroboration(subset))
        report.results.append(self._comparison_universe(subset))
        report.results.append(self._answer_type_allocation(subset))
        report.results.append(self._claims_renderable(subset))
        if known_predicates is not None:
            report.results.append(self._predicates_registered(subset, set(known_predicates)))
        return report

    def _witness(
        self, constraint: Constraint, source: CorroboratingSource
    ) -> WitnessVerdict | None:
        """ADR-0019 witness classification, or None when it cannot be attempted.

        Returns ``None`` only when no knowledge-base cache is available at all —
        a unit-test or a records-only context — in which case the admissibility
        decision stands alone and this rule adds nothing. It never *passes* a
        source it could not classify: an available classifier that cannot
        establish independence returns ``undetermined``, which does not qualify.
        """
        classifier = self._witness_classifier()
        if classifier is None:
            return None
        return classifier.classify_for_constraint(constraint, source)

    def _witness_classifier(self) -> WitnessClassifier | None:
        if self._witness_cache is _UNSET:
            try:
                from ..kb.cache import CacheMode, KBCache
                from ..kb.witness import WitnessClassifier
                from ..utils.paths import data_path

                root = data_path("wikidata_cache")
                self._witness_cache = (
                    WitnessClassifier(KBCache(root, CacheMode.FROZEN))
                    if Path(root).is_dir()
                    else None
                )
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("witness classifier unavailable: %s", exc)
                self._witness_cache = None
        cached = self._witness_cache
        return None if cached is None else cast("WitnessClassifier", cached)

    def _corroboration(self, cs: Sequence[Constraint]) -> RuleResult:
        """§4.3: historical and temporal facts need a second authoritative source.

        Read from ``configs/benchmark/design.yaml`` rather than restated here::

            ground_truth:
              corroboration_required_for: [history, temporal_facts]
              second_source_required: true

        §4.3's words are "all historical and temporal facts are corroborated
        against a second authoritative source". ``history`` is the domain;
        ``temporal_facts`` is operationalised as a constraint that is C4, carries
        a ``date`` answer, or records a ``temporal_validity`` interval — the three
        ways a constraint in this schema can BE a temporal fact. That mapping is
        engineering; the requirement itself is unchanged and is not widened.

        **Severity follows the verification ladder, not the split.** A missing
        second source is an *error* once a constraint claims EVIDENCE_VERIFIED or
        above, and a *warning* while it is still DRAFT. Authoring a draft without
        corroboration yet is normal; freezing one is not. Scoping it by status
        rather than by split means no split is quietly exempt.
        """
        gt = self.cfg.get("ground_truth", {})
        if not gt.get("second_source_required", False):
            return RuleResult(
                "corroboration", True,
                "design.yaml does not require a second source", severity="info",
            )
        def needs(c: Constraint) -> str | None:
            return corroboration_reason(c, self.cfg)

        promoted_statuses = {
            str(VerificationStatus.EVIDENCE_VERIFIED),
            str(VerificationStatus.HUMAN_VALIDATED),
            str(VerificationStatus.FROZEN),
        }
        policy = CorroborationPolicy()

        errors: list[str] = []
        drafts: list[str] = []
        for c in cs:
            reason = needs(c)
            if reason is None:
                continue
            status = str(c.verification_status)

            # A well-formed source is not automatically a VALID one. Whether its
            # provider is an independent authority is policy, and the policy is
            # deliberately unconfigured, so nothing counts yet.
            rejections = [
                f"{src.provider}: {policy.rejection_reason(src)}"
                for src in c.corroborating_sources
                if not policy.satisfies(src)
            ]
            admissible = [src for src in c.corroborating_sources if policy.satisfies(src)]

            # ADR-0019: admissibility is not qualification. A source the Wikidata
            # claim itself cites is a `same-witness` - authoritative, perhaps, but
            # not independent confirmation of that claim - and only an
            # `independent-witness` satisfies §4.3. Decided mechanically from the
            # claim's own references, never from a hand-written note.
            valid = []
            for src in admissible:
                verdict = self._witness(c, src)
                if verdict is None or verdict.qualifies:
                    valid.append(src)
                else:
                    rejections.append(f"{src.provider}: {verdict}")
            duplicates = policy.duplicate_groups(c.corroborating_sources)

            problems: list[str] = []
            if not c.corroborating_sources:
                problems.append("no second source recorded")
            elif not valid:
                problems.append("no VALID second source: " + "; ".join(rejections))
            if duplicates:
                problems.append(
                    "the same source counted twice ("
                    + "; ".join(f"{k} -> {urls}" for k, urls in duplicates)
                    + ")"
                )

            if not problems:
                continue
            entry = f"{c.constraint_id} ({reason}, status {status}): " + " | ".join(problems)
            # A duplicate is malformed corroboration, not absent corroboration, so
            # it is an error at any status rather than a draft-stage warning.
            if status in promoted_statuses or duplicates:
                errors.append(entry)
            else:
                drafts.append(entry)

        n_needing = sum(1 for c in cs if needs(c) is not None)
        suffix = "" if policy.configured else f" [{policy.describe()}]"
        if errors:
            return RuleResult(
                "corroboration", False,
                f"{len(errors)} constraint(s) have absent, invalid or duplicated "
                f"corroboration; §4.3 requires a valid second source before promotion"
                + suffix,
                errors,
            )
        if drafts:
            return RuleResult(
                "corroboration", False,
                f"{len(drafts)} of {n_needing} constraint(s) needing corroboration "
                "lack a valid second source — permitted while DRAFT, blocking at "
                "promotion" + suffix,
                drafts,
                severity="warning",
            )
        return RuleResult(
            "corroboration", True,
            f"all {n_needing} constraint(s) needing a second source carry a valid one"
            + suffix,
        )

    def validate_corroboration_freeze(
        self, constraints: Sequence[Constraint], store: CorroborationStore | None = None
    ) -> RuleResult:
        """Every corroborating source's frozen artefact must check out.

        Separate from :meth:`validate`, like the other rules that need more than
        the records themselves: this one touches the corroboration store. It
        verifies that the snapshot exists, that it is the key for this
        provider/url/fact, and that the content still hashes to the recorded
        ``content_hash`` — so "frozen" is verified rather than asserted.
        """
        sources = [
            (c.constraint_id, src) for c in constraints for src in c.corroborating_sources
        ]
        if not sources:
            return RuleResult(
                "corroboration_freeze", True,
                "no corroborating source recorded; nothing to verify", severity="info",
            )
        active = store or default_store()
        offenders = [
            f"{cid}: {problem}"
            for cid, src in sources
            if (problem := active.verify(src)) is not None
        ]
        return RuleResult(
            "corroboration_freeze",
            not offenders,
            f"{len(sources)} corroborating source(s) verified against the frozen store"
            if not offenders
            else f"{len(offenders)} of {len(sources)} source(s) failed freeze verification",
            offenders,
        )

    def _expected_answer_type(self, schema_id: str, cls: ConstraintClass) -> str | None:
        return answer_type_for_cell(schema_id, cls, self.cfg)

    def _answer_type_allocation(self, cs: Sequence[Constraint]) -> RuleResult:
        """Every constraint's answer type must match the (axis, class) rule.

        The rule lives in ``configs/benchmark/design.yaml`` and is read, not
        restated. C2 and C3 are ``boolean`` on every axis because a conjunction
        and a universal have no single binary subject-relation-object, and the
        approved probe generator requires one for a direct+affirmative probe of
        an entity/date-answered constraint. C1 and C4 keep the axis-fixed
        allocation.

        The pilot constraints predate ADR-0017 entirely (their answer type is
        tied to class), so they are reported as EXEMPT rather than as failures:
        they are development material, not instances of the 24 test schemas.
        """
        if not cs:
            return RuleResult(
                "answer_type_allocation", True, "no constraints to check", severity="info"
            )
        offenders: list[str] = []
        exempt = 0
        checked = 0
        for c in cs:
            if c.split is Split.PILOT:
                exempt += 1
                continue
            expected = self._expected_answer_type(c.schema_id, c.constraint_class)
            if expected is None:
                continue
            checked += 1
            # str() rather than .value: AnswerType is a StrEnum, and
            # model_copy(update=...) skips validation, so a caller can hand us a
            # plain string here.
            if str(c.answer_type) != expected:
                offenders.append(
                    f"{c.constraint_id} ({c.schema_id}, {c.constraint_class.value}): "
                    f"{c.answer_type!s} but the rule gives {expected}"
                )
        detail = f"{checked} checked"
        if exempt:
            detail += f", {exempt} pilot constraint(s) EXEMPT (predate ADR-0017)"
        if offenders:
            return RuleResult(
                "answer_type_allocation", False,
                f"{len(offenders)} constraint(s) disagree with ADR-0017's (axis, class) "
                f"rule; {detail}",
                offenders,
            )
        return RuleResult(
            "answer_type_allocation", True,
            f"answer type follows the (axis, class) rule; {detail}",
        )

    def _claims_renderable(self, cs: Sequence[Constraint]) -> RuleResult:
        """Every non-boolean constraint's answer must be locatable in its own
        gold proposition, directly or through a registered alias.

        D2 and D3 both build a claim by SUBSTITUTING the model's answer for the
        gold answer inside `gold_proposition`. If the gold answer does not occur
        there, `d2.templates.render_claim` refuses — correctly, since inventing
        a proposition would put words in the model's mouth.

        Added 2026-10-15 after the first D3 run aborted on `K-C1-BIO-14`:
        gold `1953-04-25` against a proposition reading "25 April 1953". THIRTEEN
        of 44 non-boolean constraints were affected, all date-answered. It went
        unnoticed from authoring because D2 and D3 are the only consumers of
        `render_claim` and NEITHER HAD EVER BEEN EXECUTED. A gate that only fires
        inside a detector is a gate that fires after the GPU time is spent.

        Boolean constraints are exempt: the proposition IS the claim, asserted
        by YES and negated by NO, so nothing is substituted.
        """
        from ..detectors.d2.templates import ClaimRenderingError, _substitute

        offenders = []
        for c in cs:
            if str(c.answer_type) == "boolean":
                continue
            aliases = (c.answer_aliases or {}).get(c.gold_answer, ())
            try:
                _substitute(c.gold_proposition, c.gold_answer, "<X>", aliases)
            except ClaimRenderingError:
                offenders.append(
                    f"{c.constraint_id} ({c.answer_type!s}): gold {c.gold_answer!r} "
                    f"not in proposition and no alias matches"
                )
        n = sum(1 for c in cs if str(c.answer_type) != "boolean")
        return RuleResult(
            "claims_renderable",
            not offenders,
            f"{n} non-boolean constraint(s) checked; "
            + ("every answer is locatable in its proposition"
               if not offenders else
               f"{len(offenders)} cannot render a claim — D2 and D3 would refuse them"),
            offenders,
        )

    def _comparison_universe(self, cs: Sequence[Constraint]) -> RuleResult:
        """Extremal schemas carry a frozen comparison universe (axis 5).

        The HARD rule lives in :class:`~semintegrity.schemas.constraint.Constraint`
        — a record cannot be constructed claiming EVIDENCE_VERIFIED or above
        without one, so this cannot be bypassed by skipping the validator. This
        rule exists so the requirement is *visible* while the constraint is still
        DRAFT, rather than surfacing only at promotion when the authoring session
        is over.
        """
        extremal: list[Constraint] = []
        for c in cs:
            m = SCHEMA_RE.match(c.schema_id)
            if m and int(m.group(2)) in EXTREMAL_SCHEMA_INDICES:
                extremal.append(c)
        if not extremal:
            return RuleResult(
                "comparison_universe", True,
                "no extremal schema in this split; the rule does not apply",
                severity="info",
            )
        missing = [
            f"{c.constraint_id} ({c.schema_id}, status {c.verification_status!s})"
            for c in extremal
            if c.comparison_universe is None
        ]
        if missing:
            return RuleResult(
                "comparison_universe", False,
                f"{len(missing)} of {len(extremal)} extremal constraint(s) have no frozen "
                "comparison universe — permitted while DRAFT, refused at promotion by the "
                "Constraint schema itself",
                missing,
                severity="warning",
            )
        # `missing` is empty here, so every extremal constraint has a universe;
        # the filter states that invariant rather than asserting it.
        universes = [c.comparison_universe for c in extremal if c.comparison_universe]
        bases = Counter("enumerated" if u.members else "ranked_source" for u in universes)
        return RuleResult(
            "comparison_universe", True,
            f"all {len(extremal)} extremal constraint(s) carry a frozen universe "
            f"({dict(bases)})",
        )

    def validate_global_id_uniqueness(
        self, constraints: Sequence[Constraint]
    ) -> RuleResult:
        """No ``constraint_id`` is reused across splits.

        :meth:`validate` filters to one split before checking ``unique_ids``, and
        the id grammar in :mod:`semintegrity.utils.ids`
        (``K-<class>-<domain>-<nn>``) carries no split field. So a TEST constraint
        and a PILOT/DEV constraint may share an id, pass both per-split
        validations, and then silently merge in any analysis that joins on
        ``constraint_id``.

        The defence is the index allocation -- test cells occupy 11..16 and
        pilot/dev keep 01..10 -- and this makes that allocation checkable. Test
        numbered 01..06 would re-mint all 12 existing pilot ids.
        """
        seen: dict[str, Split] = {}
        offenders: list[str] = []
        for c in sorted(constraints, key=lambda c: (c.constraint_id, c.split.value)):
            prior = seen.get(c.constraint_id)
            if prior is not None and prior is not c.split:
                offenders.append(
                    f"{c.constraint_id} appears in both {prior.value} and {c.split.value}"
                )
            else:
                seen[c.constraint_id] = c.split
        return RuleResult(
            "cross_split_ids",
            not offenders,
            "no constraint id is reused across splits"
            if not offenders
            else f"{len(offenders)} id(s) reused across splits; any join on "
            "constraint_id would merge distinct constraints",
            offenders,
        )

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
        """``constraint_id`` uniqueness WITHIN one split.

        Scoped deliberately, and named in the message, because ``validate`` is
        called per split: a cross-split collision is invisible here and is the
        job of :meth:`validate_global_id_uniqueness`.
        """
        dupes = [cid for cid, n in Counter(c.constraint_id for c in cs).items() if n > 1]
        return RuleResult(
            "unique_ids",
            not dupes,
            "all constraint ids unique within this split"
            if not dupes
            else f"{len(dupes)} duplicate id(s) within this split",
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
