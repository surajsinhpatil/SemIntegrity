"""Ground-truth sensitivity analyses S1/S2/S3 (ADR-0023 D9).

81 of 132 constraints are `DRAFT` for want of a §4.3 second source, so the
benchmark's ground truth is provisional to that extent. With human validation
removed, this is the **primary defence of the confirmatory results**: it
replaces the assurance that human-validated ground truth would have provided.

WHY H1_primary CANNOT BE RESTRICTED TO THE VERIFIED SUBSET
----------------------------------------------------------
The obvious analysis — re-run H1_primary on the 48 `EVIDENCE_VERIFIED` test
constraints — is **invalid**, and the code refuses it. Measured from the
benchmark data:

====  ==  ==  ==  ====
         C1  C2  C3    C4
====  ==  ==  ==  ====
EV       16  16  16   **0**
DRAFT    14  14  14    30
====  ==  ==  ==  ====

H1_primary is ``C1+C2 vs C3+C4``. With C4 empty, arm B would be **C3 alone** — a
different contrast wearing the same name. And the chance balance that protects
the contrast is destroyed: both arms sit at 0.5556 on the full benchmark (gap
0.0000) but at 0.5417 vs 0.5000 (gap **+0.0417**) on the 48.
``statistics.yaml`` is explicit that "design balance (ADR-0017), not adjustment"
is what protects the confirmatory contrast, so the protection does not survive
the restriction.

CONFOUNDING IS ASSESSED FROM THE DATA, NOT ASSERTED
---------------------------------------------------
:func:`confound_report` computes, per class, whether the verified and draft
subsets are comparable. It does not hardcode a conclusion. On the frozen
benchmark it finds:

* **C2 and C3: comparable on answer type.** Both subsets are entirely boolean,
  so the chance-PSCR gap is exactly 0.0000.
* **C1: CONFOUNDED.** The verified subset holds no `date` constraints while the
  draft subset is 10/14 `date`, giving a chance gap of -0.0595. An EV-vs-DRAFT
  difference in C1 is a difference between answer-type mixtures.
* **C4: NOT ASSESSABLE.** No verified constraint exists.
* **A residual confound in every class: domain.** All 24 `history` constraints
  are DRAFT, so `history` is absent from every verified subset. This is reported
  and not adjusted for — a bootstrap on a difference in means cannot deliver
  covariate adjustment (§4.11).

Each S1 cell therefore carries its own verdict, and a confounded or
non-assessable cell is returned **with an estimate of ``None``** rather than a
number a reader might quote. That is the rule throughout this project: a
refusal, not a silent fallback.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import mean, median
from typing import Any

from .bootstrap import BootstrapResult, bootstrap_difference, cluster_bootstrap

#: Comparability verdicts for one class's verified-vs-draft comparison.
COMPARABLE = "COMPARABLE"
CONFOUNDED_ANSWER_TYPE = "CONFOUNDED_ANSWER_TYPE"
NOT_ASSESSABLE_NO_OVERLAP = "NOT_ASSESSABLE_NO_OVERLAP"

#: A chance-PSCR gap wider than this between the two subsets makes the
#: comparison a comparison of answer-type mixtures. 0.01 is a tenth of the
#: smallest confirmatory effect observed (0.090) and an order of magnitude
#: below it, so a gap under it cannot drive a finding of that size.
CHANCE_GAP_TOLERANCE = 0.01

VERIFIED = "EVIDENCE_VERIFIED"
DRAFT = "DRAFT"


def chance_pscr(constraint: Any) -> float:
    """Expected pairwise contradiction rate under independent random answering.

    Two independent draws from a closed space of size m agree with probability
    1/m, so the chance contradiction rate is 1 - 1/m (statistics.yaml,
    ADR-0017). This is the quantity whose balance protects H1_primary.
    """
    m = len(constraint.answer_space)
    if m < 1:
        raise ValueError(f"{constraint.constraint_id} has an empty answer space")
    return 1.0 - 1.0 / m


@dataclass(frozen=True, slots=True)
class ClassConfound:
    """Whether one class's verified and draft subsets may be compared."""

    constraint_class: str
    n_verified: int
    n_draft: int
    verdict: str
    chance_verified: float | None
    chance_draft: float | None
    chance_gap: float | None
    answer_types_verified: dict[str, int]
    answer_types_draft: dict[str, int]
    domains_verified: dict[str, int]
    domains_draft: dict[str, int]
    domains_missing_from_verified: tuple[str, ...]
    median_sitelinks_verified: float | None
    median_sitelinks_draft: float | None
    notes: tuple[str, ...]

    @property
    def comparable(self) -> bool:
        return self.verdict == COMPARABLE


