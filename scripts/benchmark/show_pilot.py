#!/usr/bin/env python3
"""Display and validate the pilot benchmark. Offline, read-only.

    python scripts/benchmark/show_pilot.py              # summary + validation
    python scripts/benchmark/show_pilot.py --probes     # every probe
    python scripts/benchmark/show_pilot.py --constraint K-C1-GEO-01
    python scripts/benchmark/show_pilot.py --evidence   # evidence detail
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from semintegrity.benchmark.design_validator import BenchmarkDesignValidator  # noqa: E402
from semintegrity.benchmark.loader import check_probe_sets, is_frozen, load_split  # noqa: E402
from semintegrity.detectors.d0.registry import default_registry  # noqa: E402
from semintegrity.schemas.enums import Split  # noqa: E402
from semintegrity.utils.paths import data_path  # noqa: E402

RULE = "─" * 78
BADGE = {
    "DRAFT": "DRAFT           ",
    "EVIDENCE_VERIFIED": "EVIDENCE-VERIFIED",
    "HUMAN_VALIDATED": "HUMAN-VALIDATED ",
    "FROZEN": "FROZEN          ",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probes", action="store_true")
    ap.add_argument("--evidence", action="store_true")
    ap.add_argument("--constraint")
    ap.add_argument("--k", type=int, default=8)
    args = ap.parse_args()

    directory = data_path("benchmark") / "pilot"
    if not (directory / "constraints.jsonl").is_file():
        print("no pilot benchmark; run scripts/benchmark/build_pilot.py", file=sys.stderr)
        return 2
    constraints, probes = load_split(directory)
    by_cid = {c.constraint_id: c for c in constraints}

    if args.constraint:
        return _detail(by_cid, probes, args.constraint)

    print(RULE)
    print(" SemIntegrity — PILOT BENCHMARK")
    print(f" {len(constraints)} constraints · {len(probes)} probes · "
          f"frozen: {'yes' if is_frozen(directory) else 'NO'}")
    print(RULE)

    print(f"\n{'constraint':16s} {'cls':4s} {'domain':20s} {'type':8s} {'status':18s} evidence")
    print("-" * 78)
    for c in constraints:
        ev = c.evidence
        ok = sum(e.supports_gold for e in ev)
        mark = "" if not ev else ("all pass" if ok == len(ev) else f"{ok}/{len(ev)} PASS")
        print(f"{c.constraint_id:16s} {c.constraint_class.value:4s} {c.domain.value:20s} "
              f"{c.answer_type.value:8s} {BADGE[c.verification_status.value]} {mark}")

    print(f"\n{RULE}\n DESIGN\n{RULE}")
    print(f"  classes  : {dict(sorted(Counter(c.constraint_class.value for c in constraints).items()))}")
    print(f"  domains  : {dict(sorted(Counter(c.domain.value for c in constraints).items()))}")
    print(f"  families : {dict(sorted(Counter(c.family_id for c in constraints).items()))}")
    print(f"  answer   : {dict(sorted(Counter(c.answer_type.value for c in constraints).items()))}")
    cells = Counter(
        (p.syntax.value, p.polarity.value, p.register.value, p.directionality.value) for p in probes
    )
    print(f"  probes   : {len(probes)} over {len(cells)} distinct factor cells")

    print(f"\n{RULE}\n VALIDATION\n{RULE}")
    problems = check_probe_sets(constraints, probes, k=args.k)
    print(f"  [{'PASS' if not problems else 'FAIL'}] probe sets: {args.k}/constraint, "
          "mutually equivalent, distinct factor cells")
    for p in problems:
        print(f"         - {p}")
    report = BenchmarkDesignValidator().validate(
        constraints, split=Split.PILOT, known_predicates=default_registry().names()
    )
    for r in report.results:
        print(f"  {r}")

    print(f"\n{RULE}\n VERIFICATION LADDER\n{RULE}")
    statuses = Counter(c.verification_status.value for c in constraints)
    for key in ("DRAFT", "EVIDENCE_VERIFIED", "HUMAN_VALIDATED", "FROZEN"):
        print(f"  {BADGE[key]} {statuses.get(key, 0):2d}")
    n_ev = sum(len(c.evidence) for c in constraints)
    n_ok = sum(e.supports_gold for c in constraints for e in c.evidence)
    print(f"\n  machine-checked evidence: {n_ok}/{n_ev} checks pass")
    print("  human validation        : NONE. No constraint has been reviewed by a person.")
    print("  frozen                  : NO. The split is not frozen.")
    return 0


def _detail(by_cid, probes, cid: str) -> int:
    c = by_cid.get(cid)
    if c is None:
        print(f"unknown constraint {cid}; known: {sorted(by_cid)}", file=sys.stderr)
        return 2
    print(RULE)
    print(f" {c.constraint_id}  [{c.constraint_class.value} · {c.domain.value}]")
    print(RULE)
    print(f"status        : {c.verification_status.value}")
    print(f"family/schema : {c.family_id} / {c.schema_id}")
    print(f"predicate     : {c.formal_predicate}")
    print(f"constraint    : {c.constraint_text}")
    print(f"gold          : {c.gold_proposition}")
    print(f"answer        : {c.gold_answer}  (type {c.answer_type.value}, space {c.answer_space})")
    print(f"entities      : {list(zip(c.entities, c.entity_sitelinks, strict=False))}")
    print(f"ambiguity     : {c.ambiguity_notes}")
    print(f"review needed : {c.review_notes}")
    print(f"\nevidence ({sum(e.supports_gold for e in c.evidence)}/{len(c.evidence)} pass):")
    for e in c.evidence:
        print(f"  [{'PASS' if e.supports_gold else 'FAIL'}] {e.query:22s} {e.comparison}")
    print("\nprobes:")
    for p in sorted((p for p in probes if p.constraint_id == cid), key=lambda p: p.index):
        cellname = f"{p.syntax.value[:4]}/{p.polarity.value[:3]}/{p.register.value[:4]}/{p.directionality.value[:3]}"
        print(f"  {p.probe_id}  {cellname:24s} -> {p.expected_answer:9s} {p.probe_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
