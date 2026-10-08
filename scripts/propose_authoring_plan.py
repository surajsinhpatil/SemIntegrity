#!/usr/bin/env python3
"""Emit and validate the 132-constraint authoring plan.

    python scripts/propose_authoring_plan.py              # markdown to stdout
    python scripts/propose_authoring_plan.py --check      # validation only
    python scripts/propose_authoring_plan.py -o docs/AUTHORING_PLAN.md

Authors **nothing**. It states which constraint goes in which cell, what
evidence each schema needs, which D0 registration each maps to, and which gates
every authored record must pass — then validates the whole allocation.

The 120 test cells are **imported** from ``propose_coverage_matrix`` rather than
restated, so this plan cannot drift from the approved Revision 3 matrix. The 12
new development cells are this script's own proposal and are flagged as such.

Status: the test allocation is ADOPTED (decisions A1-A6, 2026-10-06). The
development allocation is ADOPTED (2026-10-07). All five authoring gates are
enforced from the production validation path.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from propose_coverage_matrix import (  # noqa: E402
    AXES,
    CARDINALITY,
    CLASSES,
    DOMAINS,
    TEST_INDEX_BASE,
    Axis,
    allocate,
    answer_type_for,
    d0_behaviour,
    d0_note,
    date_axes,
    dry_run,
)

from semintegrity.benchmark.design_validator import BenchmarkDesignValidator  # noqa: E402
from semintegrity.benchmark.loader import load_split  # noqa: E402
from semintegrity.benchmark.ordering import constraint_indices  # noqa: E402
from semintegrity.utils.ids import constraint_id, family_id, schema_id  # noqa: E402

AXIS_BY_INDEX = {a.index: a for a in AXES}

# ---------------------------------------------------------------------------
# The 12 NEW development constraints — ADOPTED 2026-10-07.
#
# ADR-0007 fixes the frame: dev is 24 constraints, 6 per class, disjoint from the
# 120, with the 12 pilot constraints absorbed and 12 further authored that "reuse
# the same schemas but DIFFERENT entity instantiations". 12 = 3 families x 4
# classes, so three new families are needed and the only open choice is which
# (axis, domain) each sits in.
#
# Chosen so that dev covers what dev is FOR (ADR-0007 lists D2 checkpoint
# selection, per-class D2 threshold calibration, D3 prompt tuning, Track B
# extraction rules, D0 predicate correction, canonicaliser alias tuning):
#
#   * all three answer types appear  -> axis 2 boolean, axis 3 entity, axis 4 date
#   * at least one ANCHOR schema appears, so D0's temporal predicate gets dev
#     exposure before the test split  -> axis 4
#   * the two domains the pilot never covered appear -> history, biology
#
# Index 02/03/04 keeps dev inside 01..10 and clear of the pilot's 01 and the
# test split's 11..16.
DEV_NEW: tuple[tuple[int, str], ...] = (
    (2, "history"),              # F-HIS-02, schemas S-Cx-02, boolean
    (3, "biology"),              # F-BIO-03, schemas S-Cx-03, entity
    (4, "science_technology"),   # F-SCI-04, schemas S-Cx-04, date
)


@dataclass(frozen=True)
class Row:
    split: str
    constraint_id: str
    family_id: str
    schema_id: str
    domain: str
    cls: str
    axis: Axis

    @property
    def answer_type(self) -> str:
        """ADR-0017 as amended: a function of (axis, class)."""
        return answer_type_for(self.axis.index, self.cls)

    @property
    def theme(self) -> str:
        return self.axis.themes[self.domain]


def test_rows() -> list[Row]:
    """The 120 adopted test cells, imported from the approved matrix."""
    return [
        Row("test", c.constraint_id, c.family_id, c.schema_id, c.domain, c.cls, c.axis)
        for c in allocate()
    ]


def dev_new_rows() -> list[Row]:
    """The 12 proposed new development cells."""
    rows: list[Row] = []
    for axis_index, domain in DEV_NEW:
        axis = AXIS_BY_INDEX[axis_index]
        for cls in CLASSES:
            rows.append(
                Row(
                    "dev (new)",
                    constraint_id(cls, domain, axis_index),
                    family_id(domain, axis_index),
                    schema_id(cls, axis_index),
                    domain,
                    cls,
                    axis,
                )
            )
    return rows


# ---------------------------------------------------------------------------
# Evidence requirements. RE-STATED from the approved policy, not invented:
#   §4.3  Wikidata primary but "not treated as absolute truth"; temporal
#         constraints require P580/P582; "all historical and temporal facts are
#         corroborated against a second authoritative source"; every constraint
#         stores its source, source URL and retrieval date.
#   ADR-0011  evidence resolves from the frozen KB cache; jobs never hit the
#             network.
#   Constraint schema  gold_source / gold_source_url / gold_source_date required;
#             C4 requires temporal_validity; EVIDENCE_VERIFIED requires at least
#             one Evidence record with supports_gold=True.
EVIDENCE_BASELINE = (
    "Wikidata claim for the gold proposition (>=1 Evidence record with "
    "supports_gold=True) · entity QIDs + sitelink counts · gold_source, "
    "gold_source_url, gold_source_date · resolved from the frozen cache"
)

#: Per-axis additions on top of the baseline, and whether authoring needs a
#: special route before it can start.
EVIDENCE_BY_AXIS: dict[int, tuple[str, str]] = {
    1: (
        "the role property itself (e.g. P36-style single-valued claims); for C4, "
        "P580/P582 on the role-holding",
        "",
    ),
    2: (
        "membership claims for BOTH categories, and a source for the "
        "DISJOINTNESS itself rather than only the memberships",
        "SPECIAL: Wikidata states disjointness unevenly (P1889 'different from', "
        "disjoint-union statements). The claim 'A and B are mutually exclusive' "
        "often has no single citable statement, so the second source carries it. "
        "Decide the sourcing route per family before authoring.",
    ),
    3: (
        "the containment claim at each level named by the schema; for C3, the "
        "full chain x->y->z as separate Evidence records",
        "SPECIAL: C3 transitivity needs three claims, not one, so a single "
        "supports_gold record does not establish the constraint.",
    ),
    4: (
        "P585/P580 date claims for both events, plus a second authoritative "
        "source (§4.3: all temporal facts corroborated)",
        "SPECIAL: C2 requires two events sharing one boundary year — a "
        "conjunction of two dated claims, both corroborated.",
    ),
    5: (
        "the measure for every member of the stated comparison set, plus the set "
        "definition itself",
        "SPECIAL: Wikidata has no 'is the highest/largest/longest' property. A "
        "superlative must be established either from a ranked query over a "
        "closed set or from an authoritative list, and the COMPARISON SET must "
        "be recorded or the gold answer is not well-defined. The heaviest "
        "evidence burden of the six axes.",
    ),
    6: (
        "P580 and P582 on the interval, plus a second authoritative source; for "
        "C2, both intervals",
        "SPECIAL: end dates are frequently disputed or absent in Wikidata; "
        "`end_unknown` exists precisely so 'still valid' is not conflated with "
        "'unknown'. Corroboration is mandatory, not optional.",
    ),
}

# ---------------------------------------------------------------------------
#: The authoring gates. `enforced_by` names the code that actually runs the
#: check; GAP means no automated enforcement exists yet.
GATES: tuple[tuple[str, str, str], ...] = (
    ("schema validity",
     "Constraint / Probe pydantic models — extra='forbid', id patterns, "
     "cross-field validator, C4 requires temporal_validity, boolean space is "
     "exactly {YES,NO}",
     "schemas/constraint.py, schemas/probe.py"),
    ("unique IDs, within split",
     "no duplicate constraint_id inside the validated split",
     "design_validator._unique_ids"),
    ("unique IDs, across splits",
     "no constraint_id reused between pilot/dev and test — the id grammar has no "
     "split field and validate() sees one split at a time",
     "design_validator.validate_global_id_uniqueness, invoked by the `validate` "
     "CLI for every run over all splits present on disk, and by the readiness "
     "audit"),
    ("class / schema / family mapping",
     "id-encoded class and domain agree with the fields; schema belongs to one "
     "class; family is domain-fixed; every family spans all four classes",
     "Constraint._cross_field + design_validator.{schema_class_fixed,"
     "family_domain_fixed,family_completeness}"),
    ("lattice balance",
     "120 total, 30 per class, 6 per (domain,class), 6 schemas x 5 instances, "
     "schema x domain fully crossed",
     "design_validator.validate(..., strict_schema_crossing=True)"),
    ("ground-truth completeness",
     "gold_source, gold_source_url, gold_source_date present; gold_proposition "
     "non-empty",
     "schemas/constraint.py (required fields)"),
    ("second-source corroboration",
     "§4.3 requires a second authoritative source for historical and temporal "
     "facts; design.yaml sets second_source_required: true",
     "design_validator._corroboration — policy read from design.yaml; error once "
     "a constraint claims EVIDENCE_VERIFIED or above, warning while DRAFT"),
    ("expected-answer validity",
     "gold_answer is a member of the closed answer_space; aliases only for "
     "members; each probe's expected_answer is in the space or boolean",
     "Constraint._cross_field + loader.check_probe_sets"),
    ("probe count = 8",
     "exactly K probes per constraint, indices 1..K",
     "loader.check_probe_sets(k=8)"),
    ("factor-cell completeness",
     "each constraint carries all 8 (polarity x register x directionality) cells "
     "exactly once",
     "loader.check_factor_cell_completeness, invoked by check_probe_sets — "
     "all 8 cells exactly once; distinctness alone is insufficient and is "
     "tested to be insufficient"),
    ("no duplicate probe text in a constraint",
     "identical surfaces inflate apparent agreement",
     "loader.check_distinct_probe_texts, invoked by check_probe_sets as a HARD "
     "failure"),
    ("formal representation validity",
     "all 8 probes of a constraint are mutually equivalent on the §4.4.1 key",
     "schemas/probe.assert_mutually_equivalent via loader.check_probe_sets"),
    ("D0 registration compatibility",
     "every formal_predicate resolves in the D0 registry",
     "design_validator._predicates_registered; "
     "`validate --strict-d0` makes it an error rather than a coverage warning"),
    ("evidence / provenance completeness",
     ">=1 Evidence record with supports_gold=True before EVIDENCE_VERIFIED; a "
     "NAMED human before HUMAN_VALIDATED",
     "Constraint._cross_field verification ladder"),
    ("split correctness",
     "dev shares no entity set or gold proposition with test",
     "design_validator.validate_split_disjointness, invoked by the `validate` "
     "CLI; reported as VACUOUS (explicitly not a pass) until both splits exist"),
    ("entity-familiarity matching",
     "§4.3: sitelink distribution matched across classes, Kruskal-Wallis p > 0.10 "
     "— 'the most damaging alternative explanation for any observed class effect'",
     "design_validator._sitelink_matching (fails closed without scipy)"),
)


def validate() -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True

    test = test_rows()
    dev_new = dev_new_rows()

    # 1. the adopted 120 ------------------------------------------------
    lattice_ok, report = dry_run(allocate())
    lines.append("[1] 120 test cells against design_validator (strict crossing):")
    lines.append("    " + report.splitlines()[0])
    ok &= lattice_ok

    # 2. counts ----------------------------------------------------------
    lines.append(f"[2] test rows {len(test)} · new dev rows {len(dev_new)} · "
                 f"total new {len(test) + len(dev_new)}")
    ok &= len(test) == 120 and len(dev_new) == 12

    # 3. dev reaches 6 per class with the pilot --------------------------
    pilot, pilot_probes = load_split(REPO / "data/benchmark/pilot")
    per_class_new = {c: sum(1 for r in dev_new if r.cls == c) for c in CLASSES}
    per_class_pilot = {c: sum(1 for k in pilot if k.constraint_class.value == c)
                       for c in CLASSES}
    totals = {c: per_class_new[c] + per_class_pilot[c] for c in CLASSES}
    lines.append(f"[3] dev per class: pilot {per_class_pilot} + new {per_class_new} "
                 f"= {totals}  (ADR-0007 wants 6 each)")
    ok &= all(v == 6 for v in totals.values())
    lines.append(f"    existing pilot probes: {len(pilot_probes)} (stay pilot/dev material)")

    # 4. no id collides, anywhere ---------------------------------------
    all_ids = (
        [k.constraint_id for k in pilot]
        + [r.constraint_id for r in dev_new]
        + [r.constraint_id for r in test]
    )
    dupes = sorted({i for i in all_ids if all_ids.count(i) > 1})
    lines.append(f"[4] 12 pilot + 12 new dev + 120 test = {len(all_ids)} ids, "
                 f"{len(set(all_ids))} distinct, {len(dupes)} collisions"
                 + (f" -> {dupes}" if dupes else ""))
    ok &= not dupes and len(all_ids) == 144

    # index ranges, stated so the allocation is auditable
    def span(ids: list[str]) -> str:
        nn = sorted({int(i.rsplit("-", 1)[1]) for i in ids})
        return f"{nn[0]:02d}..{nn[-1]:02d}" if nn else "-"
    lines.append(f"    index spans: pilot {span([k.constraint_id for k in pilot])} · "
                 f"new dev {span([r.constraint_id for r in dev_new])} · "
                 f"test {span([r.constraint_id for r in test])}")

    # 5. the cross-split rule, run for real ------------------------------
    v = BenchmarkDesignValidator()
    rule = v.validate_global_id_uniqueness(pilot)
    lines.append(f"[5] cross-split rule on the real pilot: {rule.message}")
    ok &= rule.passed

    # 6. answer-type allocation (ADR-0017 as amended 2026-10-07) ----------
    # The invariant is no longer "identical across all four classes". C2 and C3
    # are boolean everywhere; C1 and C4 keep the axis-fixed mix. What must still
    # hold is that the CONFIRMATORY arms are balanced, because §4.11 rests the
    # claim on C1+C2 vs C3+C4 and nothing else.
    from propose_coverage_matrix import chance_pscr

    for label, rows in (("test", test), ("new dev", dev_new)):
        mix = {
            c: {
                t: sum(1 for r in rows if r.cls == c and r.answer_type == t)
                for t in ("entity", "boolean", "date")
            }
            for c in CLASSES
        }
        c2c3_boolean = all(
            r.answer_type == "boolean" for r in rows if r.cls in ("C2", "C3")
        )
        c1_eq_c4 = mix["C1"] == mix["C4"]
        c2_eq_c3 = mix["C2"] == mix["C3"]
        per_cls = {
            c: sum(chance_pscr(CARDINALITY[r.answer_type]) for r in rows if r.cls == c)
            / max(1, sum(1 for r in rows if r.cls == c))
            for c in CLASSES
        }
        arm_a = (per_cls["C1"] + per_cls["C2"]) / 2
        arm_b = (per_cls["C3"] + per_cls["C4"]) / 2
        balanced = abs(arm_a - arm_b) < 1e-9
        lines.append(
            f"[6] {label}: C2/C3 boolean={c2c3_boolean} · C1==C4 mix={c1_eq_c4} · "
            f"C2==C3 mix={c2_eq_c3} · confirmatory {arm_a:.3f} vs {arm_b:.3f} "
            f"balanced={balanced}"
        )
        lines.append(f"    C1 {mix['C1']} · C2 {mix['C2']}")
        ok &= c2c3_boolean and c1_eq_c4 and c2_eq_c3 and balanced

    # 7. ordering is deterministic ---------------------------------------
    idx = constraint_indices(pilot)
    lines.append(f"[7] constraint_indices on the pilot: {len(idx)} indices, "
                 f"reversal-stable: {idx == constraint_indices(list(reversed(pilot)))}")
    ok &= idx == constraint_indices(list(reversed(pilot)))

    # 8. D0: every schema resolves ---------------------------------------
    from semintegrity.detectors.d0.registry import PredicateRegistry

    reg = PredicateRegistry()
    reg.autodiscover()
    needed = sorted({r.schema_id.lower().replace("-", "_") for r in test + dev_new})
    missing = [n for n in needed if not reg.has(n)]
    lines.append(f"[8] D0: {len(needed)} distinct schemas needed, "
                 f"{len(missing)} unregistered" + (f" -> {missing}" if missing else ""))
    ok &= not missing

    return ok, lines


# ---------------------------------------------------------------------------
# The deterministic authoring manifest.
#
# Enumerates every one of the 132 planned constraints and NOTHING else: no
# entities, no QIDs, no gold answers, no sources. It is the allocation, made
# machine-readable, so that authoring can be driven from it in verified batches
# and so that "did we author exactly the approved cells?" is a diff rather than
# a judgement.
def _instance_index(row: Row, siblings: list[Row]) -> int:
    """1-based position among the constraints sharing this schema, within split.

    For a test row this is the domain's position in §4.3's order, because the
    test lattice gives each (schema, domain) cell exactly one constraint. For a
    new-dev row it is always 1: each dev schema carries exactly one new-dev
    instance. Defined per split because ADR-0002's "5 instances per schema" rule
    governs the test split only.
    """
    same = sorted(
        (r for r in siblings if r.schema_id == row.schema_id and r.split == row.split),
        key=lambda r: (DOMAINS.index(r.domain), r.constraint_id),
    )
    return same.index(row) + 1


def _corroboration_required(row: Row) -> bool:
    """Mirrors design_validator._corroboration, which reads design.yaml.

    The AXIS is a trigger, not only the answer type. Axes 4 and 6 are temporal by
    construction ("Event precedence", "Interval boundary"), so a C2 or C3 on one
    of them is a temporal fact whatever its answer type. Without that trigger the
    2026-10-07 answer-type amendment would have silently narrowed §4.3's
    corroboration requirement, which it is not permitted to do.
    """
    return (
        row.domain == "history"
        or row.answer_type == "date"
        or row.cls == "C4"
        or row.axis.index in date_axes()
    )


def _comparison_universe_required(row: Row) -> bool:
    from semintegrity.schemas.constraint import EXTREMAL_SCHEMA_INDICES

    return row.axis.index in EXTREMAL_SCHEMA_INDICES


def build_manifest() -> dict:
    rows = [*test_rows(), *dev_new_rows()]
    out = []
    for row in rows:
        extra, special = EVIDENCE_BY_AXIS[row.axis.index]
        out.append(
            {
                "constraint_id": row.constraint_id,
                "split": "test" if row.split == "test" else "dev",
                "split_detail": row.split,
                "class": row.cls,
                "domain": row.domain,
                "family_id": row.family_id,
                "schema_id": row.schema_id,
                "schema_index": row.axis.index,
                "axis": row.axis.index,
                "axis_name": row.axis.name,
                "instance_index": _instance_index(row, rows),
                "theme": row.theme,
                "answer_type": row.answer_type,
                "answer_space_cardinality": CARDINALITY[row.answer_type],
                "d0_predicate": row.schema_id.lower().replace("-", "_"),
                "d0_behaviour": d0_behaviour(row.axis, row.cls),
                "d0_structural_limit": d0_note(row.cls) or None,
                "evidence_policy": {
                    "baseline": EVIDENCE_BASELINE,
                    "axis_specific": extra,
                    "special_handling": bool(special),
                    "special_handling_note": special or None,
                },
                "corroboration_required": _corroboration_required(row),
                "comparison_universe_required": _comparison_universe_required(row),
                "probes_expected": 8,
                "authoring_status": "NOT_AUTHORED",
            }
        )
    out.sort(key=lambda r: (r["split"] != "test", r["constraint_id"]))
    return {
        "generated_by": "scripts/propose_authoring_plan.py --manifest",
        "authoritative_sources": {
            "which_cells": "docs/BENCHMARK_COVERAGE_MATRIX.md (Revision 3)",
            "accounting": "docs/AUTHORING_PLAN.md",
            "lattice": "ADR-0002",
            "dev_set": "ADR-0007 (amended 2026-10-07)",
            "answer_type": "ADR-0017",
            "comparison_universe": "ADR-0018",
        },
        "contains": "the planned allocation ONLY - no entities, QIDs, gold answers or sources",
        "totals": {
            "planned_constraints": len(out),
            "test": sum(1 for r in out if r["split"] == "test"),
            "dev_new": sum(1 for r in out if r["split"] == "dev"),
            "planned_probes": 8 * len(out),
            "existing_pilot_constraints_separate": 12,
            "existing_pilot_probes_separate": 96,
            "constraints_at_freeze": len(out) + 12,
            "primary_probes_at_freeze": 8 * len(out) + 96,
        },
        "constraints": out,
    }


def manifest_summary(payload: dict) -> list[str]:
    from collections import Counter

    rows = payload["constraints"]
    lines = []
    t = payload["totals"]
    lines.append(f"planned {t['planned_constraints']} = test {t['test']} + dev {t['dev_new']}"
                 f"; probes {t['planned_probes']}")
    lines.append(f"at freeze: {t['constraints_at_freeze']} constraints, "
                 f"{t['primary_probes_at_freeze']} primary probes "
                 f"({t['existing_pilot_probes_separate']} pilot kept separate)")
    for key in ("class", "domain", "axis", "answer_type"):
        counts = Counter(r[key] for r in rows)
        lines.append(f"by {key}: {dict(sorted(counts.items(), key=lambda kv: str(kv[0])))}")
    for split in ("test", "dev"):
        counts = Counter(r["class"] for r in rows if r["split"] == split)
        lines.append(f"{split} by class: {dict(sorted(counts.items()))}")
    lines.append(f"corroboration required: {sum(r['corroboration_required'] for r in rows)}")
    lines.append(
        f"comparison_universe required: {sum(r['comparison_universe_required'] for r in rows)}"
    )
    lines.append(f"schemas touched: {len({r['schema_id'] for r in rows})}")
    lines.append(f"families touched: {len({r['family_id'] for r in rows})}")
    return lines


def markdown(ok: bool, checks: list[str]) -> str:
    out: list[str] = []
    w = out.append
    pilot, pilot_probes = load_split(REPO / "data/benchmark/pilot")

    w("# Authoring plan — 132 constraints")
    w("")
    w("**Generated by `scripts/propose_authoring_plan.py`; regenerate rather than")
    w("edit.** The 120 test cells are *imported* from the approved Revision 3")
    w("matrix, so this plan cannot drift from it.")
    w("")
    w("**Nothing is authored.** No constraint, no probe, no entity, no QID, no gold")
    w("answer, no source.")
    w("")
    w("| | status |")
    w("|---|---|")
    w("| 120 test cells | **ADOPTED** — decisions A1-A6, 2026-10-06 |")
    w("| 12 new dev cells | **ADOPTED** - 2026-10-07 |")
    w("| Validation gates | **all 5 enforced** from the production path (§7) |")
    w("")

    # --- 1. accounting -----------------------------------------------------
    w("## 1. Accounting")
    w("")
    w("| | count | state |")
    w("|---|---|---|")
    w(f"| Existing pilot constraints → dev/tuning | **{len(pilot)}** | authored, DRAFT, run three times |")
    w("| New **test** constraints | **120** | to author |")
    w("| New **dev** constraints | **12** | to author |")
    w("| **At freeze** | **144** | 120 test + 24 dev |")
    w("| **Newly authored** | **132** | |")
    w("")
    w("| probes | count |")
    w("|---|---|")
    w("| Test, new | 120 x 8 = **960** |")
    w("| Dev, new | 12 x 8 = **96** |")
    w("| **New primary probes** | **1,056** |")
    w(f"| Existing pilot probes (separate) | **{len(pilot_probes)}** |")
    w("| Dev total at freeze | 24 x 8 = 192 |")
    w("| Primary at freeze | 1,152 |")
    w("")
    w(f"The existing {len(pilot_probes)} pilot probes stay **explicitly separate**: they")
    w("belong to the 12 pilot constraints, 28 of them carry the Variant A rewrite,")
    w("and the recorded run1/run2/run3 responses are keyed to their probe ids under")
    w("ADR-0005. They are never counted toward the 960.")
    w("")

    # --- 2. coverage -------------------------------------------------------
    w("## 2. Coverage")
    w("")
    w("### 2.1 Test — the adopted Revision 3 allocation")
    w("")
    w("30 per class · 6 families x 5 domains = 30 families · 6 schemas x 5")
    w("instances per class · two `date` axes · 10 entity / 10 boolean / 10 date")
    w("per class. Family index = axis index; schema index = axis index; test cell")
    w("indices 11-16.")
    w("")
    w("| axis | answer type | *m* | schemas | D0 |")
    w("|---|---|---|---|---|")
    for a in AXES:
        w(f"| {a.index} {a.name} | `{a.answer_type}` | {CARDINALITY[a.answer_type]} "
          f"| `S-C1-{a.index:02d}` … `S-C4-{a.index:02d}` | {d0_behaviour(a)} |")
    w("")
    w("### 2.2 Development - ADOPTED 2026-10-07")
    w("")
    w("ADR-0007 fixes dev at 24 constraints, 6 per class, disjoint from the 120,")
    w("with the 12 pilot absorbed and 12 further authored reusing the **same")
    w("schemas** with **different entity instantiations**. 12 = 3 families x 4")
    w("classes, so the only open choice is which (axis, domain) each family sits in.")
    w("")
    w("| family | domain | axis | answer type | schemas | why |")
    w("|---|---|---|---|---|---|")
    reasons = {
        2: "boolean answer type; history was never covered by the pilot",
        3: "entity answer type; biology was never covered by the pilot",
        4: "date answer type; gives D0's ANCHOR predicate dev exposure before test",
    }
    for axis_index, domain in DEV_NEW:
        a = AXIS_BY_INDEX[axis_index]
        w(f"| `{family_id(domain, axis_index)}` | {domain} | {axis_index} "
          f"| `{a.answer_type}` | `S-C1-{axis_index:02d}` … `S-C4-{axis_index:02d}` "
          f"| {reasons[axis_index]} |")
    w("")
    w("With the pilot's three axis-1 families this gives dev **6 per class** and")
    w("coverage of **all five domains** and **four of six axes**.")
    w("")
    w("**Accepted limitation of the calibration design — not a defect to fix.**")
    w("**Axes 5 and 6 have no new-dev coverage.** D2's per-class thresholds, D3's")
    w("prompt tuning and D0's dev-split predicate corrections will therefore be")
    w("calibrated without ever seeing an extremal-uniqueness (axis 5) or")
    w("interval-boundary (axis 6) schema, and the tuned artefacts are applied to")
    w("test constraints of those schemas regardless. Widening dev would mean more")
    w("than 24 constraints, which ADR-0007 fixes, so this is a consequence of the")
    w("approved design rather than an oversight. It is recorded here, in ADR-0007")
    w("and in the limitations so that it is reported rather than silently")
    w("corrected later.")
    w("")
    w("A second, smaller one: the pilot's 12 constraints tie answer type to")
    w("**class** rather than axis, because they predate ADR-0017. Dev's")
    w("answer-type mix is therefore not uniform across classes the way test's is.")
    w("ADR-0007 requires neither.")
    w("")

    # --- 3. probes ---------------------------------------------------------
    w("## 3. Probe design — unchanged")
    w("")
    w("K = 8. Each constraint carries all 8 (polarity x register x")
    w("directionality) cells exactly once; syntax rotates as")
    w("`SYNTAX[(cell_index + constraint_index) % 3]`, with `constraint_index`")
    w("supplied by `semintegrity.benchmark.ordering` — derived from the records,")
    w("never from source-file order. Polar cloze uses the validated Variant A")
    w("frame `The statement \"<stem>\" is ___.` **No factor is added and no level")
    w("is altered.**")
    w("")
    w("Per class: 30 x 8 = 240 slots over 24 factor cells = exactly 10 each.")
    w("Whole test split: 960 / 24 = exactly 40 each.")
    w("")

    # --- 4. evidence -------------------------------------------------------
    w("## 4. Ground truth and evidence")
    w("")
    w("Re-stated from §4.3, ADR-0011 and the `Constraint` schema. **No new")
    w("requirement is introduced.**")
    w("")
    w(f"**Every constraint:** {EVIDENCE_BASELINE}.")
    w("")
    w("**Wikidata is primary but explicitly not absolute truth** (§4.3). Temporal")
    w("constraints require the P580/P582 qualifiers. All historical and temporal")
    w("facts are corroborated against a second authoritative source. Evidence")
    w("resolves from the frozen cache and never from the network (ADR-0011).")
    w("")
    w("| axis | additional evidence | special handling before authoring |")
    w("|---|---|---|")
    for a in AXES:
        extra, special = EVIDENCE_BY_AXIS[a.index]
        w(f"| {a.index} {a.name} | {extra} | {special or '—'} |")
    w("")
    w("**Four axes need a sourcing route decided before authoring starts** — 2, 3,")
    w("4 and 6 above — and **axis 5 is the heaviest**: Wikidata has no superlative")
    w("property, so every extremal constraint needs either a ranked query over an")
    w("explicitly recorded comparison set or an authoritative list. Without the")
    w("comparison set recorded, the gold answer is not well-defined.")
    w("")
    w("Also unchanged: `prerequisite_atomic_facts` feed the §4.11 knowledge screen,")
    w("and conditioning on them is \"a reporting view, never an inclusion criterion\".")
    w("")
    w("### 4.1 Authoring checklist — binding, per axis")
    w("")
    w("These are requirements an authored constraint must satisfy, not advice.")
    w("They restate the approved policy; nothing is added to it.")
    w("")
    w("| # | requirement | machine-checkable today |")
    w("|---|---|---|")
    w("| 1 | Every constraint: >=1 Wikidata Evidence record with "
      "`supports_gold=True`, QIDs, sitelinks, and the gold_source triple | yes - "
      "`Constraint._cross_field` + the verification ladder |")
    w("| 2 | **Axis 5 superlatives:** a frozen `comparison_universe` is recorded - "
      "either an enumerated set (>=2 members with QIDs and measured values) or an "
      "authoritative ranked source with its frozen snapshot key and gold's rank | "
      "**yes** - `Constraint._cross_field` refuses promotion without it "
      "(ADR-0018); prose is not accepted |")
    w("| 3 | **Axis 2 disjointness:** the mutual exclusivity itself is sourced, "
      "not only the two memberships | partly - presence of Evidence is checked, "
      "its subject matter is not |")
    w("| 4 | **Axis 3 C3 transitivity:** all three claims x->y, y->z, x->z are "
      "recorded as separate Evidence records | partly - count is checkable, "
      "semantics are not |")
    w("| 5 | **Axis 4 and axis 6, and every C4:** P580/P582 qualifiers recorded "
      "in `temporal_validity`, plus a second authoritative source | yes - C4 "
      "requires `temporal_validity` (schema) and corroboration is enforced "
      "(gate C) |")
    w("| 6 | **Axis 6 end dates:** `end_unknown` distinguishes 'still valid' "
      "from 'unknown'; corroboration mandatory | yes - `TemporalValidity` "
      "forbids an end date together with `end_unknown` |")
    w("")
    w("Requirements 3 and 4 are **partly** checkable: the validator can count")
    w("Evidence records but cannot judge whether a record establishes")
    w("disjointness or closes a transitive chain. Those stay human review items,")
    w("recorded here so the limit is visible rather than assumed away.")
    w("")

    # --- 5. D0 -------------------------------------------------------------
    w("## 5. D0 compatibility")
    w("")
    w("Every schema maps to a registration that already exists. **No detection")
    w("logic is added.**")
    w("")
    w("| schema | D0 registration | behaviour | honest limit |")
    w("|---|---|---|---|")
    for a in AXES:
        for cls in CLASSES:
            sid = schema_id(cls, a.index)
            note = d0_note(cls)
            w(f"| `{sid}` | `{sid.lower().replace('-', '_')}` | {d0_behaviour(a)} "
              f"| {note or '—'} |")
    w("")
    n_struct = sum(1 for cls in CLASSES if d0_note(cls)) * len(AXES)
    w(f"**{n_struct} of 24 schemas carry `N/A-struct`** — every C2 and C3. Their")
    w("class structure is not recoverable from a Track A response: the probe asks")
    w("the conjunction, or the instantiated universal, as a whole and the model")
    w("returns one token. Each registration says so in its `formal_statement`, and")
    w("that text is copied into the freeze manifest and every audit record.")
    w("")
    w("**Schemas whose intended semantics D0 cannot honestly represent**, flagged")
    w("rather than reinterpreted:")
    w("")
    w("* **all six C2 schemas** — per-conjunct verification is impossible;")
    w("* **all six C3 schemas** — the quantifier and its variable binding are")
    w("  absent from the response;")
    w("* **`S-C3-03`** (containment transitivity) specifically: the chain spans")
    w("  three claims, and D0 compares two responses within one constraint;")
    w("* **`S-C3-05`** (extremal uniqueness stated universally) — `EXCL` sees only")
    w("  whether two answers differ.")
    w("")
    w("None of these is weakened to make D0 fit. §4.8.1 makes D0 coverage a")
    w("reported result in its own right, so the limit is reported, not removed.")
    w("")

    # --- 6. allocation -----------------------------------------------------
    w("## 6. The 132-constraint allocation")
    w("")
    w("### 6.1 Summary")
    w("")
    w("| split | families | constraints | per class | cell indices |")
    w("|---|---|---|---|---|")
    w("| test | 30 (6 x 5 domains) | **120** | 30 | 11-16 |")
    w("| dev, new | 3 | **12** | 3 | 02-04 |")
    w(f"| dev, existing (pilot) | 3 | {len(pilot)} | 3 | 01 |")
    w("| **dev total at freeze** | 6 | **24** | 6 | 01-04 |")
    w("")
    w("### 6.2 Test — 120 rows, by domain")
    w("")
    for domain in DOMAINS:
        w(f"**{domain}**")
        w("")
        w("| family | axis | theme | answer | C1 | C2 | C3 | C4 |")
        w("|---|---|---|---|---|---|---|---|")
        for a in AXES:
            idx = TEST_INDEX_BASE + a.index
            ids = " | ".join(f"`{constraint_id(c, domain, idx)}`" for c in CLASSES)
            w(f"| `{family_id(domain, idx)}` | {a.index} | {a.themes[domain]} "
              f"| `{a.answer_type}` | {ids} |")
        w("")

    w("### 6.3 Development — the 12 new rows")
    w("")
    w("| family | axis | domain | theme | answer | C1 | C2 | C3 | C4 |")
    w("|---|---|---|---|---|---|---|---|---|")
    for axis_index, domain in DEV_NEW:
        a = AXIS_BY_INDEX[axis_index]
        ids = " | ".join(f"`{constraint_id(c, domain, axis_index)}`" for c in CLASSES)
        w(f"| `{family_id(domain, axis_index)}` | {axis_index} | {domain} "
          f"| {a.themes[domain]} | `{a.answer_type}` | {ids} |")
    w("")
    w("Entity sets must differ from the test constraints that share these schemas")
    w("and domains — `K-Cx-HIS-12`, `K-Cx-BIO-13`, `K-Cx-SCI-14`. Enforced by")
    w("`validate_split_disjointness` before freeze.")
    w("")
    w("### 6.4 Ordering and ids, pinned before generation")
    w("")
    w("* **`constraint_id`** `K-<class>-<domain>-<nn>`; **`family_id`**")
    w("  `F-<domain>-<nn>`; **`schema_id`** `S-<class>-<nn>`; **`probe_id`**")
    w("  `<constraint_id>-P<nn>`.")
    w("* **Cell index allocation:** pilot 01 · new dev 02-04 · reserved 05-10 ·")
    w("  **test 11-16**. The grammar carries no split field, so this is the only")
    w("  thing keeping the splits apart.")
    w("* **`constraint_index`** (which fixes every probe's syntax) =")
    w("  0-based position within the class, ordered by domain in §4.3's order,")
    w("  then schema index, then cell index —")
    w("  `semintegrity.benchmark.ordering.constraint_indices`. A pure function of")
    w("  the records, so regeneration reproduces every probe.")
    w("")

    # --- 7. gates ----------------------------------------------------------
    w("## 7. Validation gates")
    w("")
    w("Every authored constraint must pass all of these before entering the")
    w("benchmark. **All of them execute from the production validation path** -")
    w("`python -m semintegrity.benchmark.validate`, which Slurm uses as its")
    w("preflight gate. Five were closed on 2026-10-07: three had no")
    w("implementation and two had one that nothing called.")
    w("")
    w("| gate | what it checks | enforced by |")
    w("|---|---|---|")
    for name, what, by in GATES:
        mark = "**GAP** — " if by.startswith("GAP") else ""
        w(f"| {name} | {what} | {mark}{by.removeprefix('GAP — ')} |")
    w("")
    gaps = [g for g in GATES if g[2].startswith("GAP")]
    if gaps:
        w(f"**{len(gaps)} gates are still not enforced:**")
        w("")
        for name, _, by in gaps:
            w(f"* **{name}** - {by.removeprefix('GAP - ')}")
    else:
        w("**No gate is left unenforced.** Each is exercised by")
        w("`tests/unit/test_authoring_gates.py`, which checks both that it fires on")
        w("a violating input and that the real pilot still passes - a gate that")
        w("cannot fail is the same defect as one that does not exist.")
    w("")
    w("Run as:")
    w("")
    w("```bash")
    w("python -m semintegrity.benchmark.validate --split test --k 8 \\")
    w("    --strict-lattice --strict-d0")
    w("```")
    w("")

    # --- 8. validation -----------------------------------------------------
    w("## 8. Plan validation")
    w("")
    w("```")
    for line in checks:
        w(line)
    w("```")
    w("")
    w(f"**Plan internally consistent: {'YES' if ok else 'NO'}.**")
    w("")
    w("`sitelink_matching` is **not** assessed here and cannot be: §4.3's")
    w("entity-familiarity matching is a property of the entities an author")
    w("chooses, and no entity exists yet. It is an authoring-time gate, and it")
    w("fails closed without scipy.")
    w("")
    w("## 9. Axis-5 comparison universes - RESOLVED 2026-10-07")
    w("")
    w("Checklist item 2 had no field to live in. **ADR-0018 adds one.**")
    w("")
    w("`ComparisonUniverse` is now part of the constraint record and is required")
    w("for the four axis-5 schemas before they may leave DRAFT:")
    w("")
    w("| field | records |")
    w("|---|---|")
    w("| `universe` | what is being compared, in words |")
    w("| `membership_rule` | how membership is decided, precisely enough to rebuild the set |")
    w("| `measure` | the quantity ordered over, with its property |")
    w("| `frozen_at` | when the universe was fixed |")
    w("| `members[]` | the enumerated set - label, QID, measured value, >=2 members |")
    w("| `ranked_source` | or an authoritative ranking - name, url, retrieved, frozen `snapshot`, `query`, `rank_of_argmax` |")
    w("| `direction` | `max` or `min` - which extremum the superlative names |")
    w("| `argmax_qid` / `argmax_label` | the entity ASSERTED to be the extremum (not the gold answer: axis 5 is boolean) |")
    w("")
    w("Exactly one of `members` or `ranked_source` is supplied. Enforcement:")
    w("")
    w("* **hard** - `Constraint._cross_field` refuses to construct an extremal")
    w("  constraint at EVIDENCE_VERIFIED, HUMAN_VALIDATED or FROZEN without one,")
    w("  so it cannot be bypassed by skipping the validator;")
    w("* **visible** - `design_validator._comparison_universe` warns while DRAFT;")
    w("* **self-consistent** - an enumerated universe must contain `gold_answer`;")
    w("* **frozen** - `RankedSource.snapshot` is required, so a ranking is always")
    w("  backed by the frozen cache rather than by a live endpoint (ADR-0011);")
    w("* **prose is refused** - the check consults `comparison_universe` and")
    w("  nothing else; a comparison set written into `ambiguity_notes` does not")
    w("  satisfy it, and a test asserts that.")
    w("")
    w("Scope: the four axis-5 schemas only. The other 20 default to `None` and are")
    w("unaffected, as are the 12 pilot constraints, which predate the field.")
    w("")
    w("**What it does not establish.** Nothing verifies that `membership_rule`")
    w("really describes `members`, or that the universe matches the one the")
    w("constraint text implies. The gate establishes that the universe is recorded")
    w("and frozen, not that it is correct - which stays a human review item,")
    w("alongside axis-2 disjointness and axis-3 transitive chains.")
    w("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--manifest", type=Path,
                    help="write the deterministic 132-row authoring manifest (JSON)")
    args = ap.parse_args()

    ok, checks = validate()

    if args.manifest:
        import json

        payload = build_manifest()
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.manifest} - {len(payload['constraints'])} planned constraints")
        for line in manifest_summary(payload):
            print(f"  {line}")
        return 0 if ok else 1

    if args.check:
        for line in checks:
            print(line)
        print(f"\nplan internally consistent: {'YES' if ok else 'NO'}")
        return 0 if ok else 1

    md = markdown(ok, checks)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
        print(f"wrote {args.out} ({len(md.splitlines())} lines)")
    else:
        print(md)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
