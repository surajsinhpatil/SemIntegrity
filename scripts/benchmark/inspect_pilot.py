#!/usr/bin/env python3
"""Inspect the pilot benchmark in full, in plain English. READ-ONLY.

Shows, for every constraint: its plain-English statement, identifiers, formal
representation, ground truth, all eight generated probes with their expected
answers, and its evidence and verification status.

    python scripts/benchmark/inspect_pilot.py                     # all 12
    python scripts/benchmark/inspect_pilot.py --constraint K-C1-GEO-01
    python scripts/benchmark/inspect_pilot.py --class C4
    python scripts/benchmark/inspect_pilot.py --domain geography
    python scripts/benchmark/inspect_pilot.py --compact           # one line each
    python scripts/benchmark/inspect_pilot.py --no-probes

This command never writes to the benchmark. It opens the JSONL records read-only
and prints them.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from semintegrity.benchmark.loader import is_frozen, load_split  # noqa: E402
from semintegrity.schemas.constraint import Constraint  # noqa: E402
from semintegrity.schemas.probe import Probe  # noqa: E402
from semintegrity.utils.paths import data_path  # noqa: E402

WIDTH = min(shutil.get_terminal_size((100, 24)).columns, 100)
HEAVY = "═" * WIDTH
LIGHT = "─" * WIDTH

STATUS_LINE = {
    "DRAFT": "DRAFT — authored; no human has reviewed this",
    "EVIDENCE_VERIFIED": "EVIDENCE-VERIFIED — machine checks pass; still no human review",
    "HUMAN_VALIDATED": "HUMAN-VALIDATED",
    "FROZEN": "FROZEN",
}

CLASS_NAME = {
    "C1": "Atomic — a single proposition with direct mutual exclusion",
    "C2": "Conjunctive / relational — two or more propositions that must hold jointly",
    "C3": "Quantified / rule-based — universal quantification with variable binding",
    "C4": "Temporal — reasoning over validity intervals or ordering",
}

FACTOR_W = 26


def wrap(text: str, indent: str = "    ", width: int | None = None) -> str:
    return textwrap.fill(
        " ".join(text.split()),
        width=width or WIDTH,
        initial_indent=indent,
        subsequent_indent=indent,
    )


def field(label: str, value: str, *, indent: str = "  ") -> None:
    print(f"{indent}{label:<16}{value}")


def cell_label(p: Probe) -> str:
    return (
        f"{p.syntax.value[:4]}/{p.polarity.value[:3]}/"
        f"{p.register.value[:4]}/{p.directionality.value[:3]}"
    )


def show_constraint(c: Constraint, probes: list[Probe], *, with_probes: bool) -> None:
    print(f"\n{HEAVY}")
    print(f" {c.constraint_id}   [{c.constraint_class.value}] {c.domain.value}   family {c.family_id}")
    print(HEAVY)

    # 1 — plain English
    print("\n  WHAT THIS CONSTRAINT SAYS")
    print(wrap(c.constraint_text, "    "))

    # 2 — identifiers
    print("\n  IDENTIFIERS")
    field("id", c.constraint_id)
    field("class", CLASS_NAME[c.constraint_class.value])
    field("domain", c.domain.value)
    field("family", c.family_id)
    field("schema", c.schema_id)
    field("split", c.split.value)

    # 3 — formal representation
    print("\n  FORMAL REPRESENTATION")
    field("logical form", c.notes.removeprefix("logical_form: "))
    field("D0 predicate", c.formal_predicate)
    if c.temporal_validity:
        tv = c.temporal_validity
        field("valid from", f"{tv.start} (precision: {tv.precision})")

    # 4 — ground truth
    print("\n  GROUND TRUTH")
    print(wrap(c.gold_proposition, "    "))
    field("expected answer", f"{c.gold_answer}   (type: {c.answer_type.value})", indent="\n  ")
    field("answer space", ", ".join(c.answer_space))
    if c.answer_aliases:
        for canon, aliases in c.answer_aliases.items():
            quoted = "  ".join(f'"{a}"' for a in aliases)
            field("accepted as", f"{canon}  <-  {quoted}")
    for e in c.entity_records or []:
        field("entity", f"{e.label}  ({e.qid}, {e.sitelinks} sitelinks)")
    for f in c.prerequisite_atomic_facts:
        field("prerequisite", f"{f.question}  -> {f.gold_answer}")

    # 7 — evidence and status
    n_ok = sum(e.supports_gold for e in c.evidence)
    print(f"\n  EVIDENCE  ({n_ok}/{len(c.evidence)} checks pass)")
    for e in c.evidence:
        mark = "PASS" if e.supports_gold else "FAIL"
        flag = "  <-- DISCREPANCY" if "DISCREPANCY" in (e.note or "") else ""
        print(f"    [{mark}] {e.query}{flag}")
        print(wrap(e.comparison, "           "))
        print(f"           source: {e.url}  retrieved {e.retrieved_at}")
        if "DISCREPANCY" in (e.note or ""):
            print(wrap(e.note, "           "))

    print(f"\n  VERIFICATION STATUS: {STATUS_LINE[c.verification_status.value]}")
    field("human validated", c.human_validated_by or "NO — nobody has reviewed this")
    if c.ambiguity_notes:
        print("\n  KNOWN AMBIGUITY")
        print(wrap(c.ambiguity_notes, "    "))
    if c.review_notes:
        print("\n  NEEDS HUMAN REVIEW")
        print(wrap(c.review_notes, "    "))

    # 5, 6 — probes and their expected answers
    if with_probes:
        print(f"\n  PROBES  ({len(probes)} generated)")
        print(f"    {'probe':<20}{'run':<5}{'factor cell':<{FACTOR_W}}{'expects':<18}question")
        print(f"    {LIGHT[:WIDTH - 4]}")
        for p in probes:
            in_run = "yes" if "pilot_run_subset=yes" in p.notes else "-"
            print(
                f"    {p.probe_id:<20}{in_run:<5}{cell_label(p):<{FACTOR_W}}"
                f"{p.expected_answer:<18}{p.probe_text}"
            )
        print("\n    run = in the 5-probe subset the Phase 3 pilot RUN uses (§4.12);")
        print("          all 8 are authored, because factor balance only holds at K=8 (ADR-0003).")


def show_compact(constraints, by_cid) -> None:
    print(f"\n{'id':<16}{'cls':<5}{'domain':<20}{'type':<9}{'gold':<20}{'status':<8}probes")
    print(LIGHT)
    for c in constraints:
        n_ok = sum(e.supports_gold for e in c.evidence)
        flag = "*" if any("DISCREPANCY" in (e.note or "") for e in c.evidence) else " "
        print(
            f"{c.constraint_id:<16}{c.constraint_class.value:<5}{c.domain.value:<20}"
            f"{c.answer_type.value:<9}{c.gold_answer[:19]:<20}"
            f"{c.verification_status.value[:5]:<8}{len(by_cid[c.constraint_id])}"
            f"   evidence {n_ok}/{len(c.evidence)}{flag}"
        )
    print("\n* = carries a recorded source discrepancy needing human adjudication")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--constraint", help="show one constraint by id")
    ap.add_argument("--class", dest="cls", help="filter by class, e.g. C4")
    ap.add_argument("--domain", help="filter by domain")
    ap.add_argument("--compact", action="store_true", help="one line per constraint")
    ap.add_argument("--no-probes", action="store_true")
    args = ap.parse_args()

    directory = data_path("benchmark") / "pilot"
    if not (directory / "constraints.jsonl").is_file():
        print("no pilot benchmark; run scripts/benchmark/build_pilot.py", file=sys.stderr)
        return 2
    constraints, probes = load_split(directory)

    by_cid: dict[str, list[Probe]] = {}
    for p in probes:
        by_cid.setdefault(p.constraint_id, []).append(p)
    for group in by_cid.values():
        group.sort(key=lambda p: p.index)

    selected = constraints
    if args.constraint:
        selected = [c for c in constraints if c.constraint_id == args.constraint]
        if not selected:
            print(f"unknown constraint {args.constraint!r}; known:", file=sys.stderr)
            for c in constraints:
                print(f"  {c.constraint_id}", file=sys.stderr)
            return 2
    if args.cls:
        selected = [c for c in selected if c.constraint_class.value == args.cls.upper()]
    if args.domain:
        selected = [c for c in selected if c.domain.value == args.domain]
    if not selected:
        print("no constraints match that filter", file=sys.stderr)
        return 2

    print(HEAVY)
    print(" SemIntegrity — PILOT BENCHMARK, FULL INSPECTION")
    print(f" {len(constraints)} constraints · {len(probes)} probes · "
          f"showing {len(selected)}")
    print(f" split frozen: {'YES' if is_frozen(directory) else 'NO'}   "
          f"human validated: {sum(1 for c in constraints if c.human_validated_by)}/{len(constraints)}")
    print(HEAVY)

    if args.compact:
        show_compact(selected, by_cid)
        return 0

    for c in selected:
        show_constraint(c, by_cid[c.constraint_id], with_probes=not args.no_probes)

    print(f"\n{HEAVY}")
    print(" END OF INSPECTION — this command wrote nothing.")
    print(" Every constraint above is DRAFT: machine evidence only, no human review.")
    print(HEAVY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