def _counts(constraints: Sequence[Any], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in constraints:
        key = str(getattr(c, attr))
        key = key.split(".")[-1].lower() if "." in key else key
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


def _median_sitelinks(constraints: Sequence[Any]) -> float | None:
    values = [median(c.entity_sitelinks) for c in constraints if c.entity_sitelinks]
    return median(values) if values else None


def confound_report(constraints: Sequence[Any]) -> dict[str, ClassConfound]:
    """Per class, is the verified-vs-draft comparison defensible?

    Computed from the constraints themselves. Nothing here is hardcoded for the
    current benchmark, so re-authoring changes the verdict rather than silently
    invalidating it.
    """
    out: dict[str, ClassConfound] = {}
    classes = sorted({str(c.constraint_class.value) for c in constraints})
    for klass in classes:
        sub = [c for c in constraints if c.constraint_class.value == klass]
        ver = [c for c in sub if str(c.verification_status) == VERIFIED]
        dra = [c for c in sub if str(c.verification_status) == DRAFT]
        at_v, at_d = _counts(ver, "answer_type"), _counts(dra, "answer_type")
        dm_v, dm_d = _counts(ver, "domain"), _counts(dra, "domain")
        missing = tuple(d for d in dm_d if d not in dm_v)
        notes: list[str] = []

        if not ver or not dra:
            verdict = NOT_ASSESSABLE_NO_OVERLAP
            cv = cd = gap = None
            notes.append(
                f"no overlap: {len(ver)} verified, {len(dra)} draft. "
                "This class's ground truth cannot be sensitivity-tested."
            )
        else:
            cv, cd = mean(chance_pscr(c) for c in ver), mean(chance_pscr(c) for c in dra)
            gap = cv - cd
            if abs(gap) > CHANCE_GAP_TOLERANCE:
                verdict = CONFOUNDED_ANSWER_TYPE
                notes.append(
                    f"chance-PSCR gap {gap:+.4f} exceeds the {CHANCE_GAP_TOLERANCE} "
                    f"tolerance: verified {at_v} vs draft {at_d}. A verified-vs-draft "
                    "difference here is a difference between answer-type mixtures, "
                    "not an effect of verification status."
                )
            else:
                verdict = COMPARABLE
                notes.append(
                    f"answer-type composition matched (chance gap {gap:+.4f})"
                )
        if missing:
            notes.append(
                f"RESIDUAL CONFOUND: domain(s) {list(missing)} appear only in the "
                "draft subset. Not adjusted for -- a bootstrap on a difference in "
                "means cannot deliver covariate adjustment (§4.11)."
            )
        out[klass] = ClassConfound(
            constraint_class=klass, n_verified=len(ver), n_draft=len(dra),
            verdict=verdict, chance_verified=cv, chance_draft=cd, chance_gap=gap,
            answer_types_verified=at_v, answer_types_draft=at_d,
            domains_verified=dm_v, domains_draft=dm_d,
            domains_missing_from_verified=missing,
            median_sitelinks_verified=_median_sitelinks(ver),
            median_sitelinks_draft=_median_sitelinks(dra),
            notes=tuple(notes),
        )
    return out


def _pscr_by_status(
    rows: Sequence[Mapping[str, Any]], klass: str, status: str, metric: str
) -> list[float | None]:
    return [
        r[metric] for r in rows
        if r["class"] == klass and str(r.get("verification_status")) == status
    ]


def s1_within_class(
    rows: Sequence[Mapping[str, Any]],
    constraints: Sequence[Any],
    *,
    metric: str = "pscr",
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 20250058,
) -> dict[str, dict[str, Any]]:
    """**S1 — the primary sensitivity analysis.**

    Within each class, the difference in mean constraint-level ``metric``
    between `EVIDENCE_VERIFIED` and `DRAFT` constraints, with a cluster
    bootstrap over constraints. Holding class fixed holds answer-type and
    chance composition *approximately* fixed, which is what makes this — rather
    than a restricted H1 — the estimable question.

    **A class whose subsets are not comparable gets ``estimate: None``.** The
    descriptive counts and both subset means are still returned, because
    "we could not estimate this" and "we did not look" are different claims.
    """
    confounds = confound_report(constraints)
    out: dict[str, dict[str, Any]] = {}
    for klass, cf in confounds.items():
        ver = _pscr_by_status(rows, klass, VERIFIED, metric)
        dra = _pscr_by_status(rows, klass, DRAFT, metric)
        defined_v = [v for v in ver if v is not None]
        defined_d = [v for v in dra if v is not None]
        entry: dict[str, Any] = {
            "class": klass,
            "metric": metric,
            "comparability": cf.verdict,
            "comparable": cf.comparable,
            "n_verified": len(ver),
            "n_draft": len(dra),
            "n_verified_defined": len(defined_v),
            "n_draft_defined": len(defined_d),
            "mean_verified": mean(defined_v) if defined_v else None,
            "mean_draft": mean(defined_d) if defined_d else None,
            "chance_gap": cf.chance_gap,
            "notes": list(cf.notes),
            "unit": "constraint",
        }
        if not cf.comparable or not defined_v or not defined_d:
            entry["estimate"] = None
            entry["ci_low"] = entry["ci_high"] = None
            entry["refusal"] = (
                f"no estimate: comparability is {cf.verdict}. "
                "The subset means above are descriptive only and must not be "
                "differenced by a reader."
            )
        else:
            res = bootstrap_difference(ver, dra, n_boot=n_boot, ci=ci, seed=seed)
            entry.update(
                estimate=res.estimate, ci_low=res.ci_low, ci_high=res.ci_high,
                method=res.method, n_boot=res.n_boot,
                excludes_zero=(
                    res.ci_low is not None and res.ci_high is not None
                    and (res.ci_low > 0 or res.ci_high < 0)
                ),
            )
        out[klass] = entry
    return out


def s2_verified_only_profile(
    rows: Sequence[Mapping[str, Any]],
    *,
    metric: str = "pscr",
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 20250058,
) -> dict[str, dict[str, Any]]:
    """**S2 — per-class profile restricted to EVIDENCE_VERIFIED.** Descriptive.

    No contrast is formed, so no chance-balance assumption is needed. Intended
    to be read beside the full-benchmark per-class values, not instead of them.
    """
    out: dict[str, dict[str, Any]] = {}
    for klass in sorted({r["class"] for r in rows}):
        values = _pscr_by_status(rows, klass, VERIFIED, metric)
        res: BootstrapResult = cluster_bootstrap(
            values, n_boot=n_boot, ci=ci, seed=seed
        )
        out[klass] = {
            "class": klass, "n_constraints": res.n_clusters,
            "n_defined": res.n_defined, "estimate": res.estimate,
            "ci_low": res.ci_low, "ci_high": res.ci_high, "method": res.method,
            "unit": "constraint", "subset": VERIFIED,
            "note": "descriptive; NOT a contrast and NOT H1_primary",
        }
    return out


def s3_restricted_contrast(
    rows: Sequence[Mapping[str, Any]],
    constraints: Sequence[Any],
    *,
    arm_a: Sequence[str] = ("C1", "C2"),
    arm_b: Sequence[str] = ("C3", "C4"),
    metric: str = "pscr",
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 20250058,
) -> dict[str, Any]:
    """**S3 — the arm contrast on the verified subset. NOT H1_primary.**

    Returns the contrast actually computable on the verified subset, together
    with the arms that were *requested*, the classes that survived, and the
    chance gap the restriction introduces. The name ``H1_primary`` is never
    applied to the result.

    The chance gap's **direction** is reported because it is interpretable: on
    the frozen benchmark the restriction raises arm A's chance PSCR above arm
    B's (+0.0417), which pushes the estimate toward **positive**. The
    full-benchmark finding is negative, so the bias works **against** it and a
    negative estimate here is conservative.
    """
    by_id = {c.constraint_id: c for c in constraints}
    ver_rows = [r for r in rows if str(r.get("verification_status")) == VERIFIED]
    present = {r["class"] for r in ver_rows}
    kept_a = [k for k in arm_a if k in present]
    kept_b = [k for k in arm_b if k in present]
    dropped = [k for k in list(arm_a) + list(arm_b) if k not in present]

    def _arm(classes: Sequence[str]) -> tuple[list[float | None], float | None]:
        rs = [r for r in ver_rows if r["class"] in classes]
        values = [r[metric] for r in rs]
        chances = [
            chance_pscr(by_id[r["constraint_id"]])
            for r in rs if r["constraint_id"] in by_id
        ]
        return values, (mean(chances) if chances else None)

    a_values, a_chance = _arm(kept_a)
    b_values, b_chance = _arm(kept_b)
    gap = (a_chance - b_chance) if (a_chance is not None and b_chance is not None) else None

    entry: dict[str, Any] = {
        "is_h1_primary": False,
        "name": f"{'+'.join(kept_a)} vs {'+'.join(kept_b)} (EVIDENCE_VERIFIED only)",
        "requested_arm_a": list(arm_a), "requested_arm_b": list(arm_b),
        "classes_present": sorted(present), "classes_dropped": dropped,
        "n_arm_a": len(a_values), "n_arm_b": len(b_values),
        "chance_arm_a": a_chance, "chance_arm_b": b_chance, "chance_gap": gap,
        "unit": "constraint", "subset": VERIFIED,
    }
    if dropped:
        entry["warning"] = (
            f"class(es) {dropped} have NO verified constraint, so this is a "
            "DIFFERENT contrast from H1_primary and must not be reported under "
            "that name or as confirming it."
        )
    if gap is not None and abs(gap) > CHANCE_GAP_TOLERANCE:
        entry["chance_balance_note"] = (
            f"the restriction introduces a chance-PSCR gap of {gap:+.4f} "
            f"(full benchmark: 0.0000). Chance alone pushes the estimate toward "
            f"{'positive' if gap > 0 else 'negative'}, so it biases "
            f"{'AGAINST' if gap > 0 else 'TOWARD'} the negative sign observed on "
            "the full benchmark."
        )
    if not a_values or not b_values:
        entry.update(estimate=None, ci_low=None, ci_high=None,
                     refusal="an arm is empty on the verified subset")
        return entry
    res = bootstrap_difference(a_values, b_values, n_boot=n_boot, ci=ci, seed=seed)
    entry.update(
        estimate=res.estimate, ci_low=res.ci_low, ci_high=res.ci_high,
        method=res.method, n_boot=res.n_boot,
        excludes_zero=(
            res.ci_low is not None and res.ci_high is not None
            and (res.ci_low > 0 or res.ci_high < 0)
        ),
    )
    return entry


# ---------------------------------------------------------------------------
# S4 — probe-exclusion sensitivity (Q33)
# ---------------------------------------------------------------------------


def s4_probe_exclusion_plan(
    probes_by_constraint: Mapping[str, Sequence[Any]],
    excluded_probe_ids: Sequence[str],
) -> dict[str, Any]:
    """What excluding a set of probes would do to the design, BEFORE any estimate.

    **The exclusion criterion must be response-independent, and this is why S4
    is defensible at all.** `PROBE-C` flags a probe on its *text* — a polar
    cloze whose statement embeds the gold answer — with no reference to any
    model's reply. Excluding on an outcome (say, "probes that went INVALID")
    would be selection on the dependent variable and would bias PSCR by
    construction. Excluding on text does not.

    **What it DOES cost, and this is reported, not hidden:** ADR-0003 balances
    probe factors within each constraint's K=8. Dropping probes breaks that
    balance for the affected constraints and lowers their pair count from
    C(8,2)=28, which widens their per-constraint PSCR. The constraint remains
    the bootstrap unit, so the interval absorbs this rather than ignoring it.

    K=8 stays the **primary** design. S4 is secondary and never replaces it.
    """
    excluded = set(excluded_probe_ids)
    affected: dict[str, dict[str, Any]] = {}
    n_probes = n_excluded = 0
    for cid, probes in probes_by_constraint.items():
        ids = [p.probe_id for p in probes]
        n_probes += len(ids)
        dropped = [i for i in ids if i in excluded]
        n_excluded += len(dropped)
        if dropped:
            kept = len(ids) - len(dropped)
            affected[cid] = {
                "k_before": len(ids), "k_after": kept,
                "n_dropped": len(dropped), "dropped": sorted(dropped),
                "pairs_before": len(ids) * (len(ids) - 1) // 2,
                "pairs_after": kept * (kept - 1) // 2,
                "factor_cells_dropped": sorted(
                    i.rsplit("-P", 1)[-1] for i in dropped
                ),
            }
    k_after = [v["k_after"] for v in affected.values()]
    return {
        "n_probes": n_probes,
        "n_excluded": n_excluded,
        "excluded_share": (n_excluded / n_probes) if n_probes else None,
        "n_constraints": len(probes_by_constraint),
        "n_constraints_affected": len(affected),
        "min_k_after": min(k_after) if k_after else None,
        "pairs_lost": sum(
            v["pairs_before"] - v["pairs_after"] for v in affected.values()
        ),
        "affected": affected,
        "exclusion_is_response_independent": True,
        "primary_design_unchanged": "K=8 remains the primary benchmark design",
        "cost": (
            "breaks the ADR-0003 within-constraint probe-factor balance for the "
            "affected constraints and reduces their pair count, widening their "
            "per-constraint PSCR. The constraint is the bootstrap unit, so the "
            "interval absorbs this."
        ),
    }


def s4_probe_exclusion(
    rows_full: Sequence[Mapping[str, Any]],
    rows_excluded: Sequence[Mapping[str, Any]],
    *,
    metric: str = "pscr",
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 20250058,
) -> dict[str, Any]:
    """**S4 — secondary.** Paired difference in ``metric`` with and without the
    excluded probes.

    Both row sets must describe the **same constraints**, because the comparison
    is paired: each constraint is its own control, which removes between-
    constraint variation that would otherwise swamp a small effect. A mismatch
    raises rather than silently intersecting.

    A non-zero estimate means PSCR depends on the excluded probe type. It does
    **not** say which figure is correct — K=8 is the primary design and the
    excluded set is not known to be wrong, only known to be structurally
    ambiguous in its response format (Q33).
    """
    from .bootstrap import paired_cluster_bootstrap

    ids_full = [r["constraint_id"] for r in rows_full]
    ids_excl = [r["constraint_id"] for r in rows_excluded]
    if ids_full != ids_excl:
        raise ValueError(
            "S4 is PAIRED and needs the same constraints in the same order; got "
            f"{len(ids_full)} vs {len(ids_excl)} "
            f"(first mismatch at index "
            f"{next((i for i, (a, b) in enumerate(zip(ids_full, ids_excl, strict=False)) if a != b), 'n/a')})"
        )
    a = [r[metric] for r in rows_full]
    b = [r[metric] for r in rows_excluded]
    res = paired_cluster_bootstrap(a, b, n_boot=n_boot, ci=ci, seed=seed)
    return {
        "name": "S4 probe-exclusion sensitivity (secondary)",
        "metric": metric,
        "estimate": res.estimate, "ci_low": res.ci_low, "ci_high": res.ci_high,
        "n_constraints": res.n_clusters, "n_defined": res.n_defined,
        "method": res.method, "unit": "constraint", "paired": True,
        "excludes_zero": (
            res.ci_low is not None and res.ci_high is not None
            and (res.ci_low > 0 or res.ci_high < 0)
        ),
        "direction": "full minus excluded",
        "is_primary": False,
        "interpretation_limit": (
            "K=8 is the PRIMARY design. A non-zero estimate shows PSCR depends "
            "on the excluded probe type; it does not establish which figure is "
            "correct, because the excluded probes are not known to be wrong — "
            "only structurally ambiguous in response format (Q33)."
        ),
    }
