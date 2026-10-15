"""Per-constraint evaluation rows and the §4.11 confirmatory contrasts.

This module holds the row builder that was previously inline in
:mod:`semintegrity.analysis.pilot_report`. It is extracted, not reimplemented:
``pilot_report`` and the multi-model primary evaluator both call
:func:`constraint_rows`, so there is **one** definition of what a per-constraint
row means. Two implementations of PSCR that agreed today would not stay agreed.

What this module does NOT do:

* **It does not define new metrics.** The primary metrics live in
  :mod:`semintegrity.analysis.metrics`; the row builder reports the same
  quantities the pilot already reported.
* **It does not decide Q22.** Both D0 readings (pairwise and set-level) are
  carried, exactly as the pilot report carries them, because choosing one here
  would settle an open question by implementation.
* **It does not impute.** An undefined PSCR stays ``None`` and is resampled as a
  cluster that contributes nothing, which widens the interval rather than
  biasing it (Q6).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..canonicalization.canonicaliser import canonicalise
from ..detectors.d1.exact_match import check_all_pairs, coverage
from ..schemas.constraint import Constraint
from ..schemas.enums import ResponseLabel, Verdict
from ..schemas.probe import Probe
from ..schemas.response import RawResponse
from .bootstrap import bootstrap_difference, cluster_bootstrap
from .detector_agreement import DECIDED, d0_pair_verdicts

#: The confirmatory contrasts, read from configs/analysis/statistics.yaml's
#: `confirmatory.contrasts`. Stated as (id, name, arm A classes, arm B classes).
#: These are PRE-SPECIFIED and exempt from FDR (statistics.yaml:multiplicity).
CONFIRMATORY_CONTRASTS: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("H1_primary", "C1+C2 vs C3+C4", ("C1", "C2"), ("C3", "C4")),
    ("H1_planned", "C4 vs C1-C3 pooled", ("C4",), ("C1", "C2", "C3")),
)


@dataclass(slots=True)
class Stage0Summary:
    """Canonicalisation outcome for one run, with the CANON gate applied."""

    labels: dict[str, int]
    n_responses: int
    n_invalid: int
    rate: float
    threshold: float
    passed: bool


def constraint_rows(
    raws: Sequence[RawResponse],
    constraints: Mapping[str, Constraint],
    probes: Mapping[str, Probe],
    *,
    d0_kb: Any | None = None,
    d0_registry: Any | None = None,
    d0_status: str = "not_attempted",
) -> tuple[list[dict[str, Any]], Counter]:
    """One row per constraint, plus the Stage 0 label counter.

    ``d0_kb``/``d0_registry`` are optional so the caller decides whether D0 runs
    at all. When they are absent every D0 field is reported as not attempted —
    "D0 covered nothing" and "D0 never ran" are different claims and must not
    look alike.
    """
    by_constraint: dict[str, list] = defaultdict(list)
    for r in raws:
        if r.constraint_id not in constraints:
            raise KeyError(f"response references unknown constraint {r.constraint_id}")
        if r.probe_id not in probes:
            raise KeyError(f"response references unknown probe {r.probe_id}")
        by_constraint[r.constraint_id].append(
            canonicalise(r, constraints[r.constraint_id], probes[r.probe_id])
        )

    rows: list[dict[str, Any]] = []
    labels: Counter = Counter()
    for cid, canon in sorted(by_constraint.items()):
        c = constraints[cid]
        labels.update(x.label for x in canon)
        results = check_all_pairs(canon)
        evaluable = [r for r in results if r.verdict is not Verdict.NOT_APPLICABLE]
        contradictions = sum(r.is_contradiction for r in results)

        # --- D0: BOTH readings, because Q22 is open ---------------------------
        d0_pair_total = d0_pair_covered = d0_pair_violations = 0
        d0_set_verdict = None
        d0_note = d0_status
        if d0_kb is not None and d0_registry is not None and d0_registry.has(c.formal_predicate):
            pred = d0_registry.get(c.formal_predicate)
            # ONE definition of which pairs D0 is asked about, shared with
            # `analysis.detector_agreement`. Two implementations that agreed
            # today would not stay agreed, and the agreement report would then
            # be comparing a different D0 from the one these rows describe.
            d0_verdicts = d0_pair_verdicts(c, canon, d0_kb, d0_registry)
            d0_pair_total = len(d0_verdicts)
            d0_pair_covered = sum(v in DECIDED for v in d0_verdicts.values())
            d0_pair_violations = sum(v is Verdict.VIOLATION for v in d0_verdicts.values())
            set_result = pred.check_set(c, canon, d0_kb)
            d0_set_verdict = set_result.verdict.value
            d0_note = set_result.reason or "ok"
        elif d0_kb is not None and d0_registry is not None:
            d0_note = f"no predicate registered for {c.formal_predicate!r}"

        # A NEGATED response asserted "not g". It IS an answer — the model
        # committed — but it is wrong whenever g is gold, so it sits in the
        # denominator of truth accuracy and never in the numerator. Folding it
        # into abstention would flatter the model by hiding a wrong answer.
        definite = [x for x in canon if x.label is ResponseLabel.ANSWER]
        negated = [x for x in canon if x.label is ResponseLabel.NEGATED]
        answered = definite + negated
        correct = sum(x.canonical_answer == c.gold_answer for x in definite)
        cluster = Counter(x.canonical_answer for x in definite)
        n_abstain = sum(x.label is ResponseLabel.ABSTAIN for x in canon)
        rows.append({
            "constraint_id": cid,
            "class": c.constraint_class.value,
            "domain": c.domain.value,
            "schema_id": c.schema_id,
            "family_id": c.family_id,
            "answer_type": str(c.answer_type),
            "answer_space_cardinality": len(c.answer_space),
            "entity_sitelinks_median": _median(c.entity_sitelinks),
            "verification_status": str(c.verification_status),
            "n_responses": len(canon),
            "n_answer": len(answered),
            "n_definite": len(definite),
            "n_negated": len(negated),
            "n_abstain": n_abstain,
            "n_pairs": len(results),
            "n_evaluable_pairs": len(evaluable),
            "n_contradictory_pairs": contradictions,
            # PSCR is UNDEFINED with no evaluable pairs — never imputed as 0 (Q6).
            "pscr": (contradictions / len(evaluable)) if evaluable else None,
            # PCS uses the DEFINITE cluster only: "not Canberra" names no cluster.
            "pcs": (max(cluster.values()) / len(canon)) if cluster else None,
            "truth_accuracy": (correct / len(answered)) if answered else None,
            "abstention_rate": n_abstain / len(canon) if canon else None,
            "d1_coverage": coverage(results),
            "d0_pairs_considered": d0_pair_total,
            "d0_pairs_covered": d0_pair_covered,
            "d0_coverage": (d0_pair_covered / len(results)) if results else None,
            "d0_pair_violations": d0_pair_violations,
            "d0_pscr": (d0_pair_violations / d0_pair_covered) if d0_pair_covered else None,
            "d0_set_verdict": d0_set_verdict,
            "d0_note": d0_note,
        })
    return rows, labels


def _median(values: Sequence[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def canon_threshold() -> float:
    """The CANON go/no-go threshold, as a FRACTION, read from configuration.

    The criterion is prose in ``configs/inference/pilot.yaml`` (">= 95% of valid
    pilot responses"), so it is parsed rather than restated. Mirrors
    ``scripts/analysis/evaluate_cloze_rewrite.canon_threshold_pct``, which
    returns a percentage; this returns a fraction because every rate in this
    module is a fraction. A threshold duplicated in code is a threshold that
    will eventually disagree with itself.
    """
    import re

    from ..utils.config import load_config

    for gate in load_config("configs/inference/pilot.yaml").data["go_no_go"]:
        if gate["id"] == "CANON":
            m = re.search(r">=\s*(\d+(?:\.\d+)?)\s*%", gate["criterion"])
            if not m:
                raise ValueError(f"cannot parse a threshold from {gate['criterion']!r}")
            return float(m.group(1)) / 100.0
    raise ValueError("no CANON gate in configs/inference/pilot.yaml")


def stage0_summary(labels: Counter, *, threshold: float) -> Stage0Summary:
    """The CANON go/no-go criterion, applied rather than left to be recomputed.

    NEGATED and ABSTAIN both count as canonicalised: the first is a resolved
    answer, the second a first-class outcome (§4.7).
    """
    n_total = sum(labels.values())
    n_invalid = labels.get(ResponseLabel.INVALID, 0)
    rate = (n_total - n_invalid) / n_total if n_total else 0.0
    return Stage0Summary(
        labels={getattr(k, "value", str(k)): v for k, v in labels.items()},
        n_responses=n_total, n_invalid=n_invalid, rate=rate,
        threshold=threshold, passed=rate >= threshold,
    )


def _arm(rows: Sequence[Mapping[str, Any]], classes: Sequence[str], metric: str) -> list:
    return [r[metric] for r in rows if r["class"] in set(classes)]


def confirmatory_contrasts(
    rows: Sequence[Mapping[str, Any]],
    *,
    metric: str = "pscr",
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 20250058,
) -> list[dict[str, Any]]:
    """The §4.11 pre-specified contrasts, by cluster bootstrap over constraints.

    The arms are DISJOINT constraint sets, so each is resampled separately
    (:func:`bootstrap_difference`). These are pre-specified and **exempt from
    FDR**, per `configs/analysis/statistics.yaml:confirmatory.multiplicity`;
    the exemption is recorded on every row so a reader cannot mistake the
    absence of a q-value for an oversight.
    """
    out: list[dict[str, Any]] = []
    for cid, name, arm_a, arm_b in CONFIRMATORY_CONTRASTS:
        a, b = _arm(rows, arm_a, metric), _arm(rows, arm_b, metric)
        res = bootstrap_difference(a, b, n_boot=n_boot, ci=ci, seed=seed)
        out.append({
            "contrast_id": cid, "name": name, "metric": metric,
            "arm_a_classes": list(arm_a), "arm_b_classes": list(arm_b),
            "arm_a_n": len(a), "arm_b_n": len(b),
            "estimate": res.estimate, "ci_low": res.ci_low, "ci_high": res.ci_high,
            "ci_level": res.ci_level, "method": res.method, "n_boot": res.n_boot,
            "n_defined": res.n_defined, "n_degenerate_resamples": res.n_degenerate_resamples,
            "fdr": "EXEMPT — pre-specified confirmatory contrast (statistics.yaml)",
            # A bootstrap interval is not a test. Whether the interval excludes
            # zero is stated as exactly that, never as a p-value.
            "excludes_zero": (
                None if res.ci_low is None or res.ci_high is None
                else not (res.ci_low <= 0.0 <= res.ci_high)
            ),
        })
    return out


def class_profile(
    rows: Sequence[Mapping[str, Any]],
    *,
    metric: str = "pscr",
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 20250058,
) -> list[dict[str, Any]]:
    """Per-class estimates with cluster-bootstrap intervals (descriptive).

    §4.11 frames this as a structural inconsistency PROFILE, not a complexity
    curve, and the framing is carried in the output so a figure built from this
    table cannot quietly become an ordering claim.
    """
    out = []
    for cls in ("C1", "C2", "C3", "C4"):
        values = _arm(rows, (cls,), metric)
        res = cluster_bootstrap(values, n_boot=n_boot, ci=ci, seed=seed)
        out.append({
            "class": cls, "metric": metric, "estimate": res.estimate,
            "ci_low": res.ci_low, "ci_high": res.ci_high, "ci_level": res.ci_level,
            "method": res.method, "n_clusters": res.n_clusters, "n_defined": res.n_defined,
            "framing": "structural inconsistency profile; classes are CATEGORICAL, never ordered",
        })
    return out
