#!/usr/bin/env python3
"""Verify a checkout carries the 2026-10-06 approved implementation.

    python scripts/cluster/verify_implementation.py

Read-only, idempotent, verbose — ADR-0010's requirements for a cluster script.
It writes nothing, launches nothing and needs no GPU. Run it on the Mac and on
the cluster and the two outputs must agree line for line; the fingerprints make
that comparison a string match rather than a judgement.

Why fingerprints rather than ``git``: the sync excludes ``.git``, so the cluster
copy is not a repository and ``git status`` cannot answer "is this the approved
code?" there. Content hashes can.

Exit status: 0 if every check passes, 1 otherwise.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

PASS, FAIL = "PASS", "FAIL"

# --- pinned expectations -------------------------------------------------
# Computed on the Mac at the approved state. The first three are the POINT of
# the cloze rewrite: §4.4.1 defines probe equivalence on the formal
# representation, and these are byte-identical to their pre-rewrite values, so
# "the rewrite changed surface text only" is one string comparison.
FORMAL_FIELDS = (
    "constraint_id", "probe_id", "logical_form", "subject", "predicate",
    "object", "time_scope", "quantifier", "polarity", "answer_type",
)
FACTOR_FIELDS = ("syntax", "polarity", "register", "directionality", "factor_cell_index")

EXPECTED = {
    "n_constraints": 12,
    "n_probes": 96,
    "n_polar_cloze": 28,
    "formal_fp": "c377f3df44a37f3f93c087684838191d692dbce1dbbf513c0a0315a2e6f634d3",
    "factor_fp": "3856d4b934a970f8115eba5cee6e9caf90dad812df1b6618bebdd49d1d3307b9",
    "expected_answer_fp": "bd4ec4a86704deff7d8042d2877d034e383ac8b4cdc403babf9d36386c5ec2d3",
    # TEXT is the one fingerprint that MOVED. Pre-rewrite it was
    # 7b549d7ee0a6c9964305328fe4529c240dfb0a43b927a89508b3b311749a53a8.
    "text_fp": "593196c8692f983d06977270a328609a91597b528cd227a5c516270b66e67d87",
    "n_d0_predicates": 28,
    "n_d0_per_schema": 24,
    "n_d0_anchor_schemas": 4,
}

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, PASS if ok else FAIL, detail))


def _fp(rows: list[dict], fields: tuple[str, ...]) -> str:
    items = sorted(tuple(str(r[f]) for f in fields) for r in rows)
    return hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()


def _pairs_fp(rows: list[dict], field: str) -> str:
    items = sorted((r["probe_id"], r[field]) for r in rows)
    return hashlib.sha256(json.dumps(items).encode()).hexdigest()


def main() -> int:
    # --- 1. ADR approvals -------------------------------------------------
    adrs = {
        "ADR-0002-benchmark-design-lattice.md": "APPROVED BY RESEARCHER 2026-10-06",
        "ADR-0003-probe-factor-balancing.md": "APPROVED BY RESEARCHER 2026-10-06",
        "ADR-0017-answer-type-allocation.md": "APPROVED BY RESEARCHER 2026-10-06",
    }
    for fname, needle in adrs.items():
        path = ROOT / "docs" / "decisions" / fname
        if not path.is_file():
            check(f"{fname[:8]} present", False, f"missing: {path}")
            continue
        head = path.read_text(encoding="utf-8")[:600]
        check(f"{fname[:8]} approved", needle in head,
              needle if needle in head else "status line does not carry the approval")

    # Untouched decisions must stay untouched.
    adr16 = (ROOT / "docs/decisions/ADR-0016-d4-distribution-construction.md").read_text()
    check("ADR-0016 still OPEN", "OPEN — AWAITING RESEARCHER DECISION" in adr16,
          "Q5/D4 unresolved, as approved")

    # --- 2. coverage matrix ----------------------------------------------
    matrix = (ROOT / "docs/BENCHMARK_COVERAGE_MATRIX.md")
    if matrix.is_file():
        text = matrix.read_text(encoding="utf-8")
        check("coverage matrix Revision 4", "Revision 4" in text,
              "answer type by (axis, class); cell allocation unchanged")
        rows_ok = (
            "| C1 | 10 | 10 | 10 |" in text
            and "| C4 | 10 | 10 | 10 |" in text
            and "| C2 | 0 | 30 | 0 |" in text
            and "| C3 | 0 | 30 | 0 |" in text
        )
        check("answer type by (axis, class)", rows_ok,
              "C1/C4 axis-fixed 10/10/10; C2/C3 boolean throughout")
        # Count rows of the §1 AXIS table only; `date` also appears once per
        # family row, so a whole-file count would conflate the two tables.
        axis_rows = [
            line for line in text.splitlines() if re.match(r"^\| [1-6] \| \*\*", line)
        ]
        # Columns are now C1 | C2 | C3 | C4; C1 is field 3.
        date_axes = [line for line in axis_rows if "`date`" in line.split("|")[3]]
        check("axis table has 6 rows", len(axis_rows) == 6, f"{len(axis_rows)} axes")
        check("date axes = 2 (A4)", len(date_axes) == 2,
              f"{len(date_axes)} of 6 axes are `date`-typed at C1")
    else:
        check("coverage matrix Revision 3", False, f"missing: {matrix}")

    # --- 3. Variant A cloze rewrite --------------------------------------
    probes = [
        json.loads(line)
        for line in (ROOT / "data/benchmark/pilot/probes.jsonl").read_text().splitlines()
        if line.strip()
    ]
    constraints = [
        json.loads(line)
        for line in (ROOT / "data/benchmark/pilot/constraints.jsonl").read_text().splitlines()
        if line.strip()
    ]
    check("pilot constraints = 12", len(constraints) == EXPECTED["n_constraints"],
          f"{len(constraints)} constraints")
    check("pilot probes = 96", len(probes) == EXPECTED["n_probes"], f"{len(probes)} probes")

    polar_cloze = [
        p for p in probes
        if p["syntax"] == "cloze" and p["expected_answer"] in ("YES", "NO")
    ]
    variant_a = [
        p for p in polar_cloze
        if p["probe_text"].startswith('The statement "') and p["probe_text"].endswith('" is ___.')
    ]
    check("polar-cloze probes = 28", len(polar_cloze) == EXPECTED["n_polar_cloze"],
          f"{len(polar_cloze)} polar-cloze probes")
    check("all 28 use Variant A", len(variant_a) == len(polar_cloze) == 28,
          f'{len(variant_a)}/28 match: The statement "<stem>" is ___.')
    stale = [p["probe_id"] for p in probes if p["probe_text"].endswith(": ___")]
    check("old ': ___' frame gone", not stale, f"{len(stale)} probes still use it")

    # --- 4. the formal representation did NOT move -----------------------
    for label, got, want in (
        ("formal representation (§4.4.1)", _fp(probes, FORMAL_FIELDS), EXPECTED["formal_fp"]),
        ("surface factors (§4.4.2)", _fp(probes, FACTOR_FIELDS), EXPECTED["factor_fp"]),
        ("expected answers", _pairs_fp(probes, "expected_answer"), EXPECTED["expected_answer_fp"]),
        ("probe text (SHOULD differ from pre-rewrite)", _pairs_fp(probes, "probe_text"),
         EXPECTED["text_fp"]),
    ):
        check(f"fingerprint: {label}", got == want, got[:16] + ("" if got == want else f" != {want[:16]}"))

    # --- 5. D0 registrations ---------------------------------------------
    try:
        from semintegrity.detectors.d0.registry import PredicateRegistry

        reg = PredicateRegistry()
        reg.autodiscover()
        names = reg.names()
        per_schema = [n for n in names if n.startswith("s_c")]
        anchors = [
            p.predicate_name for p in reg
            if p.predicate_name.startswith("s_c")
            and "temporal anchor precedence" in p.formal_statement
        ]
        hashes = {p.predicate_name: p.describe()["source_sha256"] for p in reg}
        check("D0 predicates = 28", len(names) == EXPECTED["n_d0_predicates"], f"{len(names)}")
        check("D0 per-schema = 24", len(per_schema) == EXPECTED["n_d0_per_schema"],
              f"{len(per_schema)}")
        check("D0 anchor schemas = 4", len(anchors) == EXPECTED["n_d0_anchor_schemas"],
              f"{len(anchors)} claim the temporal anchor "
              "(C1/C4 on the two date axes; C2/C3 are boolean, ADR-0017 amended)")
        check("D0 source hashes distinct", len(set(hashes.values())) == len(hashes),
              f"{len(set(hashes.values()))}/{len(hashes)} — the freeze manifest is meaningful")
        legacy = [n for n in ("c1_mutual_exclusion", "c2_conjunction",
                              "c3_functional_uniqueness", "c4_interval_precedence")
                  if n in names]
        check("4 pilot predicates intact", len(legacy) == 4, ", ".join(legacy))
    except Exception as exc:
        check("D0 registrations", False, f"{type(exc).__name__}: {exc}")

    # --- 6. ordering module ----------------------------------------------
    try:
        from semintegrity.benchmark.loader import load_split
        from semintegrity.benchmark.ordering import DOMAIN_ORDER, constraint_indices
        from semintegrity.schemas.enums import Domain

        cons, _ = load_split(ROOT / "data/benchmark/pilot")
        idx = constraint_indices(cons)
        check("ordering module importable", True, "semintegrity.benchmark.ordering")
        check("DOMAIN_ORDER matches §4.3", tuple(Domain) == DOMAIN_ORDER,
              " < ".join(d.value for d in DOMAIN_ORDER))
        check("constraint_indices total", len(idx) == len(cons),
              f"{len(idx)} indices for {len(cons)} constraints")
        shuffled = constraint_indices(list(reversed(cons)))
        check("ordering independent of input order", idx == shuffled,
              "same indices from a reversed list")
    except Exception as exc:
        check("ordering module", False, f"{type(exc).__name__}: {exc}")

    # --- 7. cross-split id check ------------------------------------------
    try:
        from semintegrity.benchmark.design_validator import BenchmarkDesignValidator
        from semintegrity.benchmark.loader import load_split
        from semintegrity.schemas.enums import Split

        v = BenchmarkDesignValidator()
        cons, _ = load_split(ROOT / "data/benchmark/pilot")
        clean = v.validate_global_id_uniqueness(cons)
        collider = cons[0].model_copy(update={"split": Split.TEST})
        fires = v.validate_global_id_uniqueness([*cons, collider])
        check("validate_global_id_uniqueness exists", True, "on BenchmarkDesignValidator")
        check("id check passes on the pilot", clean.passed, clean.message)
        check("id check FIRES on a collision", not fires.passed,
              fires.offenders[0] if fires.offenders else "no offender reported")
    except Exception as exc:
        check("cross-split id check", False, f"{type(exc).__name__}: {exc}")

    # --- 8. accounting ----------------------------------------------------
    try:
        import yaml

        design = yaml.safe_load((ROOT / "configs/benchmark/design.yaml").read_text())
        acc = design["splits"]["accounting"]
        want = {
            "existing_pilot_constraints": 12, "new_test_constraints": 120,
            "new_dev_constraints": 12, "constraints_at_freeze": 144,
            "newly_authored_constraints": 132, "existing_pilot_probes": 96,
            "new_primary_probes": 1056, "primary_probes_at_freeze": 1152,
        }
        bad = {k: (acc.get(k), w) for k, w in want.items() if acc.get(k) != w}
        check("accounting in design.yaml", not bad,
              "144 at freeze · 132 new · 1,056 new primary probes"
              if not bad else f"mismatches: {bad}")
        at = design["lattice"]["answer_type"]
        dates = [a for a, t in at["per_axis"].items() if t == "date"]
        check("answer_type fixed by (axis, class)", at["fixed_by"] == "axis_and_class",
              at["fixed_by"])
        check("two date axes recorded", len(dates) == 2, f"axes {sorted(dates)}")
        check("C2/C3 boolean on every axis",
              at["rule"]["C2"] == "boolean" and at["rule"]["C3"] == "boolean",
              f"C1={at['rule']['C1']} C2={at['rule']['C2']} "
              f"C3={at['rule']['C3']} C4={at['rule']['C4']}")
    except Exception as exc:
        check("accounting", False, f"{type(exc).__name__}: {exc}")

    # --- report ------------------------------------------------------------
    width = max(len(n) for n, _, _ in results)
    print("=" * (width + 58))
    print("APPROVED IMPLEMENTATION VERIFICATION — 2026-10-06 decisions A1-A9")
    print("=" * (width + 58))
    for name, status, detail in results:
        print(f"  [{status}] {name:{width}s}  {detail}")
    n_fail = sum(s == FAIL for _, s, _ in results)
    print("-" * (width + 58))
    print(f"  {len(results) - n_fail} PASS · {n_fail} FAIL")
    print(f"  checkout: {ROOT}")
    print()
    if n_fail:
        print("  THIS CHECKOUT IS NOT THE APPROVED IMPLEMENTATION. Do not spend a GPU.")
    else:
        print("  Checkout carries the approved implementation.")
        print("  This says nothing about CANON: canonicalisation is a property of")
        print("  model responses and requires a run.")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
